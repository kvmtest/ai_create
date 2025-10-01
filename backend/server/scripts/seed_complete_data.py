#!/usr/bin/env python3
"""
Complete Database Seeding Script for AI CREAT Backend
Populates all necessary data for demo and testing
"""
import sys
from pathlib import Path
import uuid
import json
from datetime import datetime

# Add the project root directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.core.security import get_password_hash
from app.models.user import User
from app.models.admin import Platform, AssetFormat, TextStyleSet, AppSetting
from app.models.enums import UserRole, PlatformType
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_users(db):
    """Create sample users"""
    logger.info("Creating users...")
    
    # Admin user
    admin_user = User(
        username="admin",
        email="admin@example.com",
        hashed_password=get_password_hash("admin123"),
        role=UserRole.ADMIN,
        preferences={"theme": "dark"}
    )
    
    # Regular users
    users = [
        User(
            username="john_doe",
            email="john@example.com", 
            hashed_password=get_password_hash("password123"),
            role=UserRole.USER,
            preferences={"theme": "light"}
        ),
        User(
            username="jane_smith",
            email="jane@example.com",
            hashed_password=get_password_hash("password123"), 
            role=UserRole.USER,
            preferences={"theme": "dark"}
        )
    ]
    
    db.add(admin_user)
    for user in users:
        db.add(user)
    
    db.commit()
    logger.info(f"Created {len(users) + 1} users")
    return admin_user.id

def create_platforms(db, admin_id):
    """Create unified platforms"""
    logger.info("Creating platforms...")
    
    platforms_data = [
        # Repurposing platforms (social media)
        {"name": "Instagram", "type": PlatformType.REPURPOSING, "admin_id": admin_id},
        {"name": "Facebook", "type": PlatformType.REPURPOSING, "admin_id": admin_id}, 
        {"name": "Twitter", "type": PlatformType.REPURPOSING, "admin_id": admin_id},
        {"name": "LinkedIn", "type": PlatformType.REPURPOSING, "admin_id": admin_id},
        {"name": "YouTube", "type": PlatformType.REPURPOSING, "admin_id": admin_id},
        {"name": "TikTok", "type": PlatformType.REPURPOSING, "admin_id": admin_id},
        {"name": "Pinterest", "type": PlatformType.REPURPOSING, "admin_id": admin_id},
        # Resizing platforms (general categories)
        {"name": "Mobile", "type": PlatformType.RESIZING, "admin_id": admin_id},
        {"name": "Web", "type": PlatformType.RESIZING, "admin_id": admin_id},
        {"name": "Custom", "type": PlatformType.RESIZING, "admin_id": admin_id}
    ]
    
    platforms = []
    for platform_data in platforms_data:
        platform = Platform(
            name=platform_data["name"],
            type=platform_data["type"],
            is_active=True,
            created_by_admin_id=platform_data["admin_id"]
        )
        db.add(platform)
        platforms.append(platform)
    
    db.commit()
    logger.info(f"Created {len(platforms)} platforms")
    return platforms

def create_formats(db, admin_id, platforms):
    """Create asset formats"""
    logger.info("Creating asset formats...")
    
    # Create platform mapping
    platform_map = {p.name: p.id for p in platforms}
    
    # All formats unified - each format belongs to a platform
    formats_data = [
        # Mobile platform formats
        {"name": "Mobile Portrait", "platform": "Mobile", "width": 1080, "height": 1920},
        {"name": "Mobile Landscape", "platform": "Mobile", "width": 1920, "height": 1080},
        
        # Web platform formats
        {"name": "Desktop Banner", "platform": "Web", "width": 1200, "height": 400},
        {"name": "Square Thumbnail", "platform": "Web", "width": 400, "height": 400},
        {"name": "Wide Banner", "platform": "Web", "width": 1584, "height": 396},
        
        # Custom platform formats
        {"name": "Custom Large", "platform": "Custom", "width": 2000, "height": 1200},
        
        # Instagram formats
        {"name": "Instagram Post", "platform": "Instagram", "width": 1080, "height": 1080},
        {"name": "Instagram Story", "platform": "Instagram", "width": 1080, "height": 1920},
        {"name": "Instagram Reel", "platform": "Instagram", "width": 1080, "height": 1920},
        
        # Facebook formats
        {"name": "Facebook Post", "platform": "Facebook", "width": 1200, "height": 630},
        {"name": "Facebook Cover", "platform": "Facebook", "width": 1640, "height": 859},
        {"name": "Facebook Story", "platform": "Facebook", "width": 1080, "height": 1920},
        
        # Twitter formats
        {"name": "Twitter Post", "platform": "Twitter", "width": 1024, "height": 512},
        {"name": "Twitter Header", "platform": "Twitter", "width": 1500, "height": 500},
        
        # LinkedIn formats
        {"name": "LinkedIn Post", "platform": "LinkedIn", "width": 1200, "height": 627},
        {"name": "LinkedIn Cover", "platform": "LinkedIn", "width": 1584, "height": 396},
        
        # YouTube formats
        {"name": "YouTube Thumbnail", "platform": "YouTube", "width": 1280, "height": 720},
        {"name": "YouTube Channel Art", "platform": "YouTube", "width": 2560, "height": 1440},
        
        # TikTok formats
        {"name": "TikTok Video", "platform": "TikTok", "width": 1080, "height": 1920},
        
        # Pinterest formats
        {"name": "Pinterest Pin", "platform": "Pinterest", "width": 1000, "height": 1500}
    ]
    
    formats = []
    
    # Create all formats
    for format_data in formats_data:
        format_obj = AssetFormat(
            name=format_data["name"],
            platform_id=platform_map[format_data["platform"]],
            width=format_data["width"],
            height=format_data["height"],
            is_active=True,
            created_by_admin_id=admin_id
        )
        db.add(format_obj)
        formats.append(format_obj)
    
    db.commit()
    logger.info(f"Created {len(formats)} asset formats")

def create_text_style_sets(db, admin_id):
    """Create text style sets"""
    logger.info("Creating text style sets...")
    
    style_sets_data = [
        {
            "name": "Brand Kit Primary",
            "styles": {
                "title": {
                    "fontFamily": "Inter",
                    "fontSize": 48,
                    "fontWeight": "bold",
                    "color": "#000000"
                },
                "subtitle": {
                    "fontFamily": "Inter", 
                    "fontSize": 24,
                    "fontWeight": "medium",
                    "color": "#333333"
                },
                "content": {
                    "fontFamily": "Inter",
                    "fontSize": 16,
                    "fontWeight": "regular",
                    "color": "#666666"
                }
            }
        },
        {
            "name": "Marketing Campaign",
            "styles": {
                "title": {
                    "fontFamily": "Roboto",
                    "fontSize": 52,
                    "fontWeight": "bold",
                    "color": "#FF4757"
                },
                "subtitle": {
                    "fontFamily": "Roboto",
                    "fontSize": 28,
                    "fontWeight": "medium", 
                    "color": "#2F3542"
                },
                "content": {
                    "fontFamily": "Roboto",
                    "fontSize": 18,
                    "fontWeight": "regular",
                    "color": "#57606F"
                }
            }
        },
        {
            "name": "Elegant Minimal",
            "styles": {
                "title": {
                    "fontFamily": "Playfair Display",
                    "fontSize": 44,
                    "fontWeight": "bold",
                    "color": "#2C3E50"
                },
                "subtitle": {
                    "fontFamily": "Open Sans",
                    "fontSize": 22,
                    "fontWeight": "medium",
                    "color": "#34495E"
                },
                "content": {
                    "fontFamily": "Open Sans", 
                    "fontSize": 14,
                    "fontWeight": "regular",
                    "color": "#7F8C8D"
                }
            }
        }
    ]
    
    style_sets = []
    for style_data in style_sets_data:
        style_set = TextStyleSet(
            name=style_data["name"],
            styles=style_data["styles"],
            is_active=True,
            created_by_admin_id=admin_id
        )
        db.add(style_set)
        style_sets.append(style_set)
    
    db.commit()
    logger.info(f"Created {len(style_sets)} text style sets")

def create_app_settings(db):
    """Create application settings"""
    logger.info("Creating application settings...")
    
    settings_data = [
        {
            "rule_key": "adaptation_rules",
            "rule_value": {
                "focalPointLogic": "face-centric & product-centric",
                "layoutGuidance": {
                    "safeZone": {
                        "top": 0.1,
                        "bottom": 0.1,
                        "left": 0.1,
                        "right": 0.1
                    },
                    "logoSize": 0.15
                }
            },
            "description": "Image template rules and adaptation settings"
        },
        {
            "rule_key": "ai_behavior_rules",
            "rule_value": {
                "adaptationStrategy": "extend-canvas",
                "imageQuality": "high"
            },
            "description": "AI behavior controls and settings"
        },
        {
            "rule_key": "upload_moderation_rules",
            "rule_value": {
                "allowedImageTypes": ["jpeg", "png", "psd","jpg","webp"],
                "maxFileSizeMb": 50,
                "nsfwAlertsActive": True
            },
            "description": "Content moderation and upload rules"
        },
        {
            "rule_key": "manual_editing_rules",
            "rule_value": {
                "editingEnabled": True,
                "croppingEnabled": True,
                "saturationEnabled": True,
                "addTextOrLogoEnabled": True,
                "allowedLogoSources": {
                    "types": ["png", "jpeg"],
                    "maxSizeMb": 5
                }
            },
            "description": "Manual editing rules for users"
        }
    ]
    
    app_settings = []
    for setting_data in settings_data:
        setting = AppSetting(
            rule_key=setting_data["rule_key"],
            rule_value=setting_data["rule_value"],
            description=setting_data["description"]
        )
        db.add(setting)
        app_settings.append(setting)
    
    db.commit()
    logger.info(f"Created {len(app_settings)} application settings")

def main():
    """Main seeding function"""
    try:
        # Create database connection
        engine = create_engine(settings.DATABASE_URL)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        
        with SessionLocal() as db:
            logger.info("Starting database seeding...")
            
            # Create users first
            admin_id = create_users(db)
            
            # Create platforms
            platforms = create_platforms(db, admin_id)
            
            # Create formats
            create_formats(db, admin_id, platforms)
            
            # Create text style sets
            create_text_style_sets(db, admin_id)
            
            # Create app settings
            create_app_settings(db)
            
            logger.info("Database seeding completed successfully!")
            print("\n" + "="*50)
            print("DATABASE SEEDED SUCCESSFULLY!")
            print("="*50)
            print("Admin Login:")
            print("  Username: admin")
            print("  Password: admin123")
            print("\nRegular User Logins:")
            print("  Username: john_doe, Password: password123")
            print("  Username: jane_smith, Password: password123")
            print("="*50)
            
    except Exception as e:
        logger.error(f"Error during seeding: {e}")
        raise

if __name__ == "__main__":
    main()
