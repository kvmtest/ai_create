"""
Admin service for managing platforms, formats, text styles, and application rules
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
import structlog

logger = structlog.get_logger()

from app.models.admin import Platform, AssetFormat, TextStyleSet, AppSetting
from app.models.enums import PlatformType
from app.schemas.admin import (
    PlatformCreate, PlatformUpdate,
    AssetFormatCreate, AssetFormatUpdate,
    TextStyleSetCreate, TextStyleSetUpdate,
    AppSettingCreate, AppSettingUpdate
)
from app.core.exceptions import NotFoundError, ValidationError


class AdminService:
    def __init__(self, db: Session):
        self.db = db

    # Platform Management
    def get_platforms(self) -> List[Platform]:
        logger.info("get_platforms called")
        """Get all repurposing platforms"""
        return self.db.query(Platform).filter(
            Platform.is_active == True
        ).order_by(Platform.name).all()

    def get_platform(self, platform_id: UUID) -> Platform:
        """Get a specific platform by ID"""
        logger.info("get_platform called", platform_id=str(platform_id))
        platform = self.db.query(Platform).filter(
            Platform.id == platform_id
        ).first()
        
        if not platform:
            logger.error("Platform not found", platform_id=str(platform_id))
            raise NotFoundError("Platform not found")
        
        logger.info("Platform retrieved", platform_id=str(platform_id))
        return platform

    def create_platform(self, platform_data: PlatformCreate, admin_id: UUID) -> Platform:
        """Create a new repurposing platform"""
        logger.info("create_platform called", platform_name=platform_data.name, admin_id=str(admin_id))
        # Check if platform name already exists
        existing = self.db.query(Platform).filter(
            Platform.name == platform_data.name
        ).first()
        
        if existing:
            logger.error("Platform name already exists", platform_name=platform_data.name)
            raise ValidationError("Platform name already exists")

        platform = Platform(
            name=platform_data.name,
            type=platform_data.type,
            is_active=platform_data.is_active,
            created_by_admin_id=admin_id
        )
        
        self.db.add(platform)
        self.db.commit()
        self.db.refresh(platform)
        
        logger.info("Platform created", platform_id=str(platform.id), platform_name=platform.name)
        return platform

    def update_platform(self, platform_id: UUID, platform_data: PlatformUpdate) -> Platform:
        """Update an existing platform"""
        logger.info("update_platform called", platform_id=str(platform_id))
        platform = self.get_platform(platform_id)
        
        # Check if new name conflicts with existing platforms
        if platform_data.name and platform_data.name != platform.name:
            existing = self.db.query(Platform).filter(
                and_(
                    Platform.name == platform_data.name,
                    Platform.id != platform_id
                )
            ).first()
            
            if existing:
                logger.error("Platform name already exists", platform_name=platform_data.name)
                raise ValidationError("Platform name already exists")

        # Update fields
        if platform_data.name is not None:
            platform.name = platform_data.name
        if platform_data.type is not None:
            platform.type = platform_data.type
        if platform_data.is_active is not None:
            platform.is_active = platform_data.is_active

        self.db.commit()
        self.db.refresh(platform)
        
        return platform

    def delete_platform(self, platform_id: UUID) -> bool:
        """Delete a platform (soft delete by setting is_active=False)"""
        logger.info("delete_platform called", platform_id=str(platform_id))
        platform = self.get_platform(platform_id)
        
        # Check if platform has associated formats
        format_count = self.db.query(AssetFormat).filter(
            AssetFormat.platform_id == platform_id
        ).count()
        
        if format_count > 0:
            # Soft delete - set is_active to False
            platform.is_active = False
            self.db.commit()
            logger.info("Platform soft-deleted", platform_id=str(platform_id), format_count=format_count)
        else:
            # Hard delete if no associated formats
            self.db.delete(platform)
            self.db.commit()
            logger.info("Platform hard-deleted", platform_id=str(platform_id), format_count=format_count)
        
        return True

    # Asset Format Management
    def get_formats(self, platform_type: Optional[PlatformType] = None, platform_name: Optional[str] = None) -> List[AssetFormat]:
        """Get asset formats with optional filtering"""
        logger.info("get_formats called", platform_type=str(platform_type) if platform_type else None, platform_name=platform_name)
        query = self.db.query(AssetFormat).join(Platform).filter(AssetFormat.is_active == True)
        
        if platform_type:
            query = query.filter(Platform.type == platform_type)
        
        if platform_name:
            query = query.filter(Platform.name == platform_name)
        
        return query.order_by(AssetFormat.name).all()

    def get_format(self, format_id: UUID) -> AssetFormat:
        """Get a specific format by ID"""
        logger.info("get_format called", format_id=str(format_id))
        format_obj = self.db.query(AssetFormat).filter(
            AssetFormat.id == format_id
        ).first()
        
        if not format_obj:
            logger.error("Asset format not found", format_id=str(format_id))
            raise NotFoundError("Asset format not found")
        
        logger.info("Format retrieved", format_id=str(format_id))
        return format_obj

    def create_format(self, format_data: AssetFormatCreate, admin_id: UUID) -> AssetFormat:
        """Create a new asset format"""
        logger.info("create_format called", format_name=format_data.name, platform_id=str(format_data.platform_id), admin_id=str(admin_id))
        # Validate platform_id (now required)
        platform = self.db.query(Platform).filter(
            Platform.id == format_data.platform_id
        ).first()
        if not platform:
            logger.error("Invalid platform_id", platform_id=str(format_data.platform_id))
            raise ValidationError("Invalid platform_id")

        asset_format = AssetFormat(
            name=format_data.name,
            platform_id=format_data.platform_id,
            width=format_data.width,
            height=format_data.height,
            is_active=format_data.is_active,
            created_by_admin_id=admin_id
        )
        
        self.db.add(asset_format)
        self.db.commit()
        self.db.refresh(asset_format)
        
        logger.info("Format created", format_id=str(asset_format.id), format_name=asset_format.name)
        return asset_format

    def update_format(self, format_id: UUID, format_data: AssetFormatUpdate) -> AssetFormat:
        """Update an existing asset format"""
        logger.info("update_format called", format_id=str(format_id))
        asset_format = self.get_format(format_id)
        
        # Validate platform_id if provided
        if format_data.platform_id:
            platform = self.db.query(Platform).filter(
                Platform.id == format_data.platform_id
            ).first()
            if not platform:
                logger.error("Invalid platform_id", platform_id=str(format_data.platform_id))
                raise ValidationError("Invalid platform_id")

        # Update fields
        if format_data.name is not None:
            asset_format.name = format_data.name
        if format_data.platform_id is not None:
            asset_format.platform_id = format_data.platform_id
        if format_data.width is not None:
            asset_format.width = format_data.width
        if format_data.height is not None:
            asset_format.height = format_data.height
        if format_data.is_active is not None:
            asset_format.is_active = format_data.is_active

        self.db.commit()
        self.db.refresh(asset_format)
        
        return asset_format

    def delete_format(self, format_id: UUID) -> bool:
        """Delete an asset format (soft delete)"""
        logger.info("delete_format called", format_id=str(format_id))
        asset_format = self.get_format(format_id)
        
        # Hard delete
        self.db.delete(asset_format)
        self.db.commit()
        
        logger.info("Format deleted", format_id=str(format_id))
        return True

    # Text Style Set Management
    def get_text_style_sets(self) -> List[TextStyleSet]:
        """Get all text style sets"""
        logger.info("get_text_style_sets called")
        results = self.db.query(TextStyleSet).filter(
            TextStyleSet.is_active == True
        ).order_by(TextStyleSet.name).all()
        return results

    def get_text_style_set(self, set_id: UUID) -> TextStyleSet:
        """Get a specific text style set by ID"""
        logger.info("get_text_style_set called", set_id=str(set_id))
        style_set = self.db.query(TextStyleSet).filter(
            TextStyleSet.id == set_id
        ).first()
        
        if not style_set:
            logger.error("Text style set not found", set_id=str(set_id))
            raise NotFoundError("Text style set not found")
        
        logger.info("Text style set retrieved", set_id=str(set_id))
        return style_set

    def create_text_style_set(self, style_data: TextStyleSetCreate, admin_id: UUID) -> TextStyleSet:
        """Create a new text style set"""
        logger.info("create_text_style_set called", set_name=style_data.name, admin_id=str(admin_id))
        # Validate style definitions
        self._validate_style_definitions(style_data.styles)
        
        text_style_set = TextStyleSet(
            name=style_data.name,
            styles=style_data.styles,
            is_active=style_data.is_active,
            created_by_admin_id=admin_id
        )
        
        self.db.add(text_style_set)
        self.db.commit()
        self.db.refresh(text_style_set)
        logger.info("Text style set created", set_id=str(text_style_set.id), set_name=text_style_set.name)
        return text_style_set

    def update_text_style_set(self, style_id: UUID, style_data: TextStyleSetUpdate) -> TextStyleSet:
        """Update an existing text style set"""
        logger.info("update_text_style_set called", set_id=str(style_id))
        text_style_set = self.get_text_style_set(style_id)
        
        # Update fields
        if style_data.name is not None:
            text_style_set.name = style_data.name
        if style_data.styles is not None:
            self._validate_style_definitions(style_data.styles)
            text_style_set.styles = style_data.styles
        if style_data.is_active is not None:
            text_style_set.is_active = style_data.is_active

        self.db.commit()
        self.db.refresh(text_style_set)
        logger.info("Text style set updated", set_id=str(text_style_set.id))
        return text_style_set

    def delete_text_style_set(self, set_id: UUID) -> bool:
        """Delete a text style set (soft delete)"""
        logger.info("delete_text_style_set called", set_id=str(set_id))
        style_set = self.get_text_style_set(set_id)
        
        # Soft delete - set is_active to False
        self.db.delete(style_set)
        self.db.commit()
        
        logger.info("Text style set deleted", set_id=str(set_id))
        return True

    # Application Settings Management
    def get_app_setting(self, rule_key: str) -> Optional[AppSetting]:
        """Get an application setting by key"""
        logger.info("get_app_setting called", rule_key=rule_key)
        setting = self.db.query(AppSetting).filter(
            AppSetting.rule_key == rule_key
        ).first()
        if setting:
            logger.info("App setting retrieved", rule_key=rule_key)
        else:
            logger.info("App setting not found", rule_key=rule_key)
        return setting

    def get_all_app_settings(self) -> List[AppSetting]:
        """Get all application settings"""
        logger.info("get_all_app_settings called")
        settings = self.db.query(AppSetting).order_by(AppSetting.rule_key).all()
        logger.info("All app settings retrieved", count=len(settings))
        return settings

    def create_or_update_app_setting(self, setting_data: AppSettingCreate) -> AppSetting:
        """Create or update an application setting"""
        logger.info("create_or_update_app_setting called", rule_key=setting_data.rule_key)
        existing = self.get_app_setting(setting_data.rule_key)
        
        if existing:
            # Update existing setting
            logger.info("Updating existing app setting", rule_key=setting_data.rule_key)
            existing.rule_value = setting_data.rule_value
            if setting_data.description is not None:
                existing.description = setting_data.description
            
            self.db.commit()
            self.db.refresh(existing)
            logger.info("App setting updated", rule_key=existing.rule_key)
            return existing
        else:
            # Create new setting
            logger.info("Creating new app setting", rule_key=setting_data.rule_key)
            setting = AppSetting(
                rule_key=setting_data.rule_key,
                rule_value=setting_data.rule_value,
                description=setting_data.description
            )
            
            self.db.add(setting)
            self.db.commit()
            self.db.refresh(setting)
            logger.info("App setting created", rule_key=setting.rule_key)
            return setting

    def update_app_setting(self, rule_key: str, setting_data: AppSettingUpdate) -> AppSetting:
        """Update an existing application setting"""
        logger.info("update_app_setting called", rule_key=rule_key)
        setting = self.get_app_setting(rule_key)
        
        if not setting:
            logger.error("App setting not found", rule_key=rule_key)
            raise NotFoundError("Application setting not found")

        setting.rule_value = setting_data.rule_value
        if setting_data.description is not None:
            setting.description = setting_data.description

        self.db.commit()
        self.db.refresh(setting)
        
        logger.info("App setting updated", rule_key=rule_key)
        return setting

    def delete_app_setting(self, rule_key: str) -> bool:
        """Delete an application setting"""
        logger.info("delete_app_setting called", rule_key=rule_key)
        setting = self.get_app_setting(rule_key)
        
        if not setting:
            logger.error("App setting not found", rule_key=rule_key)
            raise NotFoundError("Application setting not found")

        self.db.delete(setting)
        self.db.commit()
        
        logger.info("App setting deleted", rule_key=rule_key)
        return True

    # Rules Management (using app settings)
    def get_adaptation_rules(self) -> Dict[str, Any]:
        """Get image adaptation rules"""
        logger.info("get_adaptation_rules called")
        setting = self.get_app_setting("adaptation_rules")
        result = setting.rule_value if setting else self._get_default_adaptation_rules()
        logger.info("Adaptation rules retrieved", from_default=not bool(setting))
        return result

    def update_adaptation_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Update image adaptation rules"""
        logger.info("update_adaptation_rules called")
        setting_data = AppSettingCreate(
            rule_key="adaptation_rules",
            rule_value=rules,
            description="Image template rules and adaptation settings"
        )
        
        setting = self.create_or_update_app_setting(setting_data)
        logger.info("Adaptation rules updated")
        return setting.rule_value

    def get_ai_behavior_rules(self) -> Dict[str, Any]:
        """Get AI behavior rules"""
        logger.info("get_ai_behavior_rules called")
        setting = self.get_app_setting("ai_behavior_rules")
        return setting.rule_value if setting else self._get_default_ai_behavior_rules()

    def update_ai_behavior_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Update AI behavior rules"""
        logger.info("update_ai_behavior_rules called")
        setting_data = AppSettingCreate(
            rule_key="ai_behavior_rules",
            rule_value=rules,
            description="AI behavior controls and settings"
        )
        
        setting = self.create_or_update_app_setting(setting_data)
        logger.info("AI behavior rules updated")
        return setting.rule_value

    def get_upload_moderation_rules(self) -> Dict[str, Any]:
        """Get upload and moderation rules"""
        logger.info("get_upload_moderation_rules called")
        setting = self.get_app_setting("upload_moderation_rules")
        return setting.rule_value if setting else self._get_default_upload_moderation_rules()

    def update_upload_moderation_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Update upload and moderation rules"""
        logger.info("update_upload_moderation_rules called")
        setting_data = AppSettingCreate(
            rule_key="upload_moderation_rules",
            rule_value=rules,
            description="Content moderation and upload rules"
        )
        
        setting = self.create_or_update_app_setting(setting_data)
        logger.info("Upload moderation rules updated")
        return setting.rule_value

    def get_manual_editing_rules(self) -> Dict[str, Any]:
        """Get manual editing rules"""
        logger.info("get_manual_editing_rules called")
        setting = self.get_app_setting("manual_editing_rules")
        return setting.rule_value if setting else self._get_default_manual_editing_rules()

    def update_manual_editing_rules(self, rules: Dict[str, Any]) -> Dict[str, Any]:
        """Update manual editing rules"""
        logger.info("update_manual_editing_rules called")
        setting_data = AppSettingCreate(
            rule_key="manual_editing_rules",
            rule_value=rules,
            description="Manual editing rules for users"
        )
        
        setting = self.create_or_update_app_setting(setting_data)
        logger.info("Manual editing rules updated")
        return setting.rule_value

    # Helper methods
    def _validate_style_definitions(self, style_definitions: Dict[str, Any]):
        """Validate text style definitions structure"""
        logger.info("_validate_style_definitions called")
        required_styles = ["title", "subtitle", "content"]
        
        for style_type in required_styles:
            if style_type not in style_definitions:
                raise ValidationError(f"Missing required style: {style_type}")
            
            style = style_definitions[style_type]
            required_fields = ["fontFamily", "fontSize", "fontWeight", "color"]
            
            for field in required_fields:
                if field not in style:
                    raise ValidationError(f"Missing required field '{field}' in {style_type} style")
        logger.info("_validate_style_definitions succeeded")

    def _get_default_adaptation_rules(self) -> Dict[str, Any]:
        """Get default adaptation rules"""
        return {
            "focalPointLogic": "face-centric",
            "layoutGuidance": {
                "safeZone": {
                    "top": 0.1,
                    "bottom": 0.1,
                    "left": 0.1,
                    "right": 0.1
                },
                "logoSize": 0.15
            }
        }

    def _get_default_ai_behavior_rules(self) -> Dict[str, Any]:
        """Get default AI behavior rules"""
        return {
            "adaptationStrategy": "crop",
            "imageQuality": "high"
        }

    def _get_default_upload_moderation_rules(self) -> Dict[str, Any]:
        """Get default upload moderation rules"""
        return {
            "allowedImageTypes": ["jpeg", "png", "psd"],
            "maxFileSizeMb": 50,
            "nsfwAlertsActive": True
        }

    def _get_default_manual_editing_rules(self) -> Dict[str, Any]:
        """Get default manual editing rules"""
        return {
            "editingEnabled": True,
            "croppingEnabled": True,
            "saturationEnabled": True,
            "addTextOrLogoEnabled": True,
            "allowedLogoSources": {
                "types": ["jpeg", "png", "psd", "ai"],
                "maxSizeMb": 10
            }
        }