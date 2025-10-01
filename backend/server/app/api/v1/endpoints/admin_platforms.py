"""
Admin endpoints for managing platforms and formats
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.models.enums import PlatformType
from app.services.admin import AdminService
from app.schemas.admin import (
    Platform, PlatformCreate, PlatformUpdate, PlatformResponse,
    AssetFormat, AssetFormatCreate, AssetFormatUpdate, AssetFormatResponse,
    TextStyleSet, TextStyleSetCreate, TextStyleSetUpdate
)
from app.core.exceptions import NotFoundError, ValidationError

router = APIRouter()


# Platform Management Endpoints
@router.get("/platforms")
async def list_platforms(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all repurposing platforms"""
    admin_service = AdminService(db)
    platforms = admin_service.get_platforms()
    # Convert to dict to avoid Pydantic serialization issues
    return [
        {
            "id": str(p.id),
            "name": p.name,
            # "description": p.description,
            # "is_active": p.is_active,
            # "created_at": p.created_at,
            # "updated_at": p.updated_at
        }
        for p in platforms
    ]


@router.post("/platforms", status_code=status.HTTP_201_CREATED)
async def create_platform(
    platform_data: PlatformCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Add a new repurposing platform"""
    admin_service = AdminService(db)
    
    try:
        platforms =  admin_service.create_platform(platform_data, current_user.id)
        return [
            {
                "id": str(platforms.id),
                "name": platforms.name,
                # "description": p.description,
                # "is_active": p.is_active,
                # "created_at": p.created_at,
                # "updated_at": p.updated_at
            }
        ]
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.put("/platforms/{platformId}", status_code=status.HTTP_200_OK, response_model=PlatformResponse)
async def update_platform(
    platformId: UUID,
    platform_data: PlatformUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
) -> PlatformResponse:
    """Update a platform's information"""
    admin_service = AdminService(db)
    
    try:
        platform = admin_service.update_platform(platformId, platform_data)
        return PlatformResponse.model_validate(platform)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform not found"
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.delete("/platforms/{platformId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_platform(
    platformId: UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a platform"""
    admin_service = AdminService(db)
    
    try:
        admin_service.delete_platform(platformId)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Platform not found"
        )


# Asset Format Management Endpoints
@router.get("/formats", response_model=List[AssetFormatResponse])
async def list_formats(
    platform_type: Optional[PlatformType] = Query(
        None, 
        description="Filter by format type",
        enum=["resizing", "repurposing"]
    ),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
) -> List[AssetFormatResponse]:
    """List all asset formats with optional filtering
    
    **Format Types:**
    - **resizing**: Formats for resizing assets to different dimensions
    - **repurposing**: Formats for repurposing assets for different platforms
    """
    admin_service = AdminService(db)
    formats = admin_service.get_formats(platform_type=platform_type)
    
    # Convert to response models with proper data
    response_formats = []
    for f in formats:
        response_formats.append(AssetFormatResponse(
            id=str(f.id),
            name=f.name,
            platform_id=str(f.platform_id),
            platform_name=f.platform.name,
            platform_type=f.platform.type,
            width=f.width,
            height=f.height,
            is_active=f.is_active,
            created_by_admin_id=str(f.created_by_admin_id) if f.created_by_admin_id else None,
            created_at=f.created_at
        ))
    
    return response_formats


@router.post("/formats", status_code=status.HTTP_201_CREATED)
async def create_format(
    format_data: AssetFormatCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new asset format"""
    admin_service = AdminService(db)
    
    try:
        return admin_service.create_format(format_data, current_user.id)
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.put("/formats/{formatId}")
async def update_format(
    formatId: UUID,
    format_data: AssetFormatUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update an asset format"""
    admin_service = AdminService(db)
    
    try:
        return admin_service.update_format(formatId, format_data)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset format not found"
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e)
        )


@router.delete("/formats/{formatId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_format(
    formatId: UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete an asset format"""
    admin_service = AdminService(db)
    
    try:
        admin_service.delete_format(formatId)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset format not found"
        )


# Text Style Set Management Endpoints
@router.get("/text-style-sets")
async def list_text_style_sets(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """List all text style sets"""
    admin_service = AdminService(db)
    styles = admin_service.get_text_style_sets()
    # Convert to dict to avoid Pydantic serialization issues
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "styles": s.styles,
            "is_active": s.is_active,
            "created_by_admin_id": str(s.created_by_admin_id) if s.created_by_admin_id else None,
            "created_at": s.created_at,
        }
        for s in styles
    ]


@router.post("/text-style-sets", status_code=status.HTTP_201_CREATED)
async def create_text_style_set(
    style_data: TextStyleSetCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create a new text style set"""
    admin_service = AdminService(db)
    return admin_service.create_text_style_set(style_data, current_user.id)


@router.put("/text-style-sets/{setId}")
async def update_text_style_set(
    setId: UUID,
    style_data: TextStyleSetUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update a text style set"""
    admin_service = AdminService(db)
    
    try:
        return admin_service.update_text_style_set(setId, style_data)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Text style set not found"
        )


@router.delete("/text-style-sets/{setId}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_text_style_set(
    setId: UUID,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Delete a text style set"""
    admin_service = AdminService(db)
    
    try:
        admin_service.delete_text_style_set(setId)
    except NotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Text style set not found"
        )
