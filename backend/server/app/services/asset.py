"""
Asset service for managing uploaded assets
"""
from typing import List, Optional, Union
from sqlalchemy.orm import Session
from sqlalchemy import and_
from uuid import UUID
from fastapi import UploadFile
import os
import shutil
from pathlib import Path
import structlog
import uuid

logger = structlog.get_logger()

from app.models.asset import Asset
from app.models.project import Project
from app.schemas.asset import AssetCreate, AssetUpdate, AssetPreview


class AssetService:
    def __init__(self, db: Session):
        self.db = db

    def create_asset(self, asset_data: AssetCreate, user_id: UUID) -> Asset:
        """Create a new asset"""
        logger.info("create_asset called", user_id=str(user_id), project_id=str(asset_data.project_id))
        # Verify project belongs to user
        project = self.db.query(Project).filter(
            and_(Project.id == asset_data.project_id, Project.user_id == user_id)
        ).first()
        
        if not project:
            logger.error("Project not found or access denied in create_asset", user_id=str(user_id), project_id=str(asset_data.project_id))
            raise ValueError("Project not found or access denied")
        
        asset = Asset(**asset_data.dict())
        self.db.add(asset)
        self.db.commit()
        self.db.refresh(asset)
        logger.info(
            "Asset created via create_asset",
            asset_id=str(asset.id),
            project_id=str(asset.project_id),
            user_id=str(user_id),
            filename=asset.original_filename
        )
        return asset

    def get_asset(self, asset_id: UUID, user_id: UUID) -> Asset:
        """Get asset by ID, ensuring it belongs to the user"""
        logger.info("get_asset called", asset_id=str(asset_id), user_id=str(user_id))
        asset = self.db.query(Asset).join(Project).filter(
            and_(Asset.id == asset_id, Project.user_id == user_id)
        ).first()
        
        if not asset:
            logger.error(
                "Asset not found or access denied",
                asset_id=str(asset_id),
                user_id=str(user_id)
            )
            raise ValueError("Asset not found or access denied")
        logger.info(
            "Asset retrieved",
            asset_id=str(asset.id),
            user_id=str(user_id)
        )
        return asset

    def get_assets_by_project(self, project_id: UUID, user_id: UUID) -> List[Asset]:
        """Get all assets for a project, ensuring project belongs to user"""
        logger.info("get_assets_by_project called", project_id=str(project_id), user_id=str(user_id))
        # First verify project belongs to user
        project = self.db.query(Project).filter(
            and_(Project.id == project_id, Project.user_id == user_id)
        ).first()
        
        if not project:
            logger.error(
                "Project not found or access denied when listing assets",
                project_id=str(project_id),
                user_id=str(user_id)
            )
            raise ValueError("Project not found or access denied")
        
        # Then get assets for the project
        assets = self.db.query(Asset).filter(Asset.project_id == project_id).all()
        logger.info(
            "Assets listed for project",
            project_id=str(project_id),
            user_id=str(user_id),
            asset_count=len(assets)
        )
        return assets

    def get_asset_previews(self, project_id: UUID, user_id: UUID) -> List[AssetPreview]:
        """Get asset previews for a project"""
        logger.info("get_asset_previews called", project_id=str(project_id), user_id=str(user_id))
        assets = self.get_assets_by_project(project_id, user_id)
        
        previews = []
        for asset in assets:
            preview = AssetPreview(
                id=str(asset.id),
                filename=asset.original_filename,
                preview_url=f"/api/v1/assets/{asset.id}/preview",
                metadata=asset.ai_metadata or {},
            )
            previews.append(preview)
        logger.info(
            "Asset previews listed",
            project_id=str(project_id),
            user_id=str(user_id),
            preview_count=len(previews)
        )
        return previews

    def update_asset(self, asset_id: UUID, asset_data: AssetUpdate, user_id: UUID) -> Asset:
        """Update an asset"""
        logger.info("update_asset called", asset_id=str(asset_id), user_id=str(user_id))
        asset = self.get_asset(asset_id, user_id)
        
        for field, value in asset_data.dict(exclude_unset=True).items():
            setattr(asset, field, value)
        
        self.db.commit()
        self.db.refresh(asset)
        logger.info(
            "Asset updated",
            asset_id=str(asset.id),
            user_id=str(user_id)
        )
        return asset

    def delete_asset(self, asset_id: UUID, user_id: UUID) -> bool:
        """Delete an asset"""
        logger.info("delete_asset called", asset_id=str(asset_id), user_id=str(user_id))
        asset = self.get_asset(asset_id, user_id)
        
        # Delete file from storage
        if os.path.exists(asset.storage_path):
            try:
                os.remove(asset.storage_path)
                logger.info(
                    "Asset file deleted from storage",
                    asset_id=str(asset.id),
                    storage_path=asset.storage_path
                )
            except Exception as e:
                logger.error(
                    "Failed to delete asset file from storage",
                    asset_id=str(asset.id),
                    storage_path=asset.storage_path,
                    error=str(e)
                )
        self.db.delete(asset)
        self.db.commit()
        logger.info(
            "Asset deleted",
            asset_id=str(asset.id),
            user_id=str(user_id)
        )
        return True

    def update_asset_status(self, asset_id: UUID, status: str, user_id: UUID) -> Asset:
        """Update asset status (deprecated)"""
        logger.info("update_asset_status called (deprecated)", asset_id=str(asset_id), user_id=str(user_id), status=status)
        try:
            asset = self.get_asset(asset_id, user_id)
        # Note: Asset model no longer has status field, so this method is deprecated
            logger.info("update_asset_status succeeded (deprecated)", asset_id=str(asset_id), user_id=str(user_id), status=status)
            return asset
        except Exception as e:
            logger.error("update_asset_status failed (deprecated)", asset_id=str(asset_id), user_id=str(user_id), status=status, error=str(e))
            raise

    def update_ai_analysis(self, asset_id: UUID, analysis_data: dict, user_id: UUID) -> Asset:
        """Update asset with AI analysis results"""
        logger.info("update_ai_analysis called", asset_id=str(asset_id), user_id=str(user_id))
        try:
            asset = self.get_asset(asset_id, user_id)
            asset.ai_metadata = analysis_data
            self.db.commit()
            self.db.refresh(asset)
            logger.info("AI analysis updated for asset", asset_id=str(asset.id), user_id=str(user_id))
            return asset
        except Exception as e:
            logger.error("update_ai_analysis failed", asset_id=str(asset_id), user_id=str(user_id), error=str(e))
            raise

    def update_ai_analysis_worker(self, asset_id: UUID, analysis_data: dict) -> Asset:
        """Update asset with AI analysis results (worker-only, bypasses user validation)"""
        logger.info("update_ai_analysis_worker called", asset_id=str(asset_id))
        try:
            asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
            if not asset:
                logger.error("Asset not found (worker) for AI analysis update", asset_id=str(asset_id))
                raise ValueError("Asset not found")
            asset.ai_metadata = analysis_data
            self.db.commit()
            self.db.refresh(asset)
            logger.info("AI analysis updated for asset (worker)", asset_id=str(asset.id))
            return asset
        except Exception as e:
            logger.error("update_ai_analysis_worker failed", asset_id=str(asset_id), error=str(e))
            raise

    def get_asset_worker(self, asset_id: UUID) -> Asset:
        """Get asset by ID (worker-only, bypasses user validation)"""
        logger.info("get_asset_worker called", asset_id=str(asset_id))
        
        try:
            asset = self.db.query(Asset).filter(Asset.id == asset_id).first()
            if not asset:
                logger.error("Asset not found (worker)", asset_id=str(asset_id))
                raise ValueError("Asset not found")
            
            logger.info("Asset retrieved (worker)", asset_id=str(asset.id))
            return asset
            
        except Exception as e:
            logger.error("get_asset_worker failed", asset_id=str(asset_id), error=str(e))
            raise

    def get_assets_by_project_worker(self, project_id: UUID) -> List[Asset]:
        """Get all assets for a project (worker-only, bypasses user validation)"""
        logger.info("get_assets_by_project_worker called", project_id=str(project_id))
        try:
            assets = self.db.query(Asset).filter(Asset.project_id == project_id).all()
            logger.info("Assets listed for project (worker)", project_id=str(project_id), asset_count=len(assets))
            return assets
        except Exception as e:
            logger.error("get_assets_by_project_worker failed", project_id=str(project_id), error=str(e))
            raise

    def create_asset_from_upload(self, project_id: Union[str, UUID], user_id: Union[str, UUID], file: UploadFile) -> Asset:
        """Create asset from uploaded file"""
        logger.info(
            "create_asset_from_upload called", 
            project_id=str(project_id), 
            user_id=str(user_id), 
            filename=file.filename
        )
        
        try:
            # Convert string UUIDs to UUID objects if needed
            if isinstance(project_id, str):
                project_id = uuid.UUID(project_id)
            if isinstance(user_id, str):
                user_id = uuid.UUID(user_id)
            
            # Verify project belongs to user
            project = self.db.query(Project).filter(
                and_(Project.id == project_id, Project.user_id == user_id)
            ).first()
            
            if not project:
                logger.error(
                    "Project not found or access denied in create_asset_from_upload", 
                    user_id=str(user_id), 
                    project_id=str(project_id)
                )
                raise ValueError("Project not found or access denied")
            
            # Create upload directory
            upload_dir = Path("uploads") / str(project_id)
            upload_dir.mkdir(parents=True, exist_ok=True)
            
            # Generate unique filename to avoid conflicts
            original_filename = file.filename
            file_extension = Path(original_filename).suffix
            base_name = Path(original_filename).stem
            
            # Check if file already exists and create unique name
            counter = 0
            file_path = upload_dir / original_filename
            while file_path.exists():
                counter += 1
                new_filename = f"{base_name}_{counter}{file_extension}"
                file_path = upload_dir / new_filename
            
            # Save file with buffered writing for better performance
            try:
                with open(file_path, "wb") as buffer:
                    # Reset file pointer to beginning
                    file.file.seek(0)
                    # Use shutil.copyfileobj for efficient copying
                    shutil.copyfileobj(file.file, buffer, length=64*1024)  # 64KB buffer
            except Exception as e:
                # Clean up partial file on error
                if file_path.exists():
                    file_path.unlink()
                raise e
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Extract dimensions for image files with better error handling
            dimensions = None
            dpi = None
            file_type = file_extension[1:].lower() if file_extension else "unknown"
            
            # Only try to extract image metadata for known image types
            if file_type in ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'tiff', 'webp']:
                try:
                    from PIL import Image
                    with Image.open(file_path) as img:
                        dimensions = {"width": img.width, "height": img.height}
                        # Extract DPI if available
                        if hasattr(img, 'info') and 'dpi' in img.info:
                            dpi = int(img.info['dpi'][0])  # Take horizontal DPI
                        elif hasattr(img, 'info') and 'resolution' in img.info:
                            dpi = int(img.info['resolution'][0])
                except Exception as img_error:
                    logger.warning(
                        "Could not extract image metadata",
                        filename=original_filename,
                        error=str(img_error)
                    )
            
            # Create asset record
            asset = Asset(
                project_id=project_id,
                original_filename=original_filename,
                storage_path=str(file_path),
                file_type=file_type,
                file_size_bytes=file_size,
                dimensions=dimensions,
                dpi=dpi
            )
            
            self.db.add(asset)
            self.db.commit()
            self.db.refresh(asset)
            
            logger.info(
                "Asset created via create_asset_from_upload",
                asset_id=str(asset.id),
                project_id=str(asset.project_id),
                user_id=str(user_id),
                filename=asset.original_filename,
                file_size=file_size,
                file_type=file_type
            )
            return asset
            
        except Exception as e:
            logger.error(
                "create_asset_from_upload failed", 
                project_id=str(project_id), 
                user_id=str(user_id), 
                filename=getattr(file, 'filename', 'unknown'), 
                error=str(e)
            )
            raise

    def create_assets_from_bulk_upload(self, project_id: Union[str, UUID], user_id: Union[str, UUID], files: List[UploadFile]) -> List[Asset]:
        """Create multiple assets from bulk upload - optimized for performance"""
        logger.info(
            "create_assets_from_bulk_upload called", 
            project_id=str(project_id), 
            user_id=str(user_id), 
            file_count=len(files)
        )
        
        # Convert string UUIDs to UUID objects if needed
        if isinstance(project_id, str):
            project_id = uuid.UUID(project_id)
        if isinstance(user_id, str):
            user_id = uuid.UUID(user_id)
        
        # Verify project belongs to user (once for all files)
        project = self.db.query(Project).filter(
            and_(Project.id == project_id, Project.user_id == user_id)
        ).first()
        
        if not project:
            logger.error(
                "Project not found or access denied in bulk upload", 
                user_id=str(user_id), 
                project_id=str(project_id)
            )
            raise ValueError("Project not found or access denied")
        
        # Create upload directory
        upload_dir = Path("uploads") / str(project_id)
        upload_dir.mkdir(parents=True, exist_ok=True)
        
        # Process all files
        assets = []
        for file in files:
            try:
                asset = self.create_asset_from_upload(project_id, user_id, file)
                assets.append(asset)
            except Exception as e:
                logger.error(
                    "Failed to create asset in bulk upload",
                    filename=getattr(file, 'filename', 'unknown'),
                    error=str(e)
                )
                # Continue with other files instead of failing entire bulk upload
                continue
        
        logger.info(
            "Bulk upload completed",
            project_id=str(project_id),
            user_id=str(user_id),
            total_files=len(files),
            successful_assets=len(assets)
        )
        
        return assets

