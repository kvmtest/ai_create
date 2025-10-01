"""
Asset schemas for API request/response validation
"""
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, UUID4


class AssetBase(BaseModel):
    original_filename: str
    file_type: str
    file_size_bytes: int


class AssetCreate(AssetBase):
    project_id: UUID4
    storage_path: str
    dimensions: Optional[Dict[str, int]] = None
    dpi: Optional[int] = None


class AssetUpdate(BaseModel):
    ai_metadata: Optional[Dict[str, Any]] = None


class Asset(AssetBase):
    id: UUID4
    project_id: UUID4
    storage_path: str
    dimensions: Optional[Dict[str, int]]
    dpi: Optional[int]
    ai_metadata: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class AssetPreview(BaseModel):
    id: UUID4
    filename: str
    preview_url: str
    metadata: Dict[str, Any]

    class Config:
        from_attributes = True


class GeneratedAssetBase(BaseModel):
    file_type: str
    dimensions: Dict[str, int]
    is_nsfw: bool = False


class GeneratedAssetCreate(GeneratedAssetBase):
    job_id: str
    original_asset_id: str
    asset_format_id: Optional[str] = None
    storage_path: str
    manual_edits: Dict[str, Any] = {}


class GeneratedAssetUpdate(BaseModel):
    manual_edits: Dict[str, Any]


class GeneratedAsset(GeneratedAssetBase):
    id: str
    job_id: str
    original_asset_id: str
    asset_format_id: Optional[str]
    storage_path: str
    manual_edits: Dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class CropParams(BaseModel):
    x: float = 0.0  # Relative x position (0.0 to 1.0)
    y: float = 0.0  # Relative y position (0.0 to 1.0)
    width: float = 1.0  # Relative width (0.0 to 1.0)
    height: float = 1.0  # Relative height (0.0 to 1.0)


class TextOverlay(BaseModel):
    text: str
    x: float = 0.5  # Relative x position (0.0 to 1.0)
    y: float = 0.5  # Relative y position (0.0 to 1.0)
    style_set_id: Optional[str] = None
    style_type: str = "content"  # title, subtitle, content


class LogoOverlay(BaseModel):
    logo_path: str
    x: float = 0.5  # Relative x position (0.0 to 1.0)
    y: float = 0.5  # Relative y position (0.0 to 1.0)
    width: Optional[int] = None  # Absolute width in pixels
    height: Optional[int] = None  # Absolute height in pixels
    source: Optional[str] = None  # Logo source identifier for validation


class ManualEdit(BaseModel):
    crop: Optional[CropParams] = None
    saturation: Optional[float] = None  # -1.0 to 1.0
    text_overlays: Optional[List[TextOverlay]] = None
    logo_overlays: Optional[List[LogoOverlay]] = None


class EditHistoryEntry(BaseModel):
    version: int
    timestamp: str
    edits: Dict[str, Any]


class EditHistory(BaseModel):
    history: List[EditHistoryEntry]
    current_version: int