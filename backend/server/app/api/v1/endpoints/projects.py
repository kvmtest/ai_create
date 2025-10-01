"""
Project endpoints - matching OpenAPI specification
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
from app.db.session import get_db
from app.services.project import ProjectService
from app.services.asset import AssetService
from app.services.auth import AuthService
from app.core.deps import get_current_user
from app.models.user import User
from app.models.enums import ProjectStatus, AssetStatus
from app.workers.queue_config import QueueName
from pydantic import BaseModel

router = APIRouter()


class ProjectResponse(BaseModel):
    id: str
    name: str
    status: str
    submitDate: str
    fileCounts: dict

    class Config:
        from_attributes = True


class ProjectStatusResponse(BaseModel):
    status: str
    progress: int


class AssetPreviewResponse(BaseModel):
    id: str
    filename: str
    previewUrl: str
    metadata: dict

    class Config:
        from_attributes = True


@router.get("/projects")
async def get_user_projects(
    limit: int = 10,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[ProjectResponse]:
    """
    Get User Projects - matches OpenAPI spec
    """
    project_service = ProjectService(db)
    projects = project_service.get_user_projects(
        user_id=str(current_user.id),
        limit=limit,
        offset=offset
    )
    
    result = []
    for project in projects:
        file_counts = project_service.count_project_files_by_type(str(project.id))
        result.append(ProjectResponse(
            id=str(project.id),
            name=project.name,
            status=project.status,
            submitDate=project.created_at.isoformat(),
            fileCounts=file_counts
        ))
    
    return result


@router.post("/projects/upload")
async def create_project_and_upload_assets(
    projectName: str = Form(...),
    files: List[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Create Project and Upload Multiple Assets - Enhanced for bulk upload
    
    Supports multiple file upload in a single request.
    Example curl commands:
    
    Single file:
    curl -X POST /api/v1/projects/upload \\
         -H "Authorization: Bearer TOKEN" \\
         -F 'projectName=My Project' \\
         -F 'files=@image1.jpg'
    
    Multiple files:
    curl -X POST /api/v1/projects/upload \\
         -H "Authorization: Bearer TOKEN" \\
         -F 'projectName=My Project' \\
         -F 'files=@image1.jpg' \\
         -F 'files=@image2.png' \\
         -F 'files=@design.psd'
    
    Returns 202 Accepted with projectId
    """
    # Validate input
    if not files or len(files) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be uploaded"
        )
    
    if len(files) > 50:  # Reasonable limit for bulk upload
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Maximum 50 files allowed per upload"
        )
    
    project_service = ProjectService(db)
    asset_service = AssetService(db)
    
    # Create the project
    project = project_service.create_project(
        user_id=str(current_user.id),
        project_name=projectName
    )
    
    # Process uploaded files with improved error handling
    processed_assets = []
    failed_files = []
    successful_uploads = 0
    
    for i, file in enumerate(files):
        try:
            # Validate file
            if not file.filename:
                failed_files.append({
                    "index": i,
                    "filename": "unknown",
                    "error": "No filename provided"
                })
                continue
                
            # Check file size (50MB limit per file)
            if hasattr(file, 'size') and file.size and file.size > 50 * 1024 * 1024:
                failed_files.append({
                    "index": i,
                    "filename": file.filename,
                    "error": "File size exceeds 50MB limit"
                })
                continue
            
            # Save file and create asset record
            asset = asset_service.create_asset_from_upload(
                project_id=str(project.id),
                user_id=str(current_user.id),
                file=file
            )
            
            # Trigger background processing with Gemini AI (optimized for multiple files)
            try:
                from app.workers.asset_processing import process_upload
                from app.workers.queue_config import create_asset_upload_message, TaskPriority
                
                # Use higher priority for multiple file uploads to process them faster
                priority = TaskPriority.HIGH if len(files) > 1 else TaskPriority.NORMAL
                
                upload_message = create_asset_upload_message(
                    user_id=current_user.id,
                    asset_id=asset.id,
                    project_id=project.id,
                    file_path=asset.storage_path,
                    original_filename=asset.original_filename,
                    file_size=asset.file_size_bytes,
                    mime_type=file.content_type or "application/octet-stream",
                    priority=priority,
                    ai_provider=None  # Let AI manager choose based on configuration
                )
                
                process_upload.apply_async(
                    kwargs={"message_data": upload_message.dict()},
                    queue=QueueName.ASSET_PROCESSING,
                    priority=priority
                )
                successful_uploads += 1
                
            except Exception as e:
                # Log the error but don't fail the upload
                import logging
                import traceback
                logging.error(f"Background processing failed for {file.filename}: {e}")
                logging.error(f"Full traceback: {traceback.format_exc()}")
                # Mark asset as ready since we can't process it with AI
                asset_service.update_ai_analysis_worker(asset.id, {
                    "analysis_completed_at": "manual",
                    "file_validated": True,
                    "processing_skipped": True,
                    "processing_error": str(e)
                })
                processed_assets.append(asset)
                successful_uploads += 1
                
        except Exception as e:
            # Handle individual file upload errors
            import logging
            logging.error(f"Failed to process file {file.filename}: {e}")
            failed_files.append({
                "index": i,
                "filename": file.filename,
                "error": str(e)
            })
    
    # Update project status based on processing results
    if successful_uploads == 0:
        # All files failed - mark project as failed
        project_service.update_project_status(project, ProjectStatus.FAILED)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "message": "All file uploads failed",
                "failed_files": failed_files,
                "successful_uploads": 0,
                "total_files": len(files)
            }
        )
    elif len(processed_assets) == successful_uploads and successful_uploads > 0:
        # All successful files were processed without background processing
        project_service.update_project_status(project, ProjectStatus.READY_FOR_REVIEW)
    else:
        # Some assets were queued for background processing
        project_service.update_project_status(project, ProjectStatus.PROCESSING)
    
    # Prepare response with upload summary
    response_data = {
        "projectId": str(project.id),
        "summary": {
            "total_files": len(files),
            "successful_uploads": successful_uploads,
            "failed_uploads": len(failed_files)
        }
    }
    
    # Include failed files info if any
    if failed_files:
        response_data["failed_files"] = failed_files
    
    return response_data


@router.get("/projects/{projectId}/status")
async def get_project_status(
    projectId: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> ProjectStatusResponse:
    """
    Get Project Status (for polling) - matches OpenAPI spec
    """
    project_service = ProjectService(db)
    project = project_service.get_project_by_id(projectId, str(current_user.id))
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    # Get detailed processing status from assets
    processing_status = project_service.get_project_processing_status(projectId)
    
    # Use asset-level progress if available, otherwise fall back to project status
    if processing_status["total_assets"] > 0:
        progress = processing_status["progress_percentage"]
    else:
        # Fallback progress based on project status
        progress_map = {
            ProjectStatus.UPLOADING: 10,
            ProjectStatus.PROCESSING: 50,
            ProjectStatus.READY_FOR_REVIEW: 80,
            ProjectStatus.GENERATING: 90,
            ProjectStatus.COMPLETED: 100,
            ProjectStatus.FAILED: 0
        }
        progress = progress_map.get(project.status, 0)
    
    return ProjectStatusResponse(
        status=project.status,
        progress=progress
    )


@router.get("/projects/{projectId}/preview")
async def get_ai_analysis_preview(
    projectId: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> List[AssetPreviewResponse]:
    """
    Get AI Analysis Preview of Assets - matches OpenAPI spec
    """
    project_service = ProjectService(db)
    asset_service = AssetService(db)
    
    project = project_service.get_project_by_id(projectId, str(current_user.id))
    
    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    asset_previews = asset_service.get_asset_previews(project.id, UUID(str(current_user.id)))
    
    result = []
    for preview in asset_previews:

    
        result.append(AssetPreviewResponse(
            id=str(preview.id),
            filename=preview.filename,
            previewUrl=f"/api/v1/assets/{preview.id}/preview",
            metadata=preview.metadata
        ))
    
    return result