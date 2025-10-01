"""
Custom middleware for the application
"""
import time
import asyncio
from collections import defaultdict, deque
from typing import Dict, Deque
from fastapi import Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
import structlog
import re

logger = structlog.get_logger()


class LoggingMiddleware(BaseHTTPMiddleware):
    """Middleware for request/response logging"""
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start_time = time.time()
        
        # Get client IP (handle proxy headers)
        client_ip = self._get_client_ip(request)
        
        # Log request
        logger.info(
            "Request started",
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            client_ip=client_ip,
            user_agent=request.headers.get("user-agent", ""),
        )
        
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log response
        logger.info(
            "Request completed",
            method=request.method,
            url=str(request.url),
            path=request.url.path,
            status_code=response.status_code,
            process_time=round(process_time, 4),
            client_ip=client_ip,
        )
        
        # Add processing time header
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, handling proxy headers"""
        # Check for forwarded headers (in order of preference)
        forwarded_headers = [
            "X-Forwarded-For",
            "X-Real-IP",
            "CF-Connecting-IP",  # Cloudflare
            "X-Client-IP"
        ]
        
        for header in forwarded_headers:
            if header in request.headers:
                # Take the first IP in case of comma-separated list
                ip = request.headers[header].split(",")[0].strip()
                if ip:
                    return ip
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware for adding comprehensive security headers"""
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        
        # Security headers
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
        
        # Content Security Policy
        csp = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "img-src 'self' data: https:; "
            "font-src 'self' https://cdn.jsdelivr.net; "
            "connect-src 'self'; "
            "frame-ancestors 'none'"
        )
        response.headers["Content-Security-Policy"] = csp
        
        # HSTS (only for HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiting middleware with sliding window algorithm"""
    
    def __init__(self, app, requests_per_minute: int = 60, requests_per_hour: int = 1000):
        super().__init__(app)
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        
        # Storage for rate limiting (in production, use Redis)
        self.minute_windows: Dict[str, Deque[float]] = defaultdict(deque)
        self.hour_windows: Dict[str, Deque[float]] = defaultdict(deque)
        
        # Different limits for different endpoint types
        self.endpoint_limits = {
            "/auth/login": {"per_minute": 5, "per_hour": 20},  # Stricter for auth
            "/projects/upload": {"per_minute": 10, "per_hour": 100},  # File uploads
            "/generate": {"per_minute": 20, "per_hour": 200},  # Generation requests
            "/admin/": {"per_minute": 100, "per_hour": 1000},  # Admin endpoints
        }
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip rate limiting for health checks and static files
        if request.url.path in ["/health", "/", "/docs", "/redoc", "/openapi.json"]:
            return await call_next(request)
        
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        
        # Get limits for this endpoint
        limits = self._get_endpoint_limits(request.url.path)
        
        # Check rate limits
        if not self._check_rate_limit(client_ip, current_time, limits):
            logger.warning(
                "Rate limit exceeded",
                client_ip=client_ip,
                path=request.url.path,
                method=request.method
            )
            
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={"Retry-After": "60"}
            )
        
        # Record this request
        self._record_request(client_ip, current_time)
        
        response = await call_next(request)
        
        # Add rate limit headers
        remaining_minute = limits["per_minute"] - len(self.minute_windows[client_ip])
        remaining_hour = limits["per_hour"] - len(self.hour_windows[client_ip])
        
        response.headers["X-RateLimit-Limit-Minute"] = str(limits["per_minute"])
        response.headers["X-RateLimit-Remaining-Minute"] = str(max(0, remaining_minute))
        response.headers["X-RateLimit-Limit-Hour"] = str(limits["per_hour"])
        response.headers["X-RateLimit-Remaining-Hour"] = str(max(0, remaining_hour))
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address"""
        # Same logic as LoggingMiddleware
        forwarded_headers = ["X-Forwarded-For", "X-Real-IP", "CF-Connecting-IP", "X-Client-IP"]
        
        for header in forwarded_headers:
            if header in request.headers:
                ip = request.headers[header].split(",")[0].strip()
                if ip:
                    return ip
        
        return request.client.host if request.client else "unknown"
    
    def _get_endpoint_limits(self, path: str) -> Dict[str, int]:
        """Get rate limits for specific endpoint"""
        # Check for specific endpoint patterns
        for pattern, limits in self.endpoint_limits.items():
            if path.startswith(pattern):
                return limits
        
        # Default limits
        return {
            "per_minute": self.requests_per_minute,
            "per_hour": self.requests_per_hour
        }
    
    def _check_rate_limit(self, client_ip: str, current_time: float, limits: Dict[str, int]) -> bool:
        """Check if request is within rate limits"""
        # Clean old entries and check minute window
        minute_window = self.minute_windows[client_ip]
        while minute_window and current_time - minute_window[0] > 60:
            minute_window.popleft()
        
        if len(minute_window) >= limits["per_minute"]:
            return False
        
        # Clean old entries and check hour window
        hour_window = self.hour_windows[client_ip]
        while hour_window and current_time - hour_window[0] > 3600:
            hour_window.popleft()
        
        if len(hour_window) >= limits["per_hour"]:
            return False
        
        return True
    
    def _record_request(self, client_ip: str, current_time: float):
        """Record a request for rate limiting"""
        self.minute_windows[client_ip].append(current_time)
        self.hour_windows[client_ip].append(current_time)


class RequestValidationMiddleware(BaseHTTPMiddleware):
    """Middleware for request validation and sanitization"""
    
    def __init__(self, app):
        super().__init__(app)
        
        # Suspicious patterns to detect potential attacks
        self.suspicious_patterns = [
            re.compile(r'<script[^>]*>.*?</script>', re.IGNORECASE | re.DOTALL),  # XSS
            re.compile(r'javascript:', re.IGNORECASE),  # JavaScript injection
            re.compile(r'on\w+\s*=', re.IGNORECASE),  # Event handlers
            re.compile(r'(union|select|insert|update|delete|drop|create|alter)\s+', re.IGNORECASE),  # SQL injection
            re.compile(r'\.\./', re.IGNORECASE),  # Path traversal
            re.compile(r'%2e%2e%2f', re.IGNORECASE),  # Encoded path traversal
        ]
    
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Validate request size
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 100 * 1024 * 1024:  # 100MB limit
            raise HTTPException(
                status_code=413,
                detail="Request entity too large"
            )
        
        # Validate content type for POST/PUT requests (skip for certain endpoints)
        if request.method in ["POST", "PUT", "PATCH"]:
            # Skip content type validation for endpoints that don't require content
            skip_content_validation = [
                "/api/v1/auth/logout",  # Logout endpoint only needs Authorization header
                "/health",              # General health check
                "/api/v1/",            # API info endpoint
            ]
            
            if request.url.path not in skip_content_validation:
                content_type = request.headers.get("content-type", "")
                if not self._is_valid_content_type(content_type, request.url.path):
                    raise HTTPException(
                        status_code=415,
                        detail="Unsupported media type"
                    )
        
        # Check for suspicious patterns in URL
        if self._contains_suspicious_content(str(request.url)):
            logger.warning(
                "Suspicious request detected",
                url=str(request.url),
                client_ip=request.client.host if request.client else "unknown"
            )
            raise HTTPException(
                status_code=400,
                detail="Invalid request"
            )
        
        return await call_next(request)
    
    def _is_valid_content_type(self, content_type: str, path: str) -> bool:
        """Validate content type for the request"""
        # Allow empty content type for certain auth endpoints (they only use headers)
        if not content_type.strip() and any(auth_path in path for auth_path in ["/auth/logout"]):
            return True
            
        # Allow multipart for file uploads
        if "/upload" in path and content_type.startswith("multipart/form-data"):
            return True
        
        # Allow JSON for API endpoints
        if content_type.startswith("application/json"):
            return True
        
        # Allow form data for some endpoints
        if content_type.startswith("application/x-www-form-urlencoded"):
            return True
        
        return False
    
    def _contains_suspicious_content(self, content: str) -> bool:
        """Check if content contains suspicious patterns"""
        for pattern in self.suspicious_patterns:
            if pattern.search(content):
                return True
        return False