"""
Main API router for v1 endpoints - matching OpenAPI specification
"""
from fastapi import APIRouter
from app.api.v1.endpoints import auth, users, projects, formats, generation, admin_platforms, admin_rules, download

api_router = APIRouter()

# Include routers matching OpenAPI structure
api_router.include_router(auth.router, prefix="/auth", tags=["Authentication"])
api_router.include_router(users.router, prefix="/users", tags=["Authentication"])
api_router.include_router(projects.router, tags=["Projects & Assets"])
api_router.include_router(formats.router, tags=["User - Formats"])
api_router.include_router(generation.router, tags=["Generation"])
api_router.include_router(download.router, tags=["Generation"])

api_router.include_router(admin_platforms.router, prefix="/admin", tags=["Admin - Formats & Platforms"])
api_router.include_router(admin_rules.router, prefix="/admin", tags=["Admin - Rules & Controls"])

@api_router.get("/")
async def api_info():
    return {"message": "AI CREAT API v1", "status": "active"}