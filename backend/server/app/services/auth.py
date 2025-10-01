"""
Authentication service
"""
from typing import Optional
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.blacklisted_token import BlacklistedToken
from app.schemas.user import UserCreate
from app.core.security import verify_password, get_password_hash, create_access_token, get_token_expiry
from datetime import timedelta, datetime
from app.core.config import settings
import structlog

logger = structlog.get_logger()


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def authenticate_user(self, username: str, password: str) -> Optional[User]:
        """Authenticate user with username and password"""
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            logger.warning("Authentication failed", username=username)
            return None
        if not verify_password(password, user.hashed_password):
            logger.warning("Authentication failed", username=username)
            return None
        logger.info(
            "User authenticated",
            username=username
        )
        return user

    def create_user(self, user_create: UserCreate) -> User:
        """Create a new user"""
        hashed_password = get_password_hash(user_create.password)
        db_user = User(
            username=user_create.username,
            email=user_create.email,
            hashed_password=hashed_password,
            role=user_create.role,
        )
        self.db.add(db_user)
        self.db.commit()
        self.db.refresh(db_user)
        logger.info(
            "User created",
            user_id=str(db_user.id),
            username=db_user.username
        )
        return db_user

    def get_user_by_username(self, username: str) -> Optional[User]:
        """Get user by username"""
        return self.db.query(User).filter(User.username == username).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        """Get user by email"""
        return self.db.query(User).filter(User.email == email).first()

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get user by ID"""
        return self.db.query(User).filter(User.id == user_id).first()

    def create_access_token_for_user(self, user: User) -> str:
        """Create access token for user"""
        access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={"sub": user.username}, expires_delta=access_token_expires
        )
        logger.info(
            "Access token created",
            user_id=str(user.id),
            expires_in_minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
        return access_token

    def update_user_preferences(self, user: User, preferences: dict) -> User:
        """Update user preferences"""
        user.preferences = preferences
        self.db.commit()
        self.db.refresh(user)
        logger.info(
            "User preferences updated",
            user_id=str(user.id)
        )
        return user

    def blacklist_token(self, token: str, user: User) -> BlacklistedToken:
        """Add token to blacklist"""
        # Get token expiry
        expires_at = get_token_expiry(token)
        if expires_at is None:
            # If we can't get expiry, set it to a reasonable default
            expires_at = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        
        blacklisted_token = BlacklistedToken(
            token=token,
            user_id=user.id,
            expires_at=expires_at
        )
        
        self.db.add(blacklisted_token)
        self.db.commit()
        self.db.refresh(blacklisted_token)
        
        logger.info(
            "Token blacklisted",
            user_id=str(user.id),
            expires_at=expires_at.isoformat()
        )
        
        return blacklisted_token
    
    def cleanup_expired_tokens(self) -> int:
        """Remove expired blacklisted tokens"""
        expired_count = self.db.query(BlacklistedToken).filter(
            BlacklistedToken.expires_at < datetime.utcnow()
        ).delete()
        
        self.db.commit()
        
        if expired_count > 0:
            logger.info("Cleaned up expired blacklisted tokens", count=expired_count)
        
        return expired_count