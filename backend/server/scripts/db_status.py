#!/usr/bin/env python3
"""
Database status script for AI CREAT Backend

This script shows the current status of the database.
"""
import sys
from pathlib import Path

# Add the app directory to the Python path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import create_engine, text
from app.core.config import settings
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_database_connection():
    """Check if database connection is working"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1"))
            result.fetchone()
        
        engine.dispose()
        logger.info("✓ Database connection: OK")
        return True
        
    except Exception as e:
        logger.error(f"✗ Database connection: FAILED - {e}")
        return False


def check_tables():
    """Check if all required tables exist"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        required_tables = [
            'users', 'projects', 'assets', 'platforms',
            'asset_formats', 'text_style_sets', 'app_settings',
            'generation_jobs', 'generated_assets'
        ]
        
        with engine.connect() as conn:
            existing_tables = []
            missing_tables = []
            
            for table in required_tables:
                result = conn.execute(
                    text(
                        "SELECT EXISTS (SELECT FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_name = :table_name)"
                    ),
                    {"table_name": table}
                )
                
                if result.fetchone()[0]:
                    existing_tables.append(table)
                else:
                    missing_tables.append(table)
        
        engine.dispose()
        
        logger.info(f"✓ Tables found: {len(existing_tables)}/{len(required_tables)}")
        
        if missing_tables:
            logger.warning(f"✗ Missing tables: {', '.join(missing_tables)}")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Table check: FAILED - {e}")
        return False


def check_data():
    """Check if initial data exists"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check platforms
            platform_count = conn.execute(
                text("SELECT COUNT(*) FROM platforms")
            ).fetchone()[0]
            
            # Check formats
            format_count = conn.execute(
                text("SELECT COUNT(*) FROM asset_formats")
            ).fetchone()[0]
            
            # Check settings
            settings_count = conn.execute(
                text("SELECT COUNT(*) FROM app_settings")
            ).fetchone()[0]
            
            # Check text styles
            styles_count = conn.execute(
                text("SELECT COUNT(*) FROM text_style_sets")
            ).fetchone()[0]
            
            # Check users
            user_count = conn.execute(
                text("SELECT COUNT(*) FROM users")
            ).fetchone()[0]
            
            # Check admin users
            admin_count = conn.execute(
                text("SELECT COUNT(*) FROM users WHERE role = 'admin'")
            ).fetchone()[0]
        
        engine.dispose()
        
        logger.info(f"✓ Repurposing platforms: {platform_count}")
        logger.info(f"✓ Asset formats: {format_count}")
        logger.info(f"✓ App settings: {settings_count}")
        logger.info(f"✓ Text style sets: {styles_count}")
        logger.info(f"✓ Total users: {user_count}")
        logger.info(f"✓ Admin users: {admin_count}")
        
        # Check if we have minimum required data
        if platform_count == 0:
            logger.warning("✗ No repurposing platforms found")
            return False
        
        if format_count == 0:
            logger.warning("✗ No asset formats found")
            return False
        
        if settings_count == 0:
            logger.warning("✗ No app settings found")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"✗ Data check: FAILED - {e}")
        return False


def check_migrations():
    """Check migration status"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Check if alembic_version table exists
            result = conn.execute(
                text(
                    "SELECT EXISTS (SELECT FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_name = 'alembic_version')"
                )
            )
            
            if not result.fetchone()[0]:
                logger.warning("✗ Alembic version table not found - migrations may not be initialized")
                return False
            
            # Get current migration version
            result = conn.execute(text("SELECT version_num FROM alembic_version"))
            version = result.fetchone()
            
            if version:
                logger.info(f"✓ Current migration version: {version[0]}")
            else:
                logger.warning("✗ No migration version found")
                return False
        
        engine.dispose()
        return True
        
    except Exception as e:
        logger.error(f"✗ Migration check: FAILED - {e}")
        return False


def show_database_info():
    """Show general database information"""
    try:
        engine = create_engine(settings.DATABASE_URL)
        
        with engine.connect() as conn:
            # Get database size
            result = conn.execute(
                text("SELECT pg_size_pretty(pg_database_size(current_database()))")
            )
            db_size = result.fetchone()[0]
            
            # Get database name
            result = conn.execute(text("SELECT current_database()"))
            db_name = result.fetchone()[0]
            
            # Get PostgreSQL version
            result = conn.execute(text("SELECT version()"))
            pg_version = result.fetchone()[0].split(',')[0]
            
            # Get connection count
            result = conn.execute(
                text("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()")
            )
            connection_count = result.fetchone()[0]
        
        engine.dispose()
        
        logger.info(f"Database name: {db_name}")
        logger.info(f"Database size: {db_size}")
        logger.info(f"PostgreSQL version: {pg_version}")
        logger.info(f"Active connections: {connection_count}")
        
    except Exception as e:
        logger.error(f"Could not retrieve database info: {e}")


def main():
    """Main status check function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Check AI CREAT database status")
    parser.add_argument("--verbose", "-v", action="store_true",
                       help="Show detailed information")
    
    args = parser.parse_args()
    
    logger.info("AI CREAT Database Status Check")
    logger.info("=" * 40)
    
    # Show database info
    if args.verbose:
        show_database_info()
        logger.info("-" * 40)
    
    # Run all checks
    connection_ok = check_database_connection()
    tables_ok = check_tables()
    migrations_ok = check_migrations()
    data_ok = check_data()
    
    logger.info("-" * 40)
    
    if all([connection_ok, tables_ok, migrations_ok, data_ok]):
        logger.info("✓ Overall status: HEALTHY")
        sys.exit(0)
    else:
        logger.error("✗ Overall status: ISSUES DETECTED")
        logger.info("\nTo fix issues, try running:")
        logger.info("  python scripts/init_db.py")
        sys.exit(1)


if __name__ == "__main__":
    main()