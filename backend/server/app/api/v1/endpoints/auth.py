"""
Authentication endpoints - matching OpenAPI specification
"""
from fastapi import APIRouter, Depends, HTTPException, status, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.schemas.user import UserLogin
from app.services.auth import AuthService
from app.core.deps import get_current_user, security
from app.models.user import User

router = APIRouter()


@router.post("/login")
async def login(
    user_credentials: UserLogin,
    db: Session = Depends(get_db)
):
    """
    User Login - matches OpenAPI spec
    """
    auth_service = AuthService(db)
    user = auth_service.authenticate_user(
        username=user_credentials.username,
        password=user_credentials.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    
    access_token = auth_service.create_access_token_for_user(user)
    return {"accessToken": access_token}


@router.post("/logout", status_code=204)
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    User Logout - matches OpenAPI spec
    Returns 204 No Content as specified
    Blacklists the JWT token to prevent further use
    """
    # Get the token from credentials
    token = credentials.credentials
    
    # Blacklist the token
    auth_service = AuthService(db)
    auth_service.blacklist_token(token, current_user)
    
    return Response(status_code=204)