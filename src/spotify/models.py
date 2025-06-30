"""
Database models for Spotify integration with user isolation
"""
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List
from sqlalchemy import (
    Column, String, DateTime, Integer, Text, 
    ForeignKey, UniqueConstraint, Index, JSON, Numeric, Date
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Session
from sqlalchemy.sql import func

from .config import get_spotify_config

Base = declarative_base()


class SpotifyConnection(Base):
    """Store user's Spotify OAuth connection details"""
    __tablename__ = "spotify_connections"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    spotify_user_id = Column(String(255), nullable=False)
    
    # Encrypted tokens
    access_token_encrypted = Column(Text, nullable=False)
    refresh_token_encrypted = Column(Text, nullable=False)
    
    token_expires_at = Column(DateTime(timezone=True), nullable=False)
    scopes = Column(Text, nullable=False)
    
    last_sync_at = Column(DateTime(timezone=True))
    last_sync_error = Column(Text)
    sync_failure_count = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    user = relationship("User", back_populates="spotify_connection")
    podcasts = relationship("UserPodcast", back_populates="connection", cascade="all, delete-orphan")
    
    __table_args__ = (
        Index("idx_token_expiry", "token_expires_at"),
        Index("idx_last_sync", "last_sync_at"),
    )
    
    @property
    def access_token(self) -> str:
        """Decrypt and return access token"""
        config = get_spotify_config()
        return config.fernet.decrypt(self.access_token_encrypted.encode()).decode()
    
    @access_token.setter
    def access_token(self, value: str):
        """Encrypt and store access token"""
        config = get_spotify_config()
        self.access_token_encrypted = config.fernet.encrypt(value.encode()).decode()
    
    @property
    def refresh_token(self) -> str:
        """Decrypt and return refresh token"""
        config = get_spotify_config()
        return config.fernet.decrypt(self.refresh_token_encrypted.encode()).decode()
    
    @refresh_token.setter
    def refresh_token(self, value: str):
        """Encrypt and store refresh token"""
        config = get_spotify_config()
        self.refresh_token_encrypted = config.fernet.encrypt(value.encode()).decode()
    
    @property
    def is_token_expired(self) -> bool:
        """Check if access token has expired"""
        return datetime.utcnow() >= self.token_expires_at
    
    def needs_sync(self, hours: int = 4) -> bool:
        """Check if data needs syncing"""
        if not self.last_sync_at:
            return True
        hours_since_sync = (datetime.utcnow() - self.last_sync_at).total_seconds() / 3600
        return hours_since_sync >= hours


class UserPodcast(Base):
    """Podcasts (shows) that a user has listened to"""
    __tablename__ = "user_podcasts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    connection_id = Column(UUID(as_uuid=True), ForeignKey("spotify_connections.id", ondelete="CASCADE"), nullable=False)
    
    spotify_show_id = Column(String(255), nullable=False)
    show_name = Column(Text, nullable=False)
    show_description = Column(Text)
    publisher = Column(Text)
    total_episodes = Column(Integer)
    language = Column(String(10))
    explicit = Column(String(10))
    
    # URLs and images
    image_url = Column(Text)
    external_urls = Column(JSON)
    
    # Listening stats
    first_listened_at = Column(DateTime(timezone=True))
    last_listened_at = Column(DateTime(timezone=True))
    total_episodes_played = Column(Integer, default=0)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    
    # Relationships
    connection = relationship("SpotifyConnection", back_populates="podcasts")
    episodes = relationship("UserPodcastEpisode", back_populates="podcast", cascade="all, delete-orphan")
    
    __table_args__ = (
        UniqueConstraint("user_id", "spotify_show_id", name="uq_user_podcast"),
        Index("idx_user_podcasts", "user_id", "last_listened_at"),
        Index("idx_podcast_show", "spotify_show_id"),
    )


class UserPodcastEpisode(Base):
    """Individual podcast episodes a user has listened to"""
    __tablename__ = "user_podcast_episodes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    podcast_id = Column(UUID(as_uuid=True), ForeignKey("user_podcasts.id", ondelete="CASCADE"), nullable=False)
    
    spotify_episode_id = Column(String(255), nullable=False)
    episode_name = Column(Text, nullable=False)
    episode_description = Column(Text)
    
    # Episode metadata
    duration_ms = Column(Integer)
    release_date = Column(Date)
    episode_type = Column(String(50))  # full, trailer, bonus
    
    # Playback info
    played_at = Column(DateTime(timezone=True), nullable=False)
    progress_ms = Column(Integer)
    completion_percentage = Column(Numeric(5, 2))
    
    # URLs
    audio_preview_url = Column(Text)
    external_urls = Column(JSON)
    
    # Transcription status (for future steps)
    transcription_status = Column(String(50), default="pending")
    transcription_cost = Column(Numeric(10, 6))
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    # Relationships
    podcast = relationship("UserPodcast", back_populates="episodes")
    
    __table_args__ = (
        UniqueConstraint("user_id", "spotify_episode_id", "played_at", name="uq_user_episode_play"),
        Index("idx_user_episodes", "user_id", "played_at"),
        Index("idx_episode_completion", "user_id", "completion_percentage"),
        Index("idx_transcription_status", "transcription_status"),
    )
    
    @property
    def is_fully_played(self) -> bool:
        """Check if episode was fully played (>90% completion)"""
        return self.completion_percentage and self.completion_percentage >= 90


class SpotifyAPICall(Base):
    """Track Spotify API calls for cost monitoring"""
    __tablename__ = "spotify_api_calls"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    
    endpoint = Column(String(255), nullable=False)
    method = Column(String(10), nullable=False)
    status_code = Column(Integer)
    
    response_time_ms = Column(Integer)
    rate_limit_remaining = Column(Integer)
    
    estimated_cost = Column(Numeric(10, 6), nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    __table_args__ = (
        Index("idx_api_calls_user", "user_id", "created_at"),
        Index("idx_api_calls_cost", "user_id", "estimated_cost"),
    )


# Repository functions for user isolation
class SpotifyRepository:
    """Repository pattern for Spotify data access with user isolation"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def get_connection(self, user_id: uuid.UUID) -> Optional[SpotifyConnection]:
        """Get Spotify connection for a specific user"""
        return self.db.query(SpotifyConnection).filter(
            SpotifyConnection.user_id == user_id
        ).first()
    
    def get_user_podcasts(self, user_id: uuid.UUID, limit: int = 50) -> List[UserPodcast]:
        """Get podcasts for a specific user, ordered by last listened"""
        return self.db.query(UserPodcast).filter(
            UserPodcast.user_id == user_id
        ).order_by(
            UserPodcast.last_listened_at.desc()
        ).limit(limit).all()
    
    def get_user_episodes(
        self, 
        user_id: uuid.UUID, 
        podcast_id: Optional[uuid.UUID] = None,
        limit: int = 100
    ) -> List[UserPodcastEpisode]:
        """Get episodes for a specific user, optionally filtered by podcast"""
        query = self.db.query(UserPodcastEpisode).filter(
            UserPodcastEpisode.user_id == user_id
        )
        
        if podcast_id:
            query = query.filter(UserPodcastEpisode.podcast_id == podcast_id)
        
        return query.order_by(
            UserPodcastEpisode.played_at.desc()
        ).limit(limit).all()
    
    def get_api_call_stats(self, user_id: uuid.UUID, days: int = 7) -> Dict[str, Any]:
        """Get API call statistics for cost monitoring"""
        cutoff = datetime.utcnow() - timedelta(days=days)
        
        calls = self.db.query(
            func.count(SpotifyAPICall.id).label("total_calls"),
            func.sum(SpotifyAPICall.estimated_cost).label("total_cost"),
            func.avg(SpotifyAPICall.response_time_ms).label("avg_response_time")
        ).filter(
            SpotifyAPICall.user_id == user_id,
            SpotifyAPICall.created_at >= cutoff
        ).first()
        
        return {
            "total_calls": calls.total_calls or 0,
            "total_cost": float(calls.total_cost or 0),
            "avg_response_time_ms": float(calls.avg_response_time or 0)
        }
