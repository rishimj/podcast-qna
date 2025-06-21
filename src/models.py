"""
Database models for multi-user podcast Q&A system.
Ensures complete user data isolation and cost attribution.
"""

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB
from datetime import datetime, timezone
import uuid

Base = declarative_base()


class User(Base):
    """User model with Spotify authentication and cost tracking."""
    __tablename__ = "users"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    spotify_user_id = Column(String(255), unique=True, nullable=False, index=True)
    spotify_access_token = Column(Text)  # Encrypted in production
    spotify_refresh_token = Column(Text)  # Encrypted in production
    spotify_token_expires_at = Column(DateTime(timezone=True))
    
    # User preferences
    display_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    
    # Cost tracking per user
    daily_cost_limit = Column(Numeric(10, 4), default=1.00)  # $1 per day default
    weekly_cost_limit = Column(Numeric(10, 4), default=5.00)  # $5 per week
    monthly_cost_limit = Column(Numeric(10, 4), default=20.00)  # $20 per month
    current_month_spend = Column(Numeric(10, 4), default=0.00)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    last_login = Column(DateTime(timezone=True))
    
    # Relationships
    podcasts = relationship("UserPodcast", back_populates="user", cascade="all, delete-orphan")
    episodes = relationship("Episode", back_populates="user", cascade="all, delete-orphan")
    queries = relationship("UserQuery", back_populates="user", cascade="all, delete-orphan")
    cost_records = relationship("CostRecord", back_populates="user", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<User(id={self.id}, email='{self.email}', spotify_id='{self.spotify_user_id}')>"


class UserPodcast(Base):
    """User's subscribed/listened podcasts with isolation."""
    __tablename__ = "user_podcasts"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Podcast metadata
    spotify_show_id = Column(String(255), nullable=False)
    name = Column(String(500), nullable=False)
    description = Column(Text)
    publisher = Column(String(255))
    
    # RSS feed information
    rss_feed_url = Column(Text)
    last_rss_check = Column(DateTime(timezone=True))
    
    # Processing status
    is_active = Column(Boolean, default=True)
    total_episodes_discovered = Column(Integer, default=0)
    total_episodes_processed = Column(Integer, default=0)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User", back_populates="podcasts")
    episodes = relationship("Episode", back_populates="podcast", cascade="all, delete-orphan")
    
    # Ensure user can't have duplicate podcasts
    __table_args__ = (
        Index('idx_user_spotify_show', 'user_id', 'spotify_show_id', unique=True),
    )
    
    def __repr__(self):
        return f"<UserPodcast(id={self.id}, user_id={self.user_id}, name='{self.name}')>"


class Episode(Base):
    """Individual podcast episodes with user isolation."""
    __tablename__ = "episodes"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    podcast_id = Column(UUID(as_uuid=True), ForeignKey("user_podcasts.id"), nullable=False, index=True)
    
    # Episode identification
    spotify_episode_id = Column(String(255), nullable=False)
    title = Column(String(500), nullable=False)
    description = Column(Text)
    
    # Audio metadata
    audio_url = Column(Text)  # Direct download URL
    duration_ms = Column(Integer)  # Duration in milliseconds
    published_at = Column(DateTime(timezone=True))
    file_size_bytes = Column(Integer)
    audio_format = Column(String(50))  # mp3, wav, etc.
    
    # Processing status
    processing_status = Column(String(50), default="discovered")  # discovered, downloading, transcribing, completed, failed
    transcript_s3_key = Column(String(500))  # S3 key for transcript
    transcript_word_count = Column(Integer)
    
    # Quality metrics
    transcription_confidence = Column(Numeric(5, 4))  # 0.0 to 1.0
    audio_quality_score = Column(Numeric(5, 4))  # 0.0 to 1.0
    
    # Cost tracking for this episode
    transcription_cost = Column(Numeric(10, 4), default=0.00)
    storage_cost = Column(Numeric(10, 4), default=0.00)
    embedding_cost = Column(Numeric(10, 4), default=0.00)
    total_processing_cost = Column(Numeric(10, 4), default=0.00)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    processed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="episodes")
    podcast = relationship("UserPodcast", back_populates="episodes")
    chunks = relationship("TranscriptChunk", back_populates="episode", cascade="all, delete-orphan")
    
    # Ensure user can't have duplicate episodes
    __table_args__ = (
        Index('idx_user_spotify_episode', 'user_id', 'spotify_episode_id', unique=True),
    )
    
    def __repr__(self):
        return f"<Episode(id={self.id}, user_id={self.user_id}, title='{self.title}')>"


class TranscriptChunk(Base):
    """Transcript chunks for RAG with user isolation."""
    __tablename__ = "transcript_chunks"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    episode_id = Column(UUID(as_uuid=True), ForeignKey("episodes.id"), nullable=False, index=True)
    
    # Chunk metadata
    chunk_index = Column(Integer, nullable=False)  # Order within episode
    start_time_ms = Column(Integer)  # Start time in milliseconds
    end_time_ms = Column(Integer)    # End time in milliseconds
    
    # Content
    text = Column(Text, nullable=False)
    word_count = Column(Integer)
    speaker = Column(String(255))  # If diarization is used
    
    # Embeddings
    embedding_vector = Column(JSONB)  # Store embedding as JSON array
    embedding_model = Column(String(100))  # e.g., "amazon.titan-embed-text-v1"
    
    # Search metadata
    topics = Column(JSONB)  # Extracted topics/keywords
    entities = Column(JSONB)  # Named entities
    sentiment_score = Column(Numeric(5, 4))  # -1.0 to 1.0
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Relationships
    user = relationship("User")
    episode = relationship("Episode", back_populates="chunks")
    
    # Indexes for efficient querying
    __table_args__ = (
        Index('idx_user_episode_chunk', 'user_id', 'episode_id', 'chunk_index'),
        Index('idx_user_embedding_search', 'user_id', 'embedding_model'),
    )
    
    def __repr__(self):
        return f"<TranscriptChunk(id={self.id}, user_id={self.user_id}, episode_id={self.episode_id}, chunk_index={self.chunk_index})>"


class UserQuery(Base):
    """User queries with responses and cost tracking."""
    __tablename__ = "user_queries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    
    # Query content
    query_text = Column(Text, nullable=False)
    query_type = Column(String(50), default="question")  # question, summary, search
    
    # Response
    response_text = Column(Text)
    source_chunks = Column(JSONB)  # References to chunks used
    confidence_score = Column(Numeric(5, 4))  # Response confidence
    
    # Cost tracking
    embedding_cost = Column(Numeric(10, 4), default=0.00)  # Cost to embed query
    search_cost = Column(Numeric(10, 4), default=0.00)     # OpenSearch cost
    llm_cost = Column(Numeric(10, 4), default=0.00)        # LLM inference cost
    total_cost = Column(Numeric(10, 4), default=0.00)
    
    # Performance metrics
    response_time_ms = Column(Integer)
    chunks_retrieved = Column(Integer)
    tokens_used = Column(Integer)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    completed_at = Column(DateTime(timezone=True))
    
    # Relationships
    user = relationship("User", back_populates="queries")
    
    def __repr__(self):
        return f"<UserQuery(id={self.id}, user_id={self.user_id}, query_text='{self.query_text[:50]}...')>"


class CostRecord(Base):
    """Detailed cost tracking per user and operation."""
    __tablename__ = "cost_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True)  # Can be None for system costs
    
    # Cost details
    aws_service = Column(String(100), nullable=False)  # dynamodb, bedrock, lambda, etc.
    operation = Column(String(100), nullable=False)    # put_item, invoke_model, etc.
    estimated_cost = Column(Numeric(10, 6), nullable=False)  # 6 decimal places for precision
    actual_cost = Column(Numeric(10, 6))  # From AWS Cost Explorer
    
    # Context
    resource_id = Column(String(255))  # Episode ID, query ID, etc.
    resource_type = Column(String(50))  # episode, query, user_auth, etc.
    tags = Column(JSONB)  # Additional metadata
    
    # Billing reconciliation
    aws_cost_explorer_synced = Column(Boolean, default=False)
    sync_date = Column(DateTime(timezone=True))
    variance = Column(Numeric(10, 6))  # Difference between estimated and actual
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    # Relationships
    user = relationship("User", back_populates="cost_records")
    
    # Indexes for cost analytics
    __table_args__ = (
        Index('idx_cost_user_service_date', 'user_id', 'aws_service', 'timestamp'),
        Index('idx_cost_date_service', 'timestamp', 'aws_service'),
        Index('idx_cost_user_date', 'user_id', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<CostRecord(id={self.id}, user_id={self.user_id}, service={self.aws_service}, cost={self.estimated_cost})>"


class SystemHealth(Base):
    """System health and budget monitoring."""
    __tablename__ = "system_health"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Budget tracking
    daily_budget_limit = Column(Numeric(10, 4), nullable=False)
    weekly_budget_limit = Column(Numeric(10, 4), nullable=False)
    monthly_budget_limit = Column(Numeric(10, 4), nullable=False)
    emergency_stop_limit = Column(Numeric(10, 4), nullable=False)
    
    # Current spending (synced from AWS)
    current_daily_spend = Column(Numeric(10, 4), default=0.00)
    current_weekly_spend = Column(Numeric(10, 4), default=0.00)
    current_monthly_spend = Column(Numeric(10, 4), default=0.00)
    
    # System status
    is_processing_enabled = Column(Boolean, default=True)
    last_aws_sync = Column(DateTime(timezone=True))
    last_health_check = Column(DateTime(timezone=True))
    
    # Alerts
    last_budget_alert = Column(DateTime(timezone=True))
    alert_level = Column(String(20))  # info, warning, critical, emergency
    alert_message = Column(Text)
    
    # Performance metrics
    total_users = Column(Integer, default=0)
    total_episodes_processed = Column(Integer, default=0)
    total_queries_answered = Column(Integer, default=0)
    average_processing_time_minutes = Column(Numeric(10, 4))
    
    # Timestamps
    timestamp = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    
    def __repr__(self):
        return f"<SystemHealth(id={self.id}, timestamp={self.timestamp}, monthly_spend={self.current_monthly_spend})>" 