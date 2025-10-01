"""
Celery workers for asset processing, analysis, and metadata extraction
"""
import asyncio
import logging
import time
from typing import Dict, Any, Optional
from uuid import UUID
from pathlib import Path
from celery import Task
from celery.exceptions import Retry, MaxRetriesExceededError
from sqlalchemy.orm import Session
import structlog

from app.workers.celery_app import celery_app
from app.db.session import get_db
from app.services.asset import AssetService
from app.services.project import ProjectService
from app.services.config_manager import ConfigManager
from app.services.ai_providers import ai_manager, AIProviderError
from app.models.asset import Asset
from app.models.project import Project
from app.models.enums import AssetStatus, ProjectStatus
from app.workers.queue_config import (
    AssetUploadMessage, AssetAnalysisMessage, BatchProcessingMessage,
    TaskPriority, QueueName
)

logger = structlog.get_logger()


class BaseAssetTask(Task):
    """Base task class with common functionality for asset processing"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        logger.error("Task failed", task_id=task_id, error=str(exc))
        
        # Update project status to failed if project_id is provided
        if 'project_id' in kwargs:
            try:
                db = next(get_db())
                project_service = ProjectService(db)
                project = project_service.get_project_by_id(kwargs['project_id'], kwargs.get('user_id'))
                if project:
                    project_service.update_project_status(project, ProjectStatus.FAILED)
                db.close()
            except Exception as e:
                logger.error("Failed to update project status", error=str(e))
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry"""
        logger.warning("Task retrying", task_id=task_id, error=str(exc))
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success"""
        logger.info("Task completed successfully", task_id=task_id)


@celery_app.task(bind=True, base=BaseAssetTask, name="app.workers.asset_processing.process_upload")
def process_upload(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process uploaded asset file and extract basic metadata
    
    Args:
        message_data: AssetUploadMessage data
        
    Returns:
        Dict with processing results
    """
    try:
        # Parse message
        message = AssetUploadMessage(**message_data)
        logger.info(
            "Starting upload processing",
            asset_id=str(message.asset_id),
            user_id=str(message.user_id),
            project_id=str(message.project_id),
            filename=message.original_filename,
            file_size_bytes=message.file_size,
            priority=message.priority
        )
        
        # Get database session
        db = next(get_db())
        asset_service = AssetService(db)
        
        try:
            # Update project status to processing if not already
            project_service = ProjectService(db)
            asset = asset_service.get_asset_worker(message.asset_id)
            project = project_service.get_project_by_id(asset.project_id, message.user_id)
            
            if project and project.status == ProjectStatus.UPLOADING:
                project_service.update_project_status(project, ProjectStatus.PROCESSING)
            
            # Extract file metadata
            file_metadata = _extract_file_metadata(message.file_path)
            
            # Apply admin configurations for validation
            config_manager = ConfigManager(db)
            
            # Check file type against admin rules
            file_ext = Path(message.file_path).suffix.lower().lstrip('.')
            if not config_manager.is_file_type_allowed(file_ext):
                raise ValueError(f"File type '{file_ext}' not allowed by admin configuration")
            
            # Check file size against admin rules
            file_size_mb = Path(message.file_path).stat().st_size / (1024 * 1024)
            max_size = config_manager.get_max_file_size_mb()
            if file_size_mb > max_size:
                raise ValueError(f"File size {file_size_mb:.1f}MB exceeds limit of {max_size}MB")
            
            # Validate file integrity
            if not _validate_file_integrity(message.file_path, message.mime_type):
                raise ValueError("File integrity validation failed")
            
            # Update asset with AI analysis metadata
            asset_service.update_ai_analysis_worker(message.asset_id, {
                "file_metadata": file_metadata,
                "processing_started_at": time.time(),
                "file_validated": True
            })
            
            # Schedule AI analysis with configured provider
            ai_task = analyze_asset.apply_async(
                kwargs={
                    "asset_id": str(message.asset_id),
                    "file_path": message.file_path,
                    "analysis_type": "full",
                    "ai_provider": message.ai_provider  # Use configured provider or let manager choose
                },
                queue=QueueName.ASSET_PROCESSING,
                priority=message.priority
            )
            
            logger.info(
                "Upload processing completed - AI analysis scheduled",
                asset_id=str(message.asset_id),
                ai_task_id=ai_task.id,
                file_size_mb=round(file_metadata.get("file_size", 0) / (1024 * 1024), 2),
                dimensions=file_metadata.get("width", "unknown")
            )
            
            return {
                "status": "success",
                "asset_id": str(message.asset_id),
                "metadata": file_metadata,
                "ai_task_id": ai_task.id
            }
            
        finally:
            db.close()
            
    except Exception as exc:
        logger.error(
            "Upload processing failed",
            asset_id=message_data.get("asset_id", "unknown"),
            user_id=message_data.get("user_id", "unknown"),
            error=str(exc),
            error_type=type(exc).__name__,
            retry_count=self.request.retries
        )
        
        # Retry with exponential backoff
        if self.request.retries < self.max_retries:
            retry_delay = 60 * (2 ** self.request.retries)
            logger.info(
                "Retrying upload processing",
                asset_id=message_data.get("asset_id", "unknown"),
                retry_count=self.request.retries + 1,
                retry_delay_seconds=retry_delay
            )
            raise self.retry(
                exc=exc,
                countdown=retry_delay,
                max_retries=3
            )
        else:
            # Mark project as failed
            try:
                db = next(get_db())
                asset_service = AssetService(db)
                project_service = ProjectService(db)
                asset = asset_service.get_asset_worker(message_data["asset_id"])
                project = project_service.get_project_by_id(asset.project_id, message_data["user_id"])
                if project:
                    project_service.update_project_status(project, ProjectStatus.FAILED)
                    logger.error(
                        "Project marked as failed due to upload processing failure",
                        project_id=str(project.id),
                        asset_id=message_data.get("asset_id", "unknown")
                    )
                db.close()
            except Exception as db_exc:
                logger.error(
                    "Failed to mark project as failed",
                    asset_id=message_data.get("asset_id", "unknown"),
                    db_error=str(db_exc)
                )
            
            raise MaxRetriesExceededError(f"Upload processing failed after {self.max_retries} retries: {exc}")


@celery_app.task(bind=True, base=BaseAssetTask, name="app.workers.asset_processing.analyze_asset")
def analyze_asset(self, asset_id: str, file_path: str, analysis_type: str = "full", ai_provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Analyze asset using AI providers for element detection and metadata extraction
    
    Args:
        asset_id: UUID of the asset
        file_path: Path to the asset file
        analysis_type: Type of analysis (full, elements_only, moderation_only)
        ai_provider: Specific AI provider to use (optional)
        
    Returns:
        Dict with analysis results
    """
    try:
        logger.info(
            "Starting AI analysis",
            asset_id=asset_id,
            analysis_type=analysis_type,
            ai_provider=ai_provider,
            file_path=file_path
        )
        
        # Get database session
        db = next(get_db())
        asset_service = AssetService(db)
        
        try:
            # Get admin configurations
            config_manager = ConfigManager(db)
            logger.info("Admin configurations loaded", asset_id=asset_id)
            
            # Perform AI analysis with admin configurations
            start_time = time.time()
            analysis_result = asyncio.run(_perform_ai_analysis(
                file_path, analysis_type, ai_provider, config_manager
            ))
            analysis_duration = time.time() - start_time
            
            logger.info(
                "AI analysis completed successfully",
                asset_id=asset_id,
                provider=analysis_result.get("provider", "unknown"),
                analysis_duration=round(analysis_duration, 2),
                elements_detected=len(analysis_result.get("detected_elements", [])),
                moderation_flagged=analysis_result.get("moderation", {}).get("flagged", False)
            )
            
            # Update asset with AI metadata
            asset_service.update_ai_analysis_worker(UUID(asset_id), {
                "ai_analysis": analysis_result,
                "analysis_completed_at": time.time(),
                "analysis_provider": analysis_result.get("provider", "unknown"),
                "moderation_flagged": analysis_result.get("moderation", {}).get("flagged", False)
            })
            
            # Update project status if all assets are processed
            asset = asset_service.get_asset_worker(UUID(asset_id))
            if asset and asset.project_id:
                _update_project_status_if_complete(db, asset.project_id)
                logger.info("Project status check completed", asset_id=asset_id, project_id=str(asset.project_id))
            
            return {
                "status": "success",
                "asset_id": asset_id,
                "analysis": analysis_result
            }
            
        finally:
            db.close()
            
    except AIProviderError as exc:
        logger.error(
            "AI analysis failed - provider error",
            asset_id=asset_id,
            provider=ai_provider,
            error=str(exc),
            retry_count=self.request.retries,
            max_retries=self.max_retries
        )
        
        # Retry with different provider if available
        if self.request.retries < self.max_retries:
            retry_delay = 30 * (2 ** self.request.retries)
            logger.info(
                "Retrying AI analysis with different provider",
                asset_id=asset_id,
                retry_count=self.request.retries + 1,
                retry_delay_seconds=retry_delay
            )
            raise self.retry(
                exc=exc,
                countdown=retry_delay,
                max_retries=2
            )
        else:
            # Mark analysis as failed in metadata
            try:
                db = next(get_db())
                asset_service = AssetService(db)
                asset_service.update_ai_analysis_worker(UUID(asset_id), {
                    "analysis_failed": True,
                    "analysis_error": str(exc),
                    "analysis_failed_at": time.time()
                })
                logger.error(
                    "AI analysis permanently failed - max retries exceeded",
                    asset_id=asset_id,
                    final_error=str(exc),
                    total_retries=self.max_retries
                )
                db.close()
            except Exception as db_exc:
                logger.error(
                    "Failed to update asset with analysis failure",
                    asset_id=asset_id,
                    db_error=str(db_exc)
                )
            
            raise MaxRetriesExceededError(f"AI analysis failed after {self.max_retries} retries: {exc}")
    
    except Exception as exc:
        logger.error(
            "Unexpected error in asset analysis",
            asset_id=asset_id,
            error=str(exc),
            error_type=type(exc).__name__
        )
        raise exc


@celery_app.task(bind=True, base=BaseAssetTask, name="app.workers.asset_processing.batch_process")
def batch_process(self, message_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Process multiple assets in batch
    
    Args:
        message_data: BatchProcessingMessage data
        
    Returns:
        Dict with batch processing results
    """
    try:
        # Parse message
        message = BatchProcessingMessage(**message_data)
        logger.info(f"Starting batch processing for batch {message.batch_id}")
        
        results = []
        failed_assets = []
        
        for asset_id in message.asset_ids:
            try:
                if message.operation_type == "analysis":
                    result = analyze_asset.apply_async(
                        kwargs={
                            "asset_id": str(asset_id),
                            "file_path": f"uploads/{asset_id}",  # This should be retrieved from DB
                            "analysis_type": message.batch_settings.get("analysis_type", "full")
                        },
                        queue=QueueName.ASSET_PROCESSING
                    )
                    results.append({"asset_id": str(asset_id), "task_id": result.id})
                
                elif message.operation_type == "moderation":
                    # Schedule moderation task
                    from app.workers.moderation import moderate_content
                    result = moderate_content.apply_async(
                        kwargs={
                            "asset_id": str(asset_id),
                            "file_path": f"uploads/{asset_id}",
                            "moderation_rules": message.batch_settings.get("moderation_rules", {})
                        },
                        queue=QueueName.MODERATION
                    )
                    results.append({"asset_id": str(asset_id), "task_id": result.id})
                
            except Exception as e:
                logger.error(f"Failed to process asset {asset_id} in batch: {e}")
                failed_assets.append(str(asset_id))
        
        logger.info(f"Batch processing initiated for batch {message.batch_id}")
        
        return {
            "status": "success",
            "batch_id": str(message.batch_id),
            "processed_count": len(results),
            "failed_count": len(failed_assets),
            "results": results,
            "failed_assets": failed_assets
        }
        
    except Exception as exc:
        logger.error(f"Batch processing failed: {exc}")
        raise exc


@celery_app.task(bind=True, name="app.workers.asset_processing.cleanup_temp_files")
def cleanup_temp_files(self, older_than_hours: int = 24) -> Dict[str, Any]:
    """
    Clean up temporary files older than specified hours
    
    Args:
        older_than_hours: Remove files older than this many hours
        
    Returns:
        Dict with cleanup results
    """
    try:
        import os
        import time
        
        temp_dir = Path("uploads/temp")
        if not temp_dir.exists():
            return {"status": "success", "message": "No temp directory found"}
        
        current_time = time.time()
        cutoff_time = current_time - (older_than_hours * 3600)
        
        cleaned_files = []
        total_size = 0
        
        for file_path in temp_dir.rglob("*"):
            if file_path.is_file():
                file_mtime = file_path.stat().st_mtime
                if file_mtime < cutoff_time:
                    file_size = file_path.stat().st_size
                    total_size += file_size
                    cleaned_files.append(str(file_path))
                    file_path.unlink()
        
        logger.info(f"Cleaned up {len(cleaned_files)} files, freed {total_size} bytes")
        
        return {
            "status": "success",
            "files_cleaned": len(cleaned_files),
            "bytes_freed": total_size,
            "files": cleaned_files
        }
        
    except Exception as exc:
        logger.error(f"Cleanup failed: {exc}")
        raise exc


# Helper functions
def _extract_file_metadata(file_path: str) -> Dict[str, Any]:
    """Extract basic file metadata"""
    try:
        from PIL import Image
        import os
        
        file_stats = os.stat(file_path)
        metadata = {
            "file_size": file_stats.st_size,
            "created_at": file_stats.st_ctime,
            "modified_at": file_stats.st_mtime,
        }
        
        # Try to extract image metadata
        try:
            with Image.open(file_path) as img:
                metadata.update({
                    "width": img.width,
                    "height": img.height,
                    "format": img.format,
                    "mode": img.mode,
                    "has_transparency": img.mode in ("RGBA", "LA") or "transparency" in img.info
                })
                
                # Extract EXIF data if available
                if hasattr(img, '_getexif') and img._getexif():
                    exif_data = img._getexif()
                    metadata["exif"] = {k: v for k, v in exif_data.items() if isinstance(v, (str, int, float))}
        
        except Exception as e:
            logger.warning(f"Could not extract image metadata: {e}")
        
        return metadata
        
    except Exception as e:
        logger.error(f"Failed to extract file metadata: {e}")
        return {"error": str(e)}


def _validate_file_integrity(file_path: str, expected_mime_type: str) -> bool:
    """Validate file integrity and type"""
    try:
        import magic
        from PIL import Image
        
        # Check if file exists and is readable
        if not Path(file_path).exists():
            return False
        
        # Verify MIME type
        actual_mime_type = magic.from_file(file_path, mime=True)
        if not actual_mime_type.startswith(expected_mime_type.split('/')[0]):
            logger.warning(f"MIME type mismatch: expected {expected_mime_type}, got {actual_mime_type}")
            return False
        
        # Try to open image file to verify it's not corrupted
        if actual_mime_type.startswith('image/'):
            try:
                with Image.open(file_path) as img:
                    img.verify()
            except Exception as e:
                logger.error(f"Image verification failed: {e}")
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"File validation failed: {e}")
        return False


async def _perform_ai_analysis(file_path: str, analysis_type: str, ai_provider: Optional[str] = None, config_manager: Optional[ConfigManager] = None) -> Dict[str, Any]:
    """Perform AI analysis on the asset"""
    try:
        # Apply admin configurations if available
        skip_moderation = False
        if config_manager:
            skip_moderation = not config_manager.is_nsfw_detection_enabled()
            logger.info(
                "AI analysis configuration",
                file_path=file_path,
                analysis_type=analysis_type,
                provider=ai_provider,
                moderation_enabled=not skip_moderation
            )
        
        if analysis_type == "full":
            logger.info("Starting full AI analysis", file_path=file_path, provider=ai_provider)
            # Full analysis including elements and moderation
            analysis = await ai_manager.analyze_image(file_path, ai_provider)
            
            result = {
                "detected_elements": [elem.__dict__ for elem in analysis.detected_elements],
                "metadata": analysis.metadata,
                "processing_time": analysis.processing_time,
                "provider": analysis.provider
            }
            
            # Include moderation only if enabled in admin config
            if not skip_moderation:
                result["moderation"] = analysis.moderation.__dict__
                logger.info(
                    "Full analysis completed with moderation",
                    file_path=file_path,
                    provider=analysis.provider,
                    elements_count=len(analysis.detected_elements),
                    moderation_flagged=analysis.moderation.flagged,
                    processing_time=analysis.processing_time
                )
            else:
                result["moderation"] = {"flagged": False, "reason": "moderation_disabled"}
                logger.info(
                    "Full analysis completed without moderation",
                    file_path=file_path,
                    provider=analysis.provider,
                    elements_count=len(analysis.detected_elements),
                    processing_time=analysis.processing_time
                )
            
            return result
        
        elif analysis_type == "elements_only":
            logger.info("Starting elements-only AI analysis", file_path=file_path, provider=ai_provider)
            # Only element detection
            elements = await ai_manager.detect_elements(file_path, ai_provider)
            logger.info(
                "Elements-only analysis completed",
                file_path=file_path,
                provider=ai_provider or "auto",
                elements_count=len(elements)
            )
            return {
                "detected_elements": [elem.__dict__ for elem in elements],
                "provider": ai_provider or "auto"
            }
        
        elif analysis_type == "moderation_only":
            # Only content moderation if enabled
            if skip_moderation:
                logger.info("Moderation analysis skipped - disabled in config", file_path=file_path)
                return {
                    "moderation": {"flagged": False, "reason": "moderation_disabled"},
                    "provider": ai_provider or "auto"
                }
            
            logger.info("Starting moderation-only AI analysis", file_path=file_path, provider=ai_provider)
            moderation = await ai_manager.moderate_content(file_path, ai_provider)
            logger.info(
                "Moderation-only analysis completed",
                file_path=file_path,
                provider=ai_provider or "auto",
                flagged=moderation.flagged,
                category=moderation.category
            )
            return {
                "moderation": moderation.__dict__,
                "provider": ai_provider or "auto"
            }
        
        else:
            error_msg = f"Unknown analysis type: {analysis_type}"
            logger.error("Invalid analysis type", analysis_type=analysis_type, file_path=file_path)
            raise ValueError(error_msg)
            
    except Exception as e:
        logger.error(
            "AI analysis failed in helper function",
            file_path=file_path,
            analysis_type=analysis_type,
            provider=ai_provider,
            error=str(e),
            error_type=type(e).__name__
        )
        raise AIProviderError(f"AI analysis failed: {e}")


def _update_project_status_if_complete(db: Session, project_id: UUID):
    """Update project status if all assets are processed"""
    try:
        project_service = ProjectService(db)
        # Get project without user_id filter for worker use
        project = db.query(Project).filter(Project.id == project_id).first()
        
        if not project:
            return
        
        # Check if all assets have AI analysis completed
        asset_service = AssetService(db)
        project_assets = asset_service.get_assets_by_project_worker(project_id)
        
        if not project_assets:
            return
        
        # Check if all assets have AI analysis or failed
        all_processed = True
        any_failed = False
        
        for asset in project_assets:
            ai_metadata = asset.ai_metadata or {}
            
            # Asset is processed if it has analysis_completed_at or analysis_failed
            has_analysis = "analysis_completed_at" in ai_metadata
            has_failure = ai_metadata.get("analysis_failed", False)
            
            if not (has_analysis or has_failure):
                all_processed = False
                break
                
            if has_failure:
                any_failed = True
        
        # Update project status based on processing completion
        if all_processed:
            if any_failed:
                # If some assets failed but others succeeded, still mark as ready for review
                # Users can decide whether to proceed with successful assets
                project_service.update_project_status(project, ProjectStatus.READY_FOR_REVIEW)
            else:
                # All assets processed successfully
                project_service.update_project_status(project, ProjectStatus.READY_FOR_REVIEW)
        
    except Exception as e:
        logger.error(f"Failed to update project status: {e}")


# Health check task
@celery_app.task(name="app.workers.asset_processing.health_check")
def health_check() -> Dict[str, Any]:
    """Health check task for monitoring"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "worker_type": "asset_processing"
    }