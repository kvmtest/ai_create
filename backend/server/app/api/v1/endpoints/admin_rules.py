"""
Admin endpoints for managing rules and controls
"""
from typing import List, Optional, Dict, Any
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_user, require_admin
from app.models.user import User
from app.models.enums import PlatformType
from app.services.admin import AdminService
from app.schemas.admin import (
    AdaptationRule, AIBehaviorRule, UploadModerationRule, ManualEditingRule
)
from app.core.exceptions import NotFoundError, ValidationError

router = APIRouter()


# Rules and Controls Endpoints
@router.get("/rules/adaptation", response_model=AdaptationRule)
async def get_adaptation_rules(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get Image Template Rules and Adaptation Settings"""
    admin_service = AdminService(db)
    return admin_service.get_adaptation_rules()


@router.put("/rules/adaptation", response_model=AdaptationRule)
async def update_adaptation_rules(
    rules: AdaptationRule,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update Image Template Rules and Adaptation Settings"""
    admin_service = AdminService(db)
    return admin_service.update_adaptation_rules(rules.dict())


@router.get("/rules/ai-behavior", response_model=AIBehaviorRule)
async def get_ai_behavior_rules(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get AI Behavior Controls"""
    admin_service = AdminService(db)
    return admin_service.get_ai_behavior_rules()


@router.put("/rules/ai-behavior", response_model=AIBehaviorRule)
async def update_ai_behavior_rules(
    rules: AIBehaviorRule,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update AI Behavior Controls"""
    admin_service = AdminService(db)
    return admin_service.update_ai_behavior_rules(rules.dict())


@router.get("/rules/upload-moderation", response_model=UploadModerationRule)
async def get_upload_moderation_rules(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get Content Moderation and Upload Rules"""
    admin_service = AdminService(db)
    return admin_service.get_upload_moderation_rules()


@router.put("/rules/upload-moderation", response_model=UploadModerationRule)
async def update_upload_moderation_rules(
    rules: UploadModerationRule,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update Content Moderation and Upload Rules"""
    admin_service = AdminService(db)
    return admin_service.update_upload_moderation_rules(rules.dict())


@router.get("/rules/manual-editing", response_model=ManualEditingRule)
async def get_manual_editing_rules(
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get Manual Editing Rules for Users"""
    admin_service = AdminService(db)
    return admin_service.get_manual_editing_rules()


@router.put("/rules/manual-editing", response_model=ManualEditingRule)
async def update_manual_editing_rules(
    rules: ManualEditingRule,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update Manual Editing Rules for Users"""
    admin_service = AdminService(db)
    return admin_service.update_manual_editing_rules(rules.dict())
