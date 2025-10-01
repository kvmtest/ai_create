"""
Common schemas used across the application
"""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: int
    message: str
    details: Optional[Dict[str, Any]] = None
    timestamp: datetime


class SuccessResponse(BaseModel):
    message: str
    data: Optional[Dict[str, Any]] = None


class PaginationParams(BaseModel):
    page: int = 1
    size: int = 20


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int
    size: int
    pages: int