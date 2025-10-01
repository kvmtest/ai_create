"""
Generation endpoints - matching OpenAPI specification
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from uuid import UUID
from app.db.session import get_db
from app.services.generation import GenerationService
from app.services.project import ProjectService
from app.core.deps import get_current_user
from app.core.config import settings
from app.models.user import User
from app.models.enums import JobStatus, ProjectStatus
from pydantic import BaseModel

router = APIRouter()


class CustomResize(BaseModel):
    width: int
    height: int


class GenerationRequest(BaseModel):
    projectId: str
    formatIds: List[str] = []
    customResizes: List[CustomResize] = []
    provider: str


class AIProviderResponse(BaseModel):
    providers: List[str]


class JobStatusResponse(BaseModel):
    status: str
    progress: int


class GeneratedAssetResponse(BaseModel):
    id: str
    originalAssetId: str
    filename: str
    assetUrl: str
    platformName: str = None
    formatName: str
    dimensions: Dict[str, int]
    isNsfw: bool

    class Config:
        from_attributes = True


class ManualEditRequest(BaseModel):
    edits: Dict[str, Any]


class TextOverlay(BaseModel):
    content: str
    textStyleSetId: str
    styleType: str
    position: Dict[str, float]


class LogoOverlay(BaseModel):
    logoUrl: str
    position: Dict[str, float]
    size: float


class DownloadRequest(BaseModel):
    assetIds: List[str]
    format: str
    quality: str
    grouping: str


@router.get("/providers", response_model=AIProviderResponse)
async def get_ai_providers():
    """
    Get List of AI Providers - New endpoint
    """
    return AIProviderResponse(providers=settings.AVAILABLE_AI_PROVIDERS)


@router.post("/generate")
async def start_generation_job(
    request: GenerationRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Start a New Generation Job - matches OpenAPI spec
    """
    project_service = ProjectService(db)
    generation_service = GenerationService(db)
    
    # Validate provider
    if request.provider not in settings.AVAILABLE_AI_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid provider. Available providers are: {', '.join(settings.AVAILABLE_AI_PROVIDERS)}"
        )
    
    # Verify project belongs to user
    project = project_service.get_project_by_id(request.projectId, str(current_user.id))
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Convert custom resizes to dict format
    custom_resizes = [{"width": r.width, "height": r.height} for r in request.customResizes]
    
    # Create generation job
    job = generation_service.create_generation_job(
        project_id=request.projectId,
        user_id=str(current_user.id),
        format_ids=request.formatIds,
        custom_resizes=custom_resizes
    )
    
    # Update project status to generating
    project_service.update_project_status(project, ProjectStatus.GENERATING)
    
    # Trigger background generation
    from app.workers.generation import generate_assets
    from app.workers.queue_config import create_generation_request_message, TaskPriority
    from uuid import UUID
    
    # Get project assets
    assets = project_service.get_project_assets(request.projectId)
    asset_ids = [asset.id for asset in assets]
    
    generation_message = create_generation_request_message(
        user_id=current_user.id,
        job_id=UUID(str(job.id)),
        project_id=UUID(request.projectId),
        asset_ids=asset_ids,
        format_ids=[UUID(fid) for fid in request.formatIds],
        custom_sizes=custom_resizes,
        priority=TaskPriority.NORMAL,
        provider=request.provider
    )
    
    generate_assets.apply_async(
        kwargs={"message_data": generation_message.dict()},
        queue="generation"
    )
    
    return {"jobId": str(job.id)}


@router.get("/generate/{jobId}/status")
async def get_generation_job_status(
    jobId: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> JobStatusResponse:
    """
    Get Generation Job Status (for polling) - matches OpenAPI spec
    """
    generation_service = GenerationService(db)
    job = generation_service.get_job_by_id(jobId)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    # Calculate progress percentage
    if isinstance(job.progress, dict):
        progress_data = job.progress
        progress_percent = int((progress_data.get("completed", 0) / progress_data.get("total", 1)) * 100)
    elif isinstance(job.progress, (int, float)):
        progress_percent = int(job.progress)
    else:
        progress_percent = 0
    
    return JobStatusResponse(
        status=job.status,
        progress=progress_percent
    )


@router.get("/generate/{jobId}/results")
async def get_generation_job_results(
    jobId: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, List[GeneratedAssetResponse]]:
    """
    Get Generation Job Results - matches OpenAPI spec
    """
    generation_service = GenerationService(db)
    job = generation_service.get_job_by_id(jobId)
    
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found"
        )
    
    results = generation_service.get_job_results(jobId)
    
    # Convert to response format
    response = {}
    for platform_name, assets in results.items():
        response[platform_name] = []
        for asset in assets:
            response[platform_name].append(GeneratedAssetResponse(
                id=str(asset.id),
                originalAssetId=str(asset.original_asset_id),
                filename=f"generated_{asset.id}.{asset.file_type}",
                assetUrl=f"/api/v1/assets/{asset.id}/download",
                platformName=platform_name,
                formatName=asset.asset_format.name if asset.asset_format else "Custom",
                dimensions=asset.dimensions,
                isNsfw=asset.is_nsfw
            ))
    
    return response


@router.get("/generated-assets/{assetId}")
async def get_generated_asset(
    assetId: str,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> GeneratedAssetResponse:
    """
    Get a single Generated Asset - matches OpenAPI spec
    """
    # Validate UUID format
    try:
        from uuid import UUID
        UUID(assetId)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid asset ID format"
        )
    
    generation_service = GenerationService(db)
    asset = generation_service.get_generated_asset_by_id(assetId)
    
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Asset not found"
        )
    
    platform_name = "Custom" if not asset.asset_format else asset.asset_format.platform.name if asset.asset_format.platform else asset.asset_format.name
    
    # Construct full URL with domain
    base_url = str(request.base_url).rstrip('/')
    full_asset_url = f"{base_url}/api/v1/assets/{asset.id}/download"
    
    return GeneratedAssetResponse(
        id=str(asset.id),
        originalAssetId=str(asset.original_asset_id),
        filename=f"generated_{asset.id}.{asset.file_type}",
        assetUrl=full_asset_url,
        platformName=platform_name,
        formatName=asset.asset_format.name if asset.asset_format else "Custom",
        dimensions=asset.dimensions,
        isNsfw=asset.is_nsfw
    )


@router.put("/generated-assets/{assetId}")
async def apply_manual_edits(
    assetId: str,
    edit_request: ManualEditRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> GeneratedAssetResponse:
    """
    Apply Manual Edits to a Generated Asset - matches OpenAPI spec
    """
    from app.services.manual_edit import ManualEditService
    from app.schemas.asset import ManualEdit
    
    manual_edit_service = ManualEditService(db)
    
    # Convert edit request to ManualEdit schema
    try:
        manual_edits = ManualEdit(**edit_request.edits)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid edit format: {str(e)}"
        )
    
    # Apply manual edits
    try:
        updated_asset = manual_edit_service.apply_manual_edits(
            generated_asset_id=UUID(assetId),
            edits=manual_edits,
            user_id=current_user.id
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    platform_name = "Custom" if not updated_asset.asset_format else updated_asset.asset_format.platform.name if updated_asset.asset_format.platform else updated_asset.asset_format.name
    
    # Construct full URL with domain
    base_url = str(request.base_url).rstrip('/')
    full_asset_url = f"{base_url}/api/v1/assets/{updated_asset.id}/download"
    
    return GeneratedAssetResponse(
        id=str(updated_asset.id),
        originalAssetId=str(updated_asset.original_asset_id),
        filename=f"generated_{updated_asset.id}.{updated_asset.file_type}",
        assetUrl=full_asset_url,
        platformName=platform_name,
        formatName=updated_asset.asset_format.name if updated_asset.asset_format else "Custom",
        dimensions=updated_asset.dimensions,
        isNsfw=updated_asset.is_nsfw
    )


@router.post("/download")
async def get_download_url(
    download_request: DownloadRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Get Download URL for Assets - matches OpenAPI spec
    """
    from app.services.download import DownloadService
    
    download_service = DownloadService(db)
    
    try:
        base_url = str(request.base_url).rstrip('/')
        download_url = download_service.create_download_url(
            asset_ids=[UUID(aid) for aid in download_request.assetIds],
            format_type=download_request.format,
            quality=download_request.quality,
            grouping=download_request.grouping,
            user_id=current_user.id,
            base_url=base_url
        )
        
        return {"downloadUrl": download_url}
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )