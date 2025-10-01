"""
AI CREAT Backend - Main FastAPI Application
Matching OpenAPI specification v1.1.0
"""
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from app.core.config import settings
from app.core.middleware import (
    LoggingMiddleware, SecurityHeadersMiddleware, 
    RateLimitMiddleware, RequestValidationMiddleware
)
from app.api.v1.api import api_router
from app.core.exceptions import NotFoundError, ValidationError as CustomValidationError
import structlog
import time

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# Create FastAPI app matching OpenAPI specification
app = FastAPI(
    title="AI CREAT - API Specification",
    description="API for the AI CREAT application, enabling users to upload, process, and generate creative assets, and allowing admins to manage the platform's rules and templates.",
    version="1.1.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc"
)

# Add custom middleware in correct order (last added = first executed)
app.add_middleware(LoggingMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware, requests_per_minute=60, requests_per_hour=1000)
app.add_middleware(RequestValidationMiddleware)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["X-Process-Time"]
)

# Global exception handlers
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions with proper error format"""
    logger = structlog.get_logger()
    logger.error(
        "HTTP Exception",
        status_code=exc.status_code,
        detail=exc.detail,
        path=request.url.path,
        method=request.method
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail
        }
    )

@app.exception_handler(StarletteHTTPException)
async def starlette_exception_handler(request: Request, exc: StarletteHTTPException):
    """Handle Starlette HTTP exceptions"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": exc.status_code,
            "message": exc.detail
        }
    )

@app.exception_handler(RequestValidationError)
async def request_validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle request validation errors"""
    logger = structlog.get_logger()
    logger.error(
        "Request Validation Error",
        errors=exc.errors(),
        path=request.url.path,
        method=request.method
    )
    
    # Format validation errors properly - only include loc, msg, type
    error_details = []
    for error in exc.errors():
        # Only include the fields we want
        clean_error = {
            "loc": error["loc"],
            "msg": error["msg"],
            "type": error["type"]
        }
        error_details.append(clean_error)
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": error_details
        }
    )

@app.exception_handler(ValidationError)
async def validation_exception_handler(request: Request, exc: ValidationError):
    """Handle Pydantic validation errors"""
    logger = structlog.get_logger()
    logger.error(
        "Validation Error",
        errors=exc.errors(),
        path=request.url.path,
        method=request.method
    )
    
    # Format validation errors properly - only include loc, msg, type
    error_details = []
    for error in exc.errors():
        # Only include the fields we want
        clean_error = {
            "loc": error["loc"],
            "msg": error["msg"],
            "type": error["type"]
        }
        error_details.append(clean_error)
    
    return JSONResponse(
        status_code=422,
        content={
            "detail": error_details
        }
    )

@app.exception_handler(CustomValidationError)
async def custom_validation_exception_handler(request: Request, exc: CustomValidationError):
    """Handle custom validation errors"""
    return JSONResponse(
        status_code=422,
        content={
            "detail": [
                {
                    "loc": ["body", "styles"],
                    "msg": str(exc),
                    "type": "validation_error"
                }
            ]
        }
    )

@app.exception_handler(NotFoundError)
async def not_found_exception_handler(request: Request, exc: NotFoundError):
    """Handle not found errors"""
    return JSONResponse(
        status_code=404,
        content={
            "code": 404,
            "message": str(exc)
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """Handle unexpected exceptions"""
    logger = structlog.get_logger()
    logger.error(
        "Unexpected Error",
        error=str(exc),
        error_type=type(exc).__name__,
        path=request.url.path,
        method=request.method
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "Internal server error"
        }
    )

# Include API router with proper prefix
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "AI CREAT API",
        "version": "1.1.0",
        "status": "active",
        "docs_url": f"{settings.API_V1_STR}/docs"
    }

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "version": "1.1.0"
    }

@app.on_event("startup")
async def startup_event():
    """Application startup event"""
    logger = structlog.get_logger()
    logger.info(
        "AI CREAT Backend starting up",
        version="1.1.0",
        api_prefix=settings.API_V1_STR,
        cors_origins=settings.CORS_ORIGINS
    )
    
    # Initialize AI providers
    try:
        from app.services.ai_providers import ai_manager
        health_status = ai_manager.health_check()
        logger.info("AI Providers initialized", health_status=health_status)
    except Exception as e:
        logger.warning("AI Providers initialization failed", error=str(e))

@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown event"""
    logger = structlog.get_logger()
    logger.info("AI CREAT Backend shutting down")