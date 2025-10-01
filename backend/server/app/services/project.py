"""
Project service for managing projects and assets
"""
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.models.project import Project
from app.models.asset import Asset
from app.models.user import User
from app.models.enums import ProjectStatus
from app.schemas.project import ProjectCreate
import uuid
import structlog

logger = structlog.get_logger()


class ProjectService:
    def __init__(self, db: Session):
        self.db = db

    def get_user_projects(self, user_id: str, limit: int = 10, offset: int = 0) -> List[Project]:
        """Get user projects with pagination"""
        return (
            self.db.query(Project)
            .filter(Project.user_id == user_id)
            .order_by(desc(Project.created_at))
            .offset(offset)
            .limit(limit)
            .all()
        )

    def create_project(self, user_id: str, project_name: str) -> Project:
        """Create a new project"""
        project = Project(
            user_id=user_id,
            name=project_name,
            status=ProjectStatus.UPLOADING
        )
        self.db.add(project)
        self.db.commit()
        self.db.refresh(project)
        logger.info(
            "Project created",
            project_id=str(project.id),
            user_id=user_id,
            project_name=project_name
        )
        return project

    def get_project_by_id(self, project_id: str, user_id: str) -> Optional[Project]:
        """Get project by ID for specific user"""
        return (
            self.db.query(Project)
            .filter(Project.id == project_id, Project.user_id == user_id)
            .first()
        )

    def update_project_status(self, project: Project, status: ProjectStatus) -> Project:
        """Update project status"""
        previous_status = project.status
        project.status = status
        self.db.commit()
        self.db.refresh(project)
        logger.info(
            "Project status updated",
            project_id=str(project.id),
            previous_status=previous_status,
            new_status=status
        )
        return project

    def get_project_assets(self, project_id: str) -> List[Asset]:
        """Get all assets for a project"""
        return (
            self.db.query(Asset)
            .filter(Asset.project_id == project_id)
            .all()
        )

    def count_project_files_by_type(self, project_id: str) -> dict:
        """Count files by type for a project"""
        assets = self.get_project_assets(project_id)
        counts = {"psd": 0, "jpg": 0, "png": 0}
        
        for asset in assets:
            file_type = asset.file_type.lower()
            if file_type in ["psd"]:
                counts["psd"] += 1
            elif file_type in ["jpg", "jpeg"]:
                counts["jpg"] += 1
            elif file_type in ["png"]:
                counts["png"] += 1
        
        return counts

    def get_project_processing_status(self, project_id: str) -> dict:
        """Get detailed processing status for a project"""
        assets = self.get_project_assets(project_id)
        
        status_counts = {"ready": 0, "processing": 0, "failed": 0, "pending": 0}
        
        for asset in assets:
            # Determine status from ai_metadata
            ai_metadata = asset.ai_metadata or {}
            
            if ai_metadata.get("analysis_failed"):
                status = "failed"
            elif "analysis_completed_at" in ai_metadata:
                status = "ready"
            elif "processing_started_at" in ai_metadata:
                status = "processing"
            else:
                status = "pending"
                
            status_counts[status] += 1
        
        total_assets = len(assets)
        ready_assets = status_counts["ready"]
        failed_assets = status_counts["failed"]
        
        # Calculate progress
        if total_assets == 0:
            progress = 0
        else:
            progress = int((ready_assets / total_assets) * 100)
        
        return {
            "total_assets": total_assets,
            "status_breakdown": status_counts,
            "progress_percentage": progress,
            "completed_assets": ready_assets,
            "failed_assets": failed_assets,
            "processing_assets": status_counts["processing"],
            "pending_assets": status_counts["pending"]
        }