"""
Generation service for managing AI generation jobs
"""
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from uuid import UUID
from app.models.generation import GenerationJob
from app.models.asset import GeneratedAsset
from app.models.project import Project
from app.models.enums import JobStatus
import uuid
import structlog

logger = structlog.get_logger()


class GenerationService:
    def __init__(self, db: Session):
        self.db = db

    def create_generation_job(
        self, 
        project_id: str, 
        user_id: str,
        format_ids: List[str], 
        custom_resizes: List[Dict[str, Any]]
    ) -> GenerationJob:
        """Create a new generation job"""
        logger.info(
            "create_generation_job called",
            project_id=project_id,
            user_id=user_id,
            format_count=len(format_ids),
            custom_resizes_count=len(custom_resizes),
        )
        total_operations = len(format_ids) + len(custom_resizes)
        
        job = GenerationJob(
            project_id=project_id,
            user_id=user_id,
            status=JobStatus.PENDING,
            progress=0
        )
        
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        logger.info("generation job created", job_id=str(job.id))
        return job

    def get_job_by_id(self, job_id: str) -> Optional[GenerationJob]:
        """Get generation job by ID"""
        logger.info("get_job_by_id called", job_id=job_id)
        return self.db.query(GenerationJob).filter(GenerationJob.id == job_id).first()

    def update_job_status(self, job: GenerationJob, status: JobStatus, progress: int = None) -> GenerationJob:
        """Update job status and progress"""
        logger.info("update_job_status called", job_id=str(job.id), status=str(status), progress=progress)
        job.status = status
        if progress is not None:
            job.progress = progress
        self.db.commit()
        self.db.refresh(job)
        logger.info("job status updated", job_id=str(job.id), status=str(job.status), progress=job.progress)
        return job

    def get_job_results(self, job_id: str) -> Dict[str, List[GeneratedAsset]]:
        """Get generation job results grouped by platform"""
        logger.info("get_job_results called", job_id=job_id)
        generated_assets = (
            self.db.query(GeneratedAsset)
            .filter(GeneratedAsset.job_id == job_id)
            .all()
        )
        
        # Group by platform name
        results = {}
        for asset in generated_assets:
            platform_name = "Custom" if not asset.asset_format else asset.asset_format.platform.name if asset.asset_format.platform else asset.asset_format.name
            
            if platform_name not in results:
                results[platform_name] = []
            
            results[platform_name].append(asset)
        
        return results

    def get_generated_asset_by_id(self, asset_id: str) -> Optional[GeneratedAsset]:
        """Get generated asset by ID"""
        logger.info("get_generated_asset_by_id called", asset_id=asset_id)
        return self.db.query(GeneratedAsset).filter(GeneratedAsset.id == asset_id).first()

    def update_generated_asset_edits(self, asset: GeneratedAsset, edits: Dict[str, Any]) -> GeneratedAsset:
        """Apply manual edits to generated asset"""
        logger.info("update_generated_asset_edits called", asset_id=str(asset.id))
        asset.manual_edits = edits
        self.db.commit()
        self.db.refresh(asset)
        logger.info("generated asset edits updated", asset_id=str(asset.id))
        return asset

    def update_job_progress(self, job_id: UUID, progress: int, status: JobStatus = None) -> GenerationJob:
        """Update job progress and optionally status"""
        logger.info("update_job_progress called", job_id=str(job_id), progress=progress, status=str(status) if status else None)
        job = self.db.query(GenerationJob).filter(GenerationJob.id == job_id).first()
        if job:
            if status:
                job.status = status
            job.progress = progress
            self.db.commit()
            self.db.refresh(job)
        return job

    def get_job_status(self, job_id: str, user_id: UUID) -> Optional[GenerationJob]:
        """Get job status for a specific user"""
        logger.info("get_job_status called", job_id=job_id, user_id=str(user_id))
        return (
            self.db.query(GenerationJob)
            .filter(GenerationJob.id == job_id, GenerationJob.user_id == str(user_id))
            .first()
        )

    def get_generated_asset(self, asset_id: UUID, user_id: UUID) -> Optional[GeneratedAsset]:
        """Get generated asset by ID for a specific user"""
        logger.info("get_generated_asset called", asset_id=str(asset_id), user_id=str(user_id))
        return (
            self.db.query(GeneratedAsset)
            .join(GenerationJob)
            .filter(GeneratedAsset.id == asset_id, GenerationJob.user_id == str(user_id))
            .first()
        )

    def update_generated_asset(self, asset_id: UUID, updates: Dict[str, Any]) -> Optional[GeneratedAsset]:
        """Update generated asset with new data"""
        logger.info("update_generated_asset called", asset_id=str(asset_id))
        asset = self.db.query(GeneratedAsset).filter(GeneratedAsset.id == asset_id).first()
        if asset:
            for key, value in updates.items():
                if hasattr(asset, key):
                    setattr(asset, key, value)
            self.db.commit()
            self.db.refresh(asset)
            logger.info("generated asset updated", asset_id=str(asset.id))
        return asset