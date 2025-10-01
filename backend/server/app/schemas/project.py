"""
Project schemas for API request/response validation
"""
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel
from app.models.enums import ProjectStatus


class ProjectBase(BaseModel):
    name: str


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    status: Optional[ProjectStatus] = None


class Project(ProjectBase):
    id: str
    user_id: str
    status: ProjectStatus
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ProjectWithAssets(Project):
    asset_count: int
    assets: Optional[List["AssetPreview"]] = None


class ProjectStatus(BaseModel):
    project_id: str
    status: ProjectStatus
    progress: Dict[str, Any]
    asset_count: int
    completed_assets: int


# Forward reference for AssetPreview
from app.schemas.asset import AssetPreview
ProjectWithAssets.model_rebuild()