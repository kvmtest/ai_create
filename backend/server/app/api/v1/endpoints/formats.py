"""
Formats endpoints - matching OpenAPI specification
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Dict, List
from app.db.session import get_db
from app.services.format import FormatService
from app.core.deps import get_current_user
from app.models.user import User
from pydantic import BaseModel

router = APIRouter()


class AssetFormatResponse(BaseModel):
    id: str
    name: str
    platformId: str
    platformName: str
    width: int
    height: int

    class Config:
        from_attributes = True


@router.get("/formats")
async def get_all_available_formats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
) -> Dict[str, List[AssetFormatResponse]]:
    """
    Get all available asset formats for users - matches OpenAPI spec
    """
    format_service = FormatService(db)
    formats = format_service.get_all_active_formats()
    
    result = {
        "resizing": [],
        "repurposing": []
    }
    
    for format_item in formats["resizing"]:
        result["resizing"].append(AssetFormatResponse(
            id=str(format_item.id),
            name=format_item.name,
            platformId=str(format_item.platform_id),
            platformName=format_item.platform.name,
            width=format_item.width,
            height=format_item.height
        ))
    
    for format_item in formats["repurposing"]:
        result["repurposing"].append(AssetFormatResponse(
            id=str(format_item.id),
            name=format_item.name,
            platformId=str(format_item.platform_id),
            platformName=format_item.platform.name,
            width=format_item.width,
            height=format_item.height
        ))
    
    return result