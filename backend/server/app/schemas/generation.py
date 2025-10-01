"""
Generation-related Pydantic schemas
"""
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from uuid import UUID
from datetime import datetime

from app.models.enums import JobStatus


class CustomResize(BaseModel):
    """Custom resize dimensions for generation"""
    width: int = Field(..., gt=0, description="Width in pixels")
    height: int = Field(..., gt=0, description="Height in pixels")
    
    class Config:
        from_attributes = True


class GenerationRequest(BaseModel):
    """Request schema for starting a new generation job"""
    projectId: UUID = Field(..., description="ID of the project containing assets")
    formatIds: List[UUID] = Field(..., description="List of format IDs to generate")
    customResizes: Optional[List[CustomResize]] = Field(default=None, description="Custom resize dimensions")
    
    class Config:
        from_attributes = True


class GenerationJob(BaseModel):
    """Generation job information"""
    id: UUID
    project_id: UUID
    user_id: UUID
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True


class GenerationJobCreate(BaseModel):
    """Schema for creating a new generation job"""
    project_id: UUID
    user_id: UUID
    status: str = JobStatus.PENDING
    
    class Config:
        from_attributes = True


class GenerationJobUpdate(BaseModel):
    """Schema for updating a generation job"""
    status: Optional[str] = None
    progress: Optional[int] = Field(None, ge=0, le=100)
    
    class Config:
        from_attributes = True


class GenerationJobStatus(BaseModel):
    """Job status response for polling endpoints"""
    status: str = Field(..., description="Current job status")
    progress: int = Field(..., ge=0, le=100, description="Progress percentage")
    
    class Config:
        from_attributes = True


class GenerationResults(BaseModel):
    """Generation results grouped by platform"""
    results: Dict[str, List[Dict[str, Any]]] = Field(
        ..., 
        description="Generated assets grouped by platform name"
    )
    
    class Config:
        from_attributes = True
