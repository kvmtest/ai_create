"""
Configuration manager for integrating admin settings with processing workflows
"""
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.services.admin import AdminService
import structlog

logger = structlog.get_logger()


class ConfigManager:
    """Manages admin configurations for processing workflows"""
    
    def __init__(self, db: Session):
        self.db = db
        self.admin_service = AdminService(db)
        self._cache = {}
    
    def get_adaptation_config(self) -> Dict[str, Any]:
        """Get image adaptation configuration"""
        logger.info("get_adaptation_config called")
        if "adaptation_rules" not in self._cache:
            logger.info("config cache miss", key="adaptation_rules")
            self._cache["adaptation_rules"] = self.admin_service.get_adaptation_rules()
        return self._cache["adaptation_rules"]
    
    def get_ai_behavior_config(self) -> Dict[str, Any]:
        """Get AI behavior configuration"""
        logger.info("get_ai_behavior_config called")
        if "ai_behavior_rules" not in self._cache:
            logger.info("config cache miss", key="ai_behavior_rules")
            self._cache["ai_behavior_rules"] = self.admin_service.get_ai_behavior_rules()
        return self._cache["ai_behavior_rules"]
    
    def get_moderation_config(self) -> Dict[str, Any]:
        """Get upload and moderation configuration"""
        logger.info("get_moderation_config called")
        if "upload_moderation_rules" not in self._cache:
            logger.info("config cache miss", key="upload_moderation_rules")
            self._cache["upload_moderation_rules"] = self.admin_service.get_upload_moderation_rules()
        return self._cache["upload_moderation_rules"]
    
    def get_manual_edit_config(self) -> Dict[str, Any]:
        """Get manual editing configuration"""
        logger.info("get_manual_edit_config called")
        if "manual_editing_rules" not in self._cache:
            logger.info("config cache miss", key="manual_editing_rules")
            self._cache["manual_editing_rules"] = self.admin_service.get_manual_editing_rules()
        return self._cache["manual_editing_rules"]
    
    def get_active_formats(self) -> list:
        """Get active asset formats"""
        logger.info("get_active_formats called")
        if "active_formats" not in self._cache:
            logger.info("config cache miss", key="active_formats")
            self._cache["active_formats"] = self.admin_service.get_formats()
        return self._cache["active_formats"]
    
    def get_active_text_styles(self) -> list:
        """Get active text style sets"""
        if "active_text_styles" not in self._cache:
            self._cache["active_text_styles"] = self.admin_service.get_text_style_sets()
        return self._cache["active_text_styles"]
    
    def refresh_cache(self):
        """Clear cache to force reload of configurations"""
        self._cache.clear()
    
    def is_file_type_allowed(self, file_type: str) -> bool:
        """Check if file type is allowed for upload"""
        config = self.get_moderation_config()
        allowed_types = config.get("allowedImageTypes", ["jpeg", "png"])
        return file_type.lower() in [t.lower() for t in allowed_types]
    
    def get_max_file_size_mb(self) -> int:
        """Get maximum allowed file size in MB"""
        config = self.get_moderation_config()
        return config.get("maxFileSizeMb", 50)
    
    def is_nsfw_detection_enabled(self) -> bool:
        """Check if NSFW detection is enabled"""
        config = self.get_moderation_config()
        return config.get("nsfwAlertsActive", True)
    
    def get_adaptation_strategy(self) -> str:
        """Get default adaptation strategy"""
        config = self.get_ai_behavior_config()
        return config.get("adaptationStrategy", "crop")
    
    def get_image_quality(self) -> str:
        """Get default image quality setting"""
        config = self.get_ai_behavior_config()
        return config.get("imageQuality", "high")
    
    def get_focal_point_logic(self) -> str:
        """Get focal point detection logic"""
        config = self.get_adaptation_config()
        return config.get("focalPointLogic", "face-centric")
    
    def get_safe_zone_config(self) -> Dict[str, float]:
        """Get safe zone configuration for layouts"""
        config = self.get_adaptation_config()
        layout = config.get("layoutGuidance", {})
        return layout.get("safeZone", {
            "top": 0.1, "bottom": 0.1, "left": 0.1, "right": 0.1
        })
    
    def get_logo_size_config(self) -> float:
        """Get default logo size configuration"""
        config = self.get_adaptation_config()
        layout = config.get("layoutGuidance", {})
        return layout.get("logoSize", 0.15)
    
    def is_manual_editing_enabled(self) -> bool:
        """Check if manual editing is enabled"""
        config = self.get_manual_edit_config()
        return config.get("editingEnabled", True)
    
    def is_cropping_enabled(self) -> bool:
        """Check if cropping is enabled"""
        config = self.get_manual_edit_config()
        return config.get("croppingEnabled", True)
    
    def is_saturation_enabled(self) -> bool:
        """Check if saturation adjustment is enabled"""
        config = self.get_manual_edit_config()
        return config.get("saturationEnabled", True)
    
    def is_text_logo_enabled(self) -> bool:
        """Check if text/logo overlay is enabled"""
        config = self.get_manual_edit_config()
        return config.get("addTextOrLogoEnabled", True)
    
    def get_allowed_logo_types(self) -> list:
        """Get allowed logo file types"""
        config = self.get_manual_edit_config()
        logo_config = config.get("allowedLogoSources", {})
        return logo_config.get("types", ["jpeg", "png", "psd", "ai"])
    
    def get_max_logo_size_mb(self) -> int:
        """Get maximum logo file size in MB"""
        config = self.get_manual_edit_config()
        logo_config = config.get("allowedLogoSources", {})
        return logo_config.get("maxSizeMb", 10)