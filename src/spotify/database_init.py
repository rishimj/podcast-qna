"""
Database configuration and session management
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from contextlib import contextmanager
from typing import Generator

from src.spotify.utils.logging import get_logger
from src.spotify.models import Base

logger = get_logger(__name__)

# Database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./podcast_qa.db")

# Create engine
if DATABASE_URL.startswith("sqlite"):
    # SQLite specific settings
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False}
    )
else:
    # PostgreSQL settings
    engine = create_engine(
        DATABASE_URL,
        pool_size=int(os.getenv("DATABASE_POOL_SIZE", "20")),
        max_overflow=int(os.getenv("DATABASE_MAX_OVERFLOW", "40")),
        pool_pre_ping=True,
        echo=os.getenv("DEBUG", "false").lower() == "true"
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """
    Dependency to get database session
    
    Yields:
        Database session
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_session() -> Generator[Session, None, None]:
    """
    Context manager for database session
    
    Usage:
        with get_db_session() as db:
            db.query(Model).all()
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Initialize database tables"""
    from src.auth import User  # Import models
    from src.spotify.models import (
        SpotifyConnection, UserPodcast, 
        UserPodcastEpisode, SpotifyAPICall
    )
    from src.cost_tracker import CostTracking
    
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")


def reset_db() -> None:
    """Reset database (WARNING: Destroys all data)"""
    logger.warning("Dropping all database tables...")
    Base.metadata.drop_all(bind=engine)
    logger.info("Creating fresh database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database reset complete")


if __name__ == "__main__":
    # Initialize database when run directly
    init_db()
