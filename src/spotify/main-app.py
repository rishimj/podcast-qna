"""
Main FastAPI application with Spotify integration
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

from src.utils.logging import get_logger, add_request_id
from src.database import engine, Base
from src.spotify.models import Base as SpotifyBase

# Import routers
from src.auth import router as auth_router
from src.spotify.api import router as spotify_router
from src.cost_tracking.api import router as cost_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    # Startup
    logger.info("Starting Podcast Q&A System...")
    
    # Create database tables
    Base.metadata.create_all(bind=engine)
    SpotifyBase.metadata.create_all(bind=engine)
    
    # Start background tasks
    if os.getenv("APP_ENV") == "production":
        from src.spotify.sync import run_sync_scheduler
        import asyncio
        
        # Start Spotify sync scheduler
        sync_task = asyncio.create_task(run_sync_scheduler())
        logger.info("Started Spotify sync scheduler")
    
    yield
    
    # Shutdown
    logger.info("Shutting down Podcast Q&A System...")
    
    if os.getenv("APP_ENV") == "production":
        sync_task.cancel()
        try:
            await sync_task
        except asyncio.CancelledError:
            pass


# Create FastAPI app
app = FastAPI(
    title="Multi-User Podcast Q&A System",
    description="AI-powered system for querying podcast content with Spotify integration",
    version="2.0.0",
    lifespan=lifespan
)

# Add middleware
app.middleware("http")(add_request_id)

# CORS configuration
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:8000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router)
app.include_router(spotify_router)
app.include_router(cost_router)

# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "version": "2.0.0",
        "step": "2 - Spotify Integration"
    }

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "Multi-User Podcast Q&A System",
        "version": "2.0.0",
        "step": "2 - Spotify Integration",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "auth": {
                "register": "/api/auth/register",
                "login": "/api/auth/login",
                "me": "/api/auth/me"
            },
            "spotify": {
                "auth_url": "/api/spotify/auth/url",
                "callback": "/api/spotify/auth/callback",
                "status": "/api/spotify/connection/status",
                "podcasts": "/api/spotify/podcasts",
                "episodes": "/api/spotify/episodes/recent",
                "sync": "/api/spotify/sync",
                "costs": "/api/spotify/costs"
            },
            "costs": {
                "summary": "/api/costs/summary",
                "daily": "/api/costs/daily",
                "by_user": "/api/costs/by-user"
            }
        }
    }

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Handle all unhandled exceptions"""
    logger.error(
        "Unhandled exception",
        path=request.url.path,
        method=request.method,
        error=str(exc),
        error_type=type(exc).__name__
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred",
            "request_id": getattr(request.state, "request_id", None)
        }
    )

# Spotify-specific error pages (for OAuth flow)
@app.get("/spotify/success")
async def spotify_success():
    """Success page after Spotify connection"""
    return JSONResponse({
        "status": "success",
        "message": "Spotify account connected successfully! You can close this window."
    })

@app.get("/spotify/error")
async def spotify_error(reason: str = "unknown"):
    """Error page for Spotify connection failures"""
    return JSONResponse({
        "status": "error",
        "message": f"Failed to connect Spotify account: {reason}",
        "help": "Please try again or contact support if the issue persists."
    })


if __name__ == "__main__":
    # Run with uvicorn for development
    uvicorn.run(
        "src.main:app",
        host=os.getenv("APP_HOST", "0.0.0.0"),
        port=int(os.getenv("APP_PORT", 8000)),
        reload=os.getenv("HOT_RELOAD", "true").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
