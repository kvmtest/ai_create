"""
Format service for managing asset formats
"""
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from app.models.admin import AssetFormat, Platform
from app.models.enums import PlatformType
import structlog

logger = structlog.get_logger()


class FormatService:
    def __init__(self, db: Session):
        self.db = db

    def get_all_active_formats(self) -> Dict[str, List[AssetFormat]]:
        """Get all active formats grouped by platform type"""
        logger.info("get_all_active_formats called")
        from sqlalchemy.orm import joinedload
        
        formats = (
            self.db.query(AssetFormat)
            .join(Platform)
            .options(joinedload(AssetFormat.platform))
            .filter(AssetFormat.is_active == True)
            .filter(Platform.is_active == True)
            .all()
        )
        
        result = {
            "resizing": [],
            "repurposing": []
        }
        
        for format_item in formats:
            if format_item.platform.type == PlatformType.RESIZING:
                result["resizing"].append(format_item)
            elif format_item.platform.type == PlatformType.REPURPOSING:
                result["repurposing"].append(format_item)
        
        logger.info(
            "active formats grouped",
            total=len(formats),
            resizing=len(result["resizing"]),
            repurposing=len(result["repurposing"]),
        )
        return result