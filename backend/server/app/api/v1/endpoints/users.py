"""
User management endpoints - matching OpenAPI specification
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.services.auth import AuthService
from app.core.deps import get_current_user
from app.models.user import User
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


class PreferencesUpdate(BaseModel):
    theme: Optional[str] = None


@router.put("/me/preferences")
async def update_user_preferences(
    preferences: PreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Update User Preferences - matches OpenAPI spec
    """
    auth_service = AuthService(db)
    
    # Update preferences with the theme setting
    updated_preferences = current_user.preferences.copy() if current_user.preferences else {}
    if preferences.theme is not None:
        updated_preferences["theme"] = preferences.theme
    
    user = auth_service.update_user_preferences(
        user=current_user,
        preferences=updated_preferences
    )
    
    return {"preferences" : user.preferences}