"""
Download service for asset download and export functionality
"""
from typing import List, Dict, Any
from uuid import UUID
import os
import zipfile
import tempfile
from pathlib import Path
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models.asset import GeneratedAsset, Asset
from app.models.project import Project
from app.core.exceptions import ValidationError, NotFoundError
from app.core.config import settings


class DownloadService:
    # Class variable for persistent token storage across instances
    _download_tokens = {}
    
    def __init__(self, db: Session):
        self.db = db

    def create_download_url(
        self,
        asset_ids: List[UUID],
        format_type: str,
        quality: str,
        grouping: str,
        user_id: UUID,
        base_url: str
    ) -> str:
        """Create a download URL for the specified assets."""
        
        # Store base URL for URL generation
        self.base_url = base_url
        
        # Validate assets belong to user
        assets = self._get_user_assets(asset_ids, user_id)
        
        if grouping == "individual" and len(assets) > 1:
            raise ValidationError("Individual grouping only supports single asset")
        
        if grouping == "individual":
            # Single asset download
            asset = assets[0]
            processed_path = self._process_single_asset(asset, format_type, quality)
            return self._generate_presigned_url(processed_path)
        else:
            # Batch or category download - create ZIP
            zip_path = self._create_zip_download(assets, format_type, quality, grouping)
            return self._generate_presigned_url(zip_path)

    def _get_user_assets(self, asset_ids: List[UUID], user_id: UUID) -> List[GeneratedAsset]:
        """Get assets that belong to the user."""
        assets = self.db.query(GeneratedAsset).join(
            Asset, GeneratedAsset.original_asset_id == Asset.id
        ).join(
            Project, Asset.project_id == Project.id
        ).filter(
            and_(
                GeneratedAsset.id.in_(asset_ids),
                Project.user_id == user_id
            )
        ).all()
        
        if len(assets) != len(asset_ids):
            raise NotFoundError("Some assets not found or access denied")
        
        return assets

    def _process_single_asset(self, asset: GeneratedAsset, format_type: str, quality: str) -> str:
        """Process a single asset for download."""
        source_path = asset.storage_path
        
        if not os.path.exists(source_path):
            raise NotFoundError(f"Asset file not found: {source_path}")
        
        # If format and quality match existing file, return as-is
        if self._matches_requirements(source_path, format_type, quality):
            return source_path
        
        # Convert format/quality if needed
        return self._convert_asset(source_path, format_type, quality)

    def _create_zip_download(
        self, 
        assets: List[GeneratedAsset], 
        format_type: str, 
        quality: str, 
        grouping: str
    ) -> str:
        """Create a ZIP file containing multiple assets."""
        
        # Create temporary ZIP file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"assets_{grouping}_{timestamp}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_filename)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            for asset in assets:
                # Process each asset
                processed_path = self._process_single_asset(asset, format_type, quality)
                
                # Determine filename in ZIP
                if grouping == "category":
                    # Group by platform/format
                    category = self._get_asset_category(asset)
                    zip_filename = f"{category}/{Path(processed_path).name}"
                else:
                    # Batch - flat structure
                    zip_filename = Path(processed_path).name
                
                zip_file.write(processed_path, zip_filename)
        
        return zip_path

    def _matches_requirements(self, file_path: str, format_type: str, quality: str) -> bool:
        """Check if file already matches the required format and quality."""
        file_ext = Path(file_path).suffix.lower()
        
        # Check format
        if format_type == "jpeg" and file_ext not in [".jpg", ".jpeg"]:
            return False
        if format_type == "png" and file_ext != ".png":
            return False
        
        # For simplicity, assume existing files are acceptable quality
        return True

    def _convert_asset(self, source_path: str, format_type: str, quality: str) -> str:
        """Convert asset to specified format and quality."""
        from PIL import Image
        
        # Create output filename
        source_file = Path(source_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        if format_type == "jpeg":
            output_filename = f"{source_file.stem}_{quality}_{timestamp}.jpg"
        else:
            output_filename = f"{source_file.stem}_{quality}_{timestamp}.png"
        
        output_path = source_file.parent / output_filename
        
        # Convert image
        with Image.open(source_path) as img:
            # Convert to RGB for JPEG
            if format_type == "jpeg" and img.mode in ("RGBA", "P"):
                img = img.convert("RGB")
            
            # Set quality based on parameter
            save_kwargs = {}
            if format_type == "jpeg":
                quality_map = {"high": 95, "medium": 80, "low": 60}
                save_kwargs = {"quality": quality_map.get(quality, 80), "optimize": True}
            else:
                save_kwargs = {"optimize": True}
            
            img.save(output_path, **save_kwargs)
        
        return str(output_path)

    def _get_asset_category(self, asset: GeneratedAsset) -> str:
        """Get category name for asset grouping."""
        if asset.asset_format and asset.asset_format.platform:
            return asset.asset_format.platform.name
        elif asset.asset_format:
            return asset.asset_format.name or "custom"
        else:
            return "generated"

    def _generate_presigned_url(self, file_path: str) -> str:
        """Generate a presigned URL for file download."""
        # For local storage, create a simple download URL
        # In production, this would be an S3 presigned URL
        
        filename = Path(file_path).name
        
        # Store file info for later retrieval (simple approach)
        # In production, use Redis or database for temporary storage
        download_id = self._create_download_token(file_path)
        
        # Use the base URL to create full URL
        base_url = getattr(self, 'base_url', 'http://localhost:8000')
        return f"{base_url}{settings.API_V1_STR}/download/file/{download_id}/{filename}"

    def _create_download_token(self, file_path: str) -> str:
        """Create a temporary download token."""
        import hashlib
        import time
        
        # Simple token generation (in production, use proper token management)
        token_data = f"{file_path}:{time.time()}"
        token = hashlib.md5(token_data.encode()).hexdigest()
        
        # Store mapping using class variable for persistence across instances
        DownloadService._download_tokens[token] = {
            'file_path': file_path,
            'created_at': datetime.now(),
            'expires_at': datetime.now() + timedelta(hours=1)
        }
        
        return token

    def get_download_file(self, token: str) -> str:
        """Get file path from download token."""
        token_info = DownloadService._download_tokens.get(token)
        if not token_info:
            raise NotFoundError("Download token not found")
        
        # Token expiry disabled for now
        # if datetime.now() > token_info['expires_at']:
        #     del DownloadService._download_tokens[token]
        #     raise NotFoundError("Download token expired")
        
        return token_info['file_path']