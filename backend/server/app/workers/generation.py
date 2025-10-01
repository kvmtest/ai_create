"""
Celery workers for AI-powered asset generation, format conversion, and manual edits
"""
import asyncio
import logging
import time
import json
from typing import Dict, Any, List, Optional
from uuid import UUID
from pathlib import Path
from celery import Task
from celery.exceptions import Retry, MaxRetriesExceededError
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.db.session import get_db
from app.services.generation import GenerationService
from app.services.asset import AssetService
from app.services.admin import AdminService
from app.services.project import ProjectService
from app.services.config_manager import ConfigManager
from app.services.ai_providers import ai_manager, AIProviderError, AdaptationStrategy
from app.models.generation import GenerationJob
from app.models.asset import GeneratedAsset
from app.models.enums import JobStatus, ProjectStatus
from app.workers.queue_config import (
    GenerationRequestMessage, ManualEditMessage,
    TaskPriority, QueueName
)

logger = logging.getLogger(__name__)


class BaseGenerationTask(Task):
    """Base task class with common functionality for generation tasks"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        logger.error(f"Generation task {task_id} failed: {exc}")
        
        # Update job status to failed if job_id is provided
        if 'job_id' in kwargs:
            try:
                db = next(get_db())
                generation_service = GenerationService(db)
                generation_service.update_job_progress(UUID(kwargs['job_id']), 0, JobStatus.FAILED)
                db.close()
            except Exception as e:
                logger.error(f"Failed to update job status: {e}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry"""
        logger.warning(f"Generation task {task_id} retrying: {exc}")
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success"""
        logger.info(f"Generation task {task_id} completed successfully")


@celery_app.task(bind=True, base=BaseGenerationTask, name="app.workers.generation.generate_assets")
def generate_assets(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate assets for different platforms and formats using AI
    
    Args:
        message_data: GenerationRequestMessage data
        
    Returns:
        Dict with generation results
    """
    try:
        # Parse message
        message = GenerationRequestMessage(**message_data)
        logger.info(f"Starting asset generation for job {message.job_id}")
        
        # Get database session
        db = next(get_db())
        generation_service = GenerationService(db)
        asset_service = AssetService(db)
        admin_service = AdminService(db)
        config_manager = ConfigManager(db)
        
        try:
            # Update job status to processing
            generation_service.update_job_progress(message.job_id, 10, JobStatus.PROCESSING)
            
            # Get generation job details
            job = generation_service.get_job_status(str(message.job_id), message.user_id)
            if not job:
                raise ValueError("Generation job not found")
            
            # Get assets to process
            assets = []
            for asset_id in message.asset_ids:
                asset = asset_service.get_asset(asset_id, message.user_id)
                if asset:
                    assets.append(asset)
            
            if not assets:
                raise ValueError("No valid assets found for generation")
            
            # Get formats to generate
            formats = []
            for format_id in message.format_ids:
                format_obj = admin_service.get_format(format_id)
                if format_obj:
                    formats.append(format_obj)
            
            total_operations = len(assets) * (len(formats) + len(message.custom_sizes))
            completed_operations = 0
            
            generated_assets = []
            
            # Process each asset
            for asset in assets:
                logger.info(f"Processing asset {asset.id} for generation")
                
                # Generate for each format
                for format_obj in formats:
                    try:
                        generated_asset = _generate_asset_for_format(
                            asset, format_obj, message.job_id, generation_service, config_manager, provider=message.provider
                        )
                        generated_assets.append(generated_asset)
                        
                        completed_operations += 1
                        progress = int((completed_operations / total_operations) * 80) + 10
                        generation_service.update_job_progress(message.job_id, progress)
                        
                    except Exception as e:
                        logger.error(f"Failed to generate asset for format {format_obj.id}: {e}")
                        continue
                
                # Generate for custom sizes
                for custom_size in message.custom_sizes:
                    try:
                        generated_asset = _generate_asset_for_custom_size(
                            asset, custom_size, message.job_id, generation_service, provider=message.provider
                        )
                        generated_assets.append(generated_asset)
                        
                        completed_operations += 1
                        progress = int((completed_operations / total_operations) * 80) + 10
                        generation_service.update_job_progress(message.job_id, progress)
                        
                    except Exception as e:
                        logger.error(f"Failed to generate asset for custom size {custom_size}: {e}")
                        continue
            
            # Mark job as completed
            generation_service.update_job_progress(message.job_id, 100, JobStatus.COMPLETED)
            
            # Update project status to completed
            project_service = ProjectService(db)
            project = project_service.get_project_by_id(str(message.project_id), str(message.user_id))
            if project:
                project_service.update_project_status(project, ProjectStatus.COMPLETED)
            
            logger.info(f"Asset generation completed for job {message.job_id}")
            
            return {
                "status": "success",
                "job_id": str(message.job_id),
                "generated_assets": len(generated_assets),
                "assets_processed": len(assets)
            }
            
        finally:
            db.close()
            
    except Exception as exc:
        logger.error(f"Asset generation failed: {exc}")
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=120 * (2 ** self.request.retries),  # 2, 4, 8 minutes
                max_retries=2
            )
        else:
            # Mark job as failed
            try:
                db = next(get_db())
                generation_service = GenerationService(db)
                generation_service.update_job_progress(message_data["job_id"], 0, JobStatus.FAILED)
                db.close()
            except:
                pass
            
            raise MaxRetriesExceededError(f"Asset generation failed after {self.max_retries} retries: {exc}")


@celery_app.task(bind=True, base=BaseGenerationTask, name="app.workers.generation.apply_manual_edits")
def apply_manual_edits(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply manual edits to a generated asset
    
    Args:
        message_data: ManualEditMessage data
        
    Returns:
        Dict with edit results
    """
    try:
        # Parse message
        message = ManualEditMessage(**message_data)
        logger.info(f"Applying manual edits to asset {message.generated_asset_id}")
        
        # Get database session
        db = next(get_db())
        generation_service = GenerationService(db)
        
        try:
            # Get generated asset
            generated_asset = generation_service.get_generated_asset(message.generated_asset_id, message.user_id)
            if not generated_asset:
                raise ValueError("Generated asset not found")
            
            # Apply edits using image processing
            edited_asset_path = _apply_image_edits(
                generated_asset.storage_path,
                message.edit_operations,
                message.output_format,
                message.quality
            )
            
            # Update generated asset with edited version
            generation_service.update_generated_asset(message.generated_asset_id, {
                "edited_path": edited_asset_path,
                "manual_edits": message.edit_operations,
                "edit_applied_at": time.time()
            })
            
            logger.info(f"Manual edits applied to asset {message.generated_asset_id}")
            
            return {
                "status": "success",
                "generated_asset_id": str(message.generated_asset_id),
                "edited_path": edited_asset_path
            }
            
        finally:
            db.close()
            
    except Exception as exc:
        logger.error(f"Manual edit application failed: {exc}")
        
        # Retry once
        if self.request.retries < 1:
            raise self.retry(
                exc=exc,
                countdown=60,
                max_retries=1
            )
        else:
            raise MaxRetriesExceededError(f"Manual edit application failed: {exc}")


@celery_app.task(bind=True, base=BaseGenerationTask, name="app.workers.generation.convert_format")
def convert_format(self, asset_path: str, target_format: str, quality: str = "high") -> Dict[str, Any]:
    """
    Convert asset to different format
    
    Args:
        asset_path: Path to the source asset
        target_format: Target format (jpeg, png, webp)
        quality: Quality setting (high, medium, low)
        
    Returns:
        Dict with conversion results
    """
    try:
        logger.info(f"Converting {asset_path} to {target_format}")
        
        converted_path = _convert_image_format(asset_path, target_format, quality)
        
        logger.info(f"Format conversion completed: {converted_path}")
        
        return {
            "status": "success",
            "original_path": asset_path,
            "converted_path": converted_path,
            "target_format": target_format
        }
        
    except Exception as exc:
        logger.error(f"Format conversion failed: {exc}")
        raise exc


@celery_app.task(bind=True, base=BaseGenerationTask, name="app.workers.generation.batch_generate")
def batch_generate(self, job_ids: List[str]) -> Dict[str, Any]:
    """
    Process multiple generation jobs in batch
    
    Args:
        job_ids: List of generation job IDs
        
    Returns:
        Dict with batch results
    """
    try:
        logger.info(f"Starting batch generation for {len(job_ids)} jobs")
        
        results = []
        failed_jobs = []
        
        for job_id in job_ids:
            try:
                # Get job details from database
                db = next(get_db())
                generation_service = GenerationService(db)
                job = generation_service.get_job_by_id(UUID(job_id))
                db.close()
                
                if not job:
                    failed_jobs.append(job_id)
                    continue
                
                # Create generation message
                message_data = {
                    "message_id": f"batch_{job_id}",
                    "message_type": "generation_request",
                    "user_id": str(job.user_id),
                    "job_id": job_id,
                    "project_id": str(job.original_asset_id),  # This should be project_id
                    "asset_ids": [str(job.original_asset_id)],
                    "format_ids": [],  # Should be extracted from job
                    "custom_sizes": job.custom_sizes or [],
                    "priority": TaskPriority.NORMAL,
                    "created_at": job.created_at.isoformat()
                }
                
                # Schedule generation task
                result = generate_assets.apply_async(
                    kwargs={"message_data": message_data},
                    queue=QueueName.GENERATION
                )
                
                results.append({"job_id": job_id, "task_id": result.id})
                
            except Exception as e:
                logger.error(f"Failed to process job {job_id} in batch: {e}")
                failed_jobs.append(job_id)
        
        logger.info(f"Batch generation initiated for {len(results)} jobs")
        
        return {
            "status": "success",
            "processed_count": len(results),
            "failed_count": len(failed_jobs),
            "results": results,
            "failed_jobs": failed_jobs
        }
        
    except Exception as exc:
        logger.error(f"Batch generation failed: {exc}")
        raise exc


# Helper functions
def _generate_asset_for_format(asset, format_obj, job_id: UUID, generation_service: GenerationService, config_manager: ConfigManager = None, provider: str = None) -> GeneratedAsset:
    """Generate asset for a specific format"""
    try:
        # Get admin configurations
        if config_manager:
            adaptation_strategy = config_manager.get_adaptation_strategy()
            image_quality = config_manager.get_image_quality()
        else:
            adaptation_strategy = "smart"
            image_quality = "high"
        
        # Create adaptation strategy based on format and admin config
        strategy = AdaptationStrategy(
            target_width=format_obj.width,
            target_height=format_obj.height,
            crop_strategy=adaptation_strategy,
            quality=image_quality,
            format="jpeg"
        )
        
        # Apply AI-powered adaptation
        adapted_path = asyncio.run(ai_manager.apply_adaptation(
            asset.storage_path, strategy, provider=provider
        ))
        
        # Create generated asset record
        generated_asset = GeneratedAsset(
            job_id=job_id,
            original_asset_id=asset.id,
            asset_format_id=format_obj.id,
            storage_path=adapted_path,
            file_type="jpeg",
            dimensions={"width": format_obj.width, "height": format_obj.height},
            is_nsfw=False,
            manual_edits={}
        )
        
        # Save to database
        db = next(get_db())
        try:
            db.add(generated_asset)
            db.commit()
            db.refresh(generated_asset)
            return generated_asset
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Failed to generate asset for format: {e}")
        raise e


def _generate_asset_for_custom_size(asset, custom_size: Dict[str, int], job_id: UUID, generation_service: GenerationService, provider: str = None) -> GeneratedAsset:
    """Generate asset for custom dimensions"""
    try:
        # Create adaptation strategy for custom size
        strategy = AdaptationStrategy(
            target_width=custom_size["width"],
            target_height=custom_size["height"],
            crop_strategy="smart",
            quality="high",
            format="jpeg"
        )
        
        # Apply AI-powered adaptation
        adapted_path = asyncio.run(ai_manager.apply_adaptation(
            asset.storage_path, strategy, provider=provider
        ))
        
        # Create generated asset record
        generated_asset = GeneratedAsset(
            job_id=job_id,
            original_asset_id=asset.id,
            asset_format_id=None,  # Custom size, no format
            storage_path=adapted_path,
            file_type="jpeg",
            dimensions=custom_size,
            is_nsfw=False,
            manual_edits={}
        )
        
        # Save to database
        db = next(get_db())
        try:
            db.add(generated_asset)
            db.commit()
            db.refresh(generated_asset)
            return generated_asset
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Failed to generate asset for custom size: {e}")
        raise e


def _apply_image_edits(image_path: str, edit_operations: Dict[str, Any], output_format: str, quality: str) -> str:
    """Apply manual edits to an image"""
    try:
        from PIL import Image, ImageEnhance, ImageDraw, ImageFont
        import os
        
        # Open the image
        with Image.open(image_path) as img:
            # Convert to RGB if necessary
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Apply crop if specified
            if "crop" in edit_operations:
                crop_data = edit_operations["crop"]
                left = int(crop_data["x"] * img.width)
                top = int(crop_data["y"] * img.height)
                right = left + int(crop_data["width"] * img.width)
                bottom = top + int(crop_data["height"] * img.height)
                img = img.crop((left, top, right, bottom))
            
            # Apply saturation adjustment
            if "saturation" in edit_operations:
                saturation_factor = edit_operations["saturation"]
                enhancer = ImageEnhance.Color(img)
                img = enhancer.enhance(saturation_factor)
            
            # Apply text overlays
            if "textOverlays" in edit_operations:
                draw = ImageDraw.Draw(img)
                for text_overlay in edit_operations["textOverlays"]:
                    try:
                        # Use default font for now
                        font = ImageFont.load_default()
                        position = (
                            int(text_overlay["position"]["x"] * img.width),
                            int(text_overlay["position"]["y"] * img.height)
                        )
                        draw.text(position, text_overlay["content"], fill="white", font=font)
                    except Exception as e:
                        logger.warning(f"Failed to apply text overlay: {e}")
            
            # Apply logo overlay
            if "logoOverlay" in edit_operations:
                try:
                    logo_data = edit_operations["logoOverlay"]
                    # This would require loading the logo image and compositing it
                    # For now, just log the operation
                    logger.info(f"Logo overlay requested: {logo_data}")
                except Exception as e:
                    logger.warning(f"Failed to apply logo overlay: {e}")
            
            # Generate output path
            input_path = Path(image_path)
            output_filename = f"{input_path.stem}_edited.{output_format}"
            output_path = input_path.parent / output_filename
            
            # Save with appropriate quality
            quality_map = {"high": 95, "medium": 85, "low": 75}
            save_quality = quality_map.get(quality, 85)
            
            if output_format.lower() in ['jpg', 'jpeg']:
                img.save(output_path, 'JPEG', quality=save_quality, optimize=True)
            else:
                img.save(output_path, output_format.upper())
            
            return str(output_path)
        
    except Exception as e:
        logger.error(f"Failed to apply image edits: {e}")
        raise e


def _convert_image_format(image_path: str, target_format: str, quality: str) -> str:
    """Convert image to different format"""
    try:
        from PIL import Image
        
        with Image.open(image_path) as img:
            # Convert to RGB if targeting JPEG
            if target_format.lower() in ['jpg', 'jpeg'] and img.mode != 'RGB':
                img = img.convert('RGB')
            
            # Generate output path
            input_path = Path(image_path)
            output_filename = f"{input_path.stem}.{target_format}"
            output_path = input_path.parent / output_filename
            
            # Save with appropriate quality
            quality_map = {"high": 95, "medium": 85, "low": 75}
            save_quality = quality_map.get(quality, 85)
            
            if target_format.lower() in ['jpg', 'jpeg']:
                img.save(output_path, 'JPEG', quality=save_quality, optimize=True)
            elif target_format.lower() == 'png':
                img.save(output_path, 'PNG', optimize=True)
            elif target_format.lower() == 'webp':
                img.save(output_path, 'WEBP', quality=save_quality, optimize=True)
            else:
                img.save(output_path, target_format.upper())
            
            return str(output_path)
        
    except Exception as e:
        logger.error(f"Failed to convert image format: {e}")
        raise e


# Health check task
@celery_app.task(name="app.workers.generation.health_check")
def health_check() -> Dict[str, Any]:
    """Health check task for monitoring"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "worker_type": "generation"
    }