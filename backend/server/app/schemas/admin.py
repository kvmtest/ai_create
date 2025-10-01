"""
Admin schemas for API request/response validation
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import PlatformType


class PlatformBase(BaseModel):
    name: str
    type: PlatformType
    is_active: bool = True


class PlatformCreate(PlatformBase):
    pass


class PlatformUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[PlatformType] = None
    is_active: Optional[bool] = None


class PlatformResponse(BaseModel):
    name: str
    type: PlatformType

    model_config = {"from_attributes": True}


class Platform(PlatformBase):
    id: str
    created_by_admin_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
    
    @classmethod
    def from_orm(cls, obj):
        """Custom from_orm method to handle UUID conversion"""
        data = {
            "id": str(obj.id),
            "name": obj.name,
            "type": obj.type,
            "is_active": obj.is_active,
            "created_by_admin_id": str(obj.created_by_admin_id) if obj.created_by_admin_id else None,
            "created_at": obj.created_at
        }
        return cls(**data)


class AssetFormatBase(BaseModel):
    name: str
    platform_id: str
    width: int
    height: int
    is_active: bool = True


class AssetFormatCreate(AssetFormatBase):
    pass


class AssetFormatUpdate(BaseModel):
    name: Optional[str] = None
    platform_id: Optional[str] = None
    width: Optional[int] = None
    height: Optional[int] = None
    is_active: Optional[bool] = None


class AssetFormatResponse(BaseModel):
    id: str
    name: str
    platform_id: str
    platform_name: str
    platform_type: PlatformType
    width: int
    height: int
    is_active: bool
    created_by_admin_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AssetFormat(AssetFormatBase):
    id: str
    created_by_admin_id: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class TextStyleSetBase(BaseModel):
    name: str
    styles: Dict[str, Any]
    is_active: bool = True


class TextStyleSetCreate(TextStyleSetBase):
    pass


class TextStyleSetUpdate(BaseModel):
    name: Optional[str] = None
    styles: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None


class TextStyleSet(TextStyleSetBase):
    id: str
    created_by_admin_id: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}
    
    @classmethod
    def from_orm(cls, obj):
        """Custom from_orm method to handle UUID conversion"""
        data = {
            "id": str(obj.id),
            "name": obj.name,
            "styles": obj.styles,
            "is_active": obj.is_active,
            "created_by_admin_id": str(obj.created_by_admin_id) if obj.created_by_admin_id else None,
            "created_at": obj.created_at
        }
        return cls(**data)


class AppSettingBase(BaseModel):
    rule_key: str
    rule_value: Dict[str, Any]
    description: Optional[str] = None


# Rule Schemas matching OpenAPI specification
class TextStyleDefinition(BaseModel):
    fontFamily: str
    fontSize: int
    fontWeight: str
    color: str


class AdaptationRule(BaseModel):
    focalPointLogic: str  # face-centric, product-centric, 'face-centric & product-centric', human-centered
    layoutGuidance: Dict[str, Any]


class AIBehaviorRule(BaseModel):
    adaptationStrategy: str  # crop, extend-canvas, add-background
    imageQuality: str  # low, medium, high


class UploadModerationRule(BaseModel):
    allowedImageTypes: list[str]  # jpeg, png, psd
    maxFileSizeMb: int
    nsfwAlertsActive: bool


class ManualEditingRule(BaseModel):
    editingEnabled: bool
    croppingEnabled: bool
    saturationEnabled: bool
    addTextOrLogoEnabled: bool
    allowedLogoSources: Dict[str, Any]


class AppSettingCreate(AppSettingBase):
    pass


class AppSettingUpdate(BaseModel):
    rule_value: Dict[str, Any]
    description: Optional[str] = None


class AppSetting(AppSettingBase):
    id: int
    updated_at: datetime

    class Config:
        from_attributes = True


class RulesUpdate(BaseModel):
    adaptation_rules: Optional[Dict[str, Any]] = None
    ai_behavior_rules: Optional[Dict[str, Any]] = None
    moderation_rules: Optional[Dict[str, Any]] = None
    editing_rules: Optional[Dict[str, Any]] = None