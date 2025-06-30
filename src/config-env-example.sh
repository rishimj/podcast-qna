# Multi-User Podcast Q&A System Configuration
# Copy this file to config.env and fill in your values

# ===== STEP 1: AWS & COST TRACKING =====

# AWS Configuration - REQUIRED for cost tracking
AWS_ACCESS_KEY_ID=your_aws_access_key_here
AWS_SECRET_ACCESS_KEY=your_aws_secret_access_key_here
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=123456789012

# Cost Monitoring Configuration
DAILY_BUDGET_LIMIT=5.00
WEEKLY_BUDGET_LIMIT=25.00
MONTHLY_BUDGET_LIMIT=100.00
COST_ALERT_EMAIL=your-email@example.com

# SES Configuration (for email alerts)
SES_SENDER_EMAIL=noreply@yourdomain.com
SES_REGION=us-east-1

# ===== STEP 2: SPOTIFY INTEGRATION =====

# Spotify App Credentials
# Get these from https://developer.spotify.com/dashboard
SPOTIFY_CLIENT_ID=f71ed5fb17e4491c8d800dc40e4d3e0d
SPOTIFY_CLIENT_SECRET=87ac841385d44adfb2cbfbbcc0d4b8f9
SPOTIFY_REDIRECT_URI=https://localhost:8000/callback

# Token Encryption Key
# Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
SPOTIFY_TOKEN_ENCRYPTION_KEY=dsaiZKpyzwSPljpULfr5mX5zRs67m0GMhbu9Ad7w_OQ

# Spotify Test Account (for automated tests)
# Optional: Pre-authorized refresh token for testing
SPOTIFY_TEST_REFRESH_TOKEN=your_test_account_refresh_token

# ===== DATABASE CONFIGURATION =====

# PostgreSQL Connection
DATABASE_URL=postgresql://user:password@localhost:5432/podcast_qa
DATABASE_POOL_SIZE=20
DATABASE_MAX_OVERFLOW=40

# Redis (for caching and background tasks)
REDIS_URL=redis://localhost:6379/0

# ===== APPLICATION SETTINGS =====

# Security
SECRET_KEY=your-secret-key-here-change-in-production
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30

# Server
APP_HOST=0.0.0.0
APP_PORT=8000
APP_ENV=development
DEBUG=true

# CORS
CORS_ORIGINS=["http://localhost:3000", "http://localhost:8000"]

# ===== FUTURE STEPS CONFIGURATION =====

# Step 3: Audio Discovery
RSS_FEED_TIMEOUT=30
MAX_DOWNLOAD_SIZE_MB=500

# Step 4: Transcription
WHISPER_MODEL_SIZE=base
EC2_INSTANCE_TYPE=g4dn.xlarge
S3_TRANSCRIPT_BUCKET=podcast-transcripts-bucket

# Step 5: Vector Search
OPENAI_API_KEY=your_openai_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=us-east-1

# Step 6: Q&A System
MAX_CONTEXT_LENGTH=4000
MAX_RESPONSE_LENGTH=500
TEMPERATURE=0.7

# ===== MONITORING & LOGGING =====

# Logging
LOG_LEVEL=INFO
LOG_FORMAT=json
LOG_FILE=/var/log/podcast-qa/app.log

# Metrics
PROMETHEUS_PORT=9090
METRICS_ENABLED=true

# Error Tracking (optional)
SENTRY_DSN=https://your-sentry-dsn@sentry.io/project-id

# ===== RATE LIMITING =====

# API Rate Limits
RATE_LIMIT_PER_MINUTE=60
RATE_LIMIT_PER_HOUR=1000

# Spotify Specific Limits
SPOTIFY_RATE_LIMIT_CALLS=180
SPOTIFY_RATE_LIMIT_PERIOD=60

# ===== BACKGROUND TASKS =====

# Celery Configuration
CELERY_BROKER_URL=redis://localhost:6379/1
CELERY_RESULT_BACKEND=redis://localhost:6379/2

# Sync Intervals (hours)
SPOTIFY_SYNC_INTERVAL=4
TRANSCRIPT_CHECK_INTERVAL=24

# ===== DEVELOPMENT SETTINGS =====

# Testing
TEST_DATABASE_URL=postgresql://user:password@localhost:5432/podcast_qa_test
PYTEST_WORKERS=4

# Local Development
HOT_RELOAD=true
SWAGGER_UI_ENABLED=true
