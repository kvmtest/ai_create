"""
Celery workers for content moderation, NSFW detection, and security scanning
"""
import asyncio
import logging
import time
import hashlib
from typing import Dict, Any, List, Optional
from uuid import UUID
from pathlib import Path
from celery import Task
from celery.exceptions import Retry, MaxRetriesExceededError
from sqlalchemy.orm import Session

from app.workers.celery_app import celery_app
from app.db.session import get_db
from app.services.asset import AssetService
from app.services.admin import AdminService
from app.services.ai_providers import ai_manager, AIProviderError
from app.services.ai_providers.base import ModerationCategory
from app.models.asset import Asset
from app.models.enums import AssetStatus
from app.workers.queue_config import (
    ContentModerationMessage, TaskPriority, QueueName
)

logger = logging.getLogger(__name__)


class BaseModerationTask(Task):
    """Base task class with common functionality for moderation tasks"""
    
    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure"""
        logger.error(f"Moderation task {task_id} failed: {exc}")
        
        # Update asset status if asset_id is provided
        if 'asset_id' in kwargs:
            try:
                db = next(get_db())
                asset_service = AssetService(db)
                asset_service.update_asset_status(UUID(kwargs['asset_id']), AssetStatus.FAILED)
                db.close()
            except Exception as e:
                logger.error(f"Failed to update asset status: {e}")
    
    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Handle task retry"""
        logger.warning(f"Moderation task {task_id} retrying: {exc}")
    
    def on_success(self, retval, task_id, args, kwargs):
        """Handle task success"""
        logger.info(f"Moderation task {task_id} completed successfully")


@celery_app.task(bind=True, base=BaseModerationTask, name="app.workers.moderation.moderate_content")
def moderate_content(self, asset_id: str, file_path: str, moderation_rules: Dict[str, Any], ai_provider: Optional[str] = None) -> Dict[str, Any]:
    """
    Perform comprehensive content moderation on an asset
    
    Args:
        asset_id: UUID of the asset
        file_path: Path to the asset file
        moderation_rules: Moderation rules and settings
        ai_provider: Specific AI provider to use (optional)
        
    Returns:
        Dict with moderation results
    """
    try:
        logger.info(f"Starting content moderation for asset {asset_id}")
        
        # Get database session
        db = next(get_db())
        asset_service = AssetService(db)
        
        try:
            # Update asset status to moderating
            asset_service.update_asset_status(UUID(asset_id), AssetStatus.PROCESSING)
            
            # Perform AI-based content moderation
            moderation_result = asyncio.run(ai_manager.moderate_content(file_path, ai_provider))
            
            # Perform additional security checks
            security_scan_result = _perform_security_scan(file_path)
            
            # Apply moderation rules
            final_decision = _apply_moderation_rules(
                moderation_result, security_scan_result, moderation_rules
            )
            
            # Update asset with moderation results
            moderation_metadata = {
                "ai_moderation": {
                    "category": moderation_result.category,
                    "confidence": moderation_result.confidence,
                    "flagged": moderation_result.flagged,
                    "categories": moderation_result.categories,
                    "reason": moderation_result.reason,
                    "provider": ai_provider or "auto"
                },
                "security_scan": security_scan_result,
                "final_decision": final_decision,
                "moderated_at": time.time(),
                "moderation_rules_applied": moderation_rules
            }
            
            asset_service.update_asset_metadata(UUID(asset_id), {
                "moderation": moderation_metadata
            })
            
            # Update asset status based on moderation result
            if final_decision["action"] == "block":
                asset_service.update_asset_status(UUID(asset_id), AssetStatus.FAILED)
            elif final_decision["action"] == "flag":
                asset_service.update_asset_status(UUID(asset_id), AssetStatus.FAILED)
            else:
                asset_service.update_asset_status(UUID(asset_id), AssetStatus.READY_FOR_GENERATION)
            
            logger.info(f"Content moderation completed for asset {asset_id}")
            
            return {
                "status": "success",
                "asset_id": asset_id,
                "moderation_result": final_decision,
                "ai_confidence": moderation_result.confidence
            }
            
        finally:
            db.close()
            
    except AIProviderError as exc:
        logger.error(f"AI moderation failed for asset {asset_id}: {exc}")
        
        # Retry with different provider if available
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=30 * (2 ** self.request.retries),
                max_retries=2
            )
        else:
            # Mark asset as failed
            try:
                db = next(get_db())
                asset_service = AssetService(db)
                asset_service.update_asset_status(UUID(asset_id), AssetStatus.FAILED)
                db.close()
            except:
                pass
            
            raise MaxRetriesExceededError(f"Content moderation failed after {self.max_retries} retries: {exc}")
    
    except Exception as exc:
        logger.error(f"Unexpected error in content moderation: {exc}")
        raise exc


@celery_app.task(bind=True, base=BaseModerationTask, name="app.workers.moderation.scan_for_malware")
def scan_for_malware(self, file_path: str, asset_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Scan file for malware and security threats
    
    Args:
        file_path: Path to the file to scan
        asset_id: Optional asset ID for status updates
        
    Returns:
        Dict with scan results
    """
    try:
        logger.info(f"Starting malware scan for file {file_path}")
        
        # Perform file hash check against known malware signatures
        file_hash = _calculate_file_hash(file_path)
        hash_check_result = _check_malware_hash(file_hash)
        
        # Perform file structure analysis
        structure_analysis = _analyze_file_structure(file_path)
        
        # Check for embedded executables or scripts
        embedded_content_check = _check_embedded_content(file_path)
        
        # Combine results
        scan_result = {
            "file_hash": file_hash,
            "hash_check": hash_check_result,
            "structure_analysis": structure_analysis,
            "embedded_content": embedded_content_check,
            "scan_timestamp": time.time(),
            "threat_detected": (
                hash_check_result.get("threat_detected", False) or
                structure_analysis.get("suspicious", False) or
                embedded_content_check.get("threat_detected", False)
            )
        }
        
        # Update asset if asset_id provided
        if asset_id:
            db = next(get_db())
            try:
                asset_service = AssetService(db)
                asset_service.update_asset_metadata(UUID(asset_id), {
                    "security_scan": scan_result
                })
                
                # Flag asset if threat detected
                if scan_result["threat_detected"]:
                    asset_service.update_asset_status(UUID(asset_id), AssetStatus.FAILED)
                    
            finally:
                db.close()
        
        logger.info(f"Malware scan completed for file {file_path}")
        
        return {
            "status": "success",
            "file_path": file_path,
            "scan_result": scan_result
        }
        
    except Exception as exc:
        logger.error(f"Malware scan failed: {exc}")
        raise exc


@celery_app.task(bind=True, base=BaseModerationTask, name="app.workers.moderation.batch_moderate")
def batch_moderate(self, asset_ids: List[str], moderation_rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform batch content moderation on multiple assets
    
    Args:
        asset_ids: List of asset IDs to moderate
        moderation_rules: Moderation rules to apply
        
    Returns:
        Dict with batch moderation results
    """
    try:
        logger.info(f"Starting batch moderation for {len(asset_ids)} assets")
        
        results = []
        failed_assets = []
        
        for asset_id in asset_ids:
            try:
                # Get asset file path from database
                db = next(get_db())
                asset_service = AssetService(db)
                asset = asset_service.get_asset(UUID(asset_id))
                db.close()
                
                if not asset:
                    failed_assets.append(asset_id)
                    continue
                
                # Schedule moderation task
                result = moderate_content.apply_async(
                    kwargs={
                        "asset_id": asset_id,
                        "file_path": asset.file_path,
                        "moderation_rules": moderation_rules
                    },
                    queue=QueueName.MODERATION,
                    priority=TaskPriority.HIGH
                )
                
                results.append({"asset_id": asset_id, "task_id": result.id})
                
            except Exception as e:
                logger.error(f"Failed to schedule moderation for asset {asset_id}: {e}")
                failed_assets.append(asset_id)
        
        logger.info(f"Batch moderation scheduled for {len(results)} assets")
        
        return {
            "status": "success",
            "scheduled_count": len(results),
            "failed_count": len(failed_assets),
            "results": results,
            "failed_assets": failed_assets
        }
        
    except Exception as exc:
        logger.error(f"Batch moderation failed: {exc}")
        raise exc


@celery_app.task(bind=True, base=BaseModerationTask, name="app.workers.moderation.update_moderation_rules")
def update_moderation_rules(self, new_rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Update moderation rules and re-evaluate flagged content
    
    Args:
        new_rules: New moderation rules to apply
        
    Returns:
        Dict with update results
    """
    try:
        logger.info("Updating moderation rules and re-evaluating content")
        
        # Get all flagged assets
        db = next(get_db())
        asset_service = AssetService(db)
        
        try:
            flagged_assets = db.query(Asset).filter(Asset.status == AssetStatus.FAILED).all()
            
            re_evaluated = []
            for asset in flagged_assets:
                try:
                    # Re-evaluate with new rules
                    if asset.ai_metadata and "moderation" in asset.ai_metadata:
                        old_moderation = asset.ai_metadata["moderation"]
                        
                        # Apply new rules to existing moderation data
                        new_decision = _apply_moderation_rules(
                            type('MockResult', (), {
                                'category': old_moderation["ai_moderation"]["category"],
                                'confidence': old_moderation["ai_moderation"]["confidence"],
                                'flagged': old_moderation["ai_moderation"]["flagged"],
                                'categories': old_moderation["ai_moderation"]["categories"]
                            })(),
                            old_moderation.get("security_scan", {}),
                            new_rules
                        )
                        
                        # Update asset status if decision changed
                        if new_decision["action"] != old_moderation["final_decision"]["action"]:
                            if new_decision["action"] == "allow":
                                asset_service.update_asset_status(asset.id, AssetStatus.READY_FOR_GENERATION)
                            else:
                                asset_service.update_asset_status(asset.id, AssetStatus.FAILED)
                            
                            re_evaluated.append(str(asset.id))
                
                except Exception as e:
                    logger.error(f"Failed to re-evaluate asset {asset.id}: {e}")
            
            logger.info(f"Moderation rules updated, re-evaluated {len(re_evaluated)} assets")
            
            return {
                "status": "success",
                "rules_updated": True,
                "re_evaluated_count": len(re_evaluated),
                "re_evaluated_assets": re_evaluated
            }
            
        finally:
            db.close()
            
    except Exception as exc:
        logger.error(f"Moderation rules update failed: {exc}")
        raise exc


# Helper functions
def _perform_security_scan(file_path: str) -> Dict[str, Any]:
    """Perform comprehensive security scan on file"""
    try:
        # File hash check
        file_hash = _calculate_file_hash(file_path)
        
        # File size check
        file_size = Path(file_path).stat().st_size
        
        # File type verification
        import magic
        actual_mime_type = magic.from_file(file_path, mime=True)
        
        # Basic structure analysis
        structure_check = _analyze_file_structure(file_path)
        
        return {
            "file_hash": file_hash,
            "file_size": file_size,
            "mime_type": actual_mime_type,
            "structure_analysis": structure_check,
            "scan_timestamp": time.time(),
            "threats_detected": structure_check.get("suspicious", False)
        }
        
    except Exception as e:
        logger.error(f"Security scan failed: {e}")
        return {
            "error": str(e),
            "scan_timestamp": time.time(),
            "threats_detected": False
        }


def _calculate_file_hash(file_path: str) -> str:
    """Calculate SHA-256 hash of file"""
    try:
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()
    except Exception as e:
        logger.error(f"Failed to calculate file hash: {e}")
        return ""


def _check_malware_hash(file_hash: str) -> Dict[str, Any]:
    """Check file hash against malware databases"""
    # This would integrate with actual malware detection services
    # For now, return a mock result
    return {
        "hash": file_hash,
        "threat_detected": False,
        "threat_type": None,
        "confidence": 0.0,
        "database_version": "mock_v1.0"
    }


def _analyze_file_structure(file_path: str) -> Dict[str, Any]:
    """Analyze file structure for suspicious content"""
    try:
        file_size = Path(file_path).stat().st_size
        
        # Check for unusually large files
        max_size = 100 * 1024 * 1024  # 100MB
        size_suspicious = file_size > max_size
        
        # Check file extension vs content
        import magic
        actual_mime = magic.from_file(file_path, mime=True)
        expected_mime = _get_expected_mime_type(file_path)
        mime_mismatch = actual_mime != expected_mime
        
        return {
            "file_size": file_size,
            "size_suspicious": size_suspicious,
            "actual_mime_type": actual_mime,
            "expected_mime_type": expected_mime,
            "mime_mismatch": mime_mismatch,
            "suspicious": size_suspicious or mime_mismatch
        }
        
    except Exception as e:
        logger.error(f"File structure analysis failed: {e}")
        return {
            "error": str(e),
            "suspicious": True  # Err on the side of caution
        }


def _check_embedded_content(file_path: str) -> Dict[str, Any]:
    """Check for embedded executables or scripts in image files"""
    try:
        # Read file in binary mode and look for suspicious patterns
        with open(file_path, 'rb') as f:
            content = f.read(1024 * 1024)  # Read first 1MB
        
        # Look for executable signatures
        executable_signatures = [
            b'MZ',  # Windows PE
            b'\x7fELF',  # Linux ELF
            b'\xfe\xed\xfa',  # macOS Mach-O
            b'<script',  # JavaScript
            b'<?php',  # PHP
        ]
        
        threats_found = []
        for signature in executable_signatures:
            if signature in content:
                threats_found.append(signature.decode('utf-8', errors='ignore'))
        
        return {
            "threats_detected": len(threats_found) > 0,
            "threat_signatures": threats_found,
            "scan_method": "signature_detection"
        }
        
    except Exception as e:
        logger.error(f"Embedded content check failed: {e}")
        return {
            "threats_detected": False,
            "error": str(e)
        }


def _get_expected_mime_type(file_path: str) -> str:
    """Get expected MIME type based on file extension"""
    extension = Path(file_path).suffix.lower()
    mime_map = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.psd': 'image/vnd.adobe.photoshop',
        '.tiff': 'image/tiff',
        '.bmp': 'image/bmp'
    }
    return mime_map.get(extension, 'application/octet-stream')


def _apply_moderation_rules(moderation_result, security_scan_result: Dict[str, Any], rules: Dict[str, Any]) -> Dict[str, Any]:
    """Apply moderation rules to determine final action"""
    try:
        # Get rule settings
        nsfw_alerts_active = rules.get("nsfwAlertsActive", True)
        allowed_categories = rules.get("allowedCategories", ["safe"])
        confidence_threshold = rules.get("confidenceThreshold", 0.7)
        
        # Check security threats
        if security_scan_result.get("threats_detected", False):
            return {
                "action": "block",
                "reason": "Security threat detected",
                "confidence": 1.0,
                "rule_applied": "security_scan"
            }
        
        # Check AI moderation results
        if nsfw_alerts_active and moderation_result.flagged:
            if moderation_result.confidence >= confidence_threshold:
                if moderation_result.category not in allowed_categories:
                    return {
                        "action": "block",
                        "reason": f"Content flagged as {moderation_result.category}",
                        "confidence": moderation_result.confidence,
                        "rule_applied": "ai_moderation"
                    }
                else:
                    return {
                        "action": "flag",
                        "reason": f"Content flagged for review: {moderation_result.category}",
                        "confidence": moderation_result.confidence,
                        "rule_applied": "ai_moderation_review"
                    }
        
        # Default to allow
        return {
            "action": "allow",
            "reason": "Content passed all moderation checks",
            "confidence": moderation_result.confidence,
            "rule_applied": "default_allow"
        }
        
    except Exception as e:
        logger.error(f"Failed to apply moderation rules: {e}")
        # Err on the side of caution
        return {
            "action": "flag",
            "reason": f"Rule application failed: {e}",
            "confidence": 0.0,
            "rule_applied": "error_fallback"
        }


# Health check task
@celery_app.task(name="app.workers.moderation.health_check")
def health_check() -> Dict[str, Any]:
    """Health check task for monitoring"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "worker_type": "moderation"
    }