"""
Download endpoints for asset download and export
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.core.deps import get_db, get_current_user
from app.models.user import User
from app.services.download import DownloadService
from app.core.exceptions import ValidationError, NotFoundError

router = APIRouter()


class DownloadRequest(BaseModel):
    assetIds: List[UUID]
    format: str  # jpeg, png
    quality: str  # high, medium, low
    grouping: str  # individual, batch, category


class DownloadResponse(BaseModel):
    downloadUrl: str


@router.post("/download", response_model=DownloadResponse)
async def get_download_url(
    payload: DownloadRequest,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Get Download URL for Assets
    
    Creates a download URL for the specified assets with format conversion and quality optimization.
    Supports individual files, batch downloads, and category grouping.
    """
    try:
        # Validate request parameters
        if payload.format not in ["jpeg", "png"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Format must be 'jpeg' or 'png'"
            )
        
        if payload.quality not in ["high", "medium", "low"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Quality must be 'high', 'medium', or 'low'"
            )
        
        if payload.grouping not in ["individual", "batch", "category"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Grouping must be 'individual', 'batch', or 'category'"
            )
        
        if not payload.assetIds:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="At least one asset ID is required"
            )
        
        service = DownloadService(db)
        # Derive base URL for absolute download links from FastAPI Request
        base_url = str(request.base_url).rstrip('/')
        download_url = service.create_download_url(
            asset_ids=payload.assetIds,
            format_type=payload.format,
            quality=payload.quality,
            grouping=payload.grouping,
            user_id=current_user.id,
            base_url=base_url
        )
        
        return DownloadResponse(downloadUrl=download_url)
    
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )
    except ValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/download/file/{token}/{filename}")
async def download_file(
    token: str,
    filename: str,
    db: Session = Depends(get_db)
):
    """
    Download file using token
    
    Internal endpoint for serving files via download tokens.
    """
    try:
        service = DownloadService(db)
        file_path = service.get_download_file(token)
        
        return FileResponse(
            path=file_path,
            filename=filename,
            media_type='application/octet-stream'
        )
    except NotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e)
        )


@router.get("/assets/{assetId}/download")
async def download_generated_asset(
    assetId: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Download a single generated asset file directly.

    This endpoint serves the physical file for a generated asset while validating that
    the asset belongs to the authenticated user. It is referenced by the
    `assetUrl` field returned from generation result endpoints.
    """
    from uuid import UUID as _UUID
    from app.services.generation import GenerationService
    import mimetypes
    import os

    # Validate UUID format
    try:
        asset_uuid = _UUID(assetId)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset ID format"
        )

    generation_service = GenerationService(db)
    asset = generation_service.get_generated_asset(asset_uuid, current_user.id)
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )

    file_path = asset.storage_path
    if not file_path or not os.path.exists(file_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset file not found"
        )

    # Determine media type
    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        # Fallback for common image extensions if mimetypes fails
        ext = (asset.file_type or '').lower()
        if ext in ("jpg", "jpeg"):
            mime_type = "image/jpeg"
        elif ext == "png":
            mime_type = "image/png"
        else:
            mime_type = "application/octet-stream"

    download_filename = f"generated_{asset.id}.{asset.file_type}" if asset.file_type else os.path.basename(file_path)

    return FileResponse(
        path=file_path,
        filename=download_filename,
        media_type=mime_type,
        headers={
            # Allow inline display in browsers for images while still downloadable
            "Content-Disposition": f"inline; filename={download_filename}" if mime_type.startswith("image/") else f"attachment; filename={download_filename}"
        }
    )