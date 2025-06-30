"""
FastAPI endpoints for Spotify integration
"""
from datetime import datetime
from typing import Dict, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from database import get_db
from auth import get_current_user, User
from oauth import SpotifyOAuth, SpotifyAuthState
from client import SpotifyPodcastFetcher
from sync import SpotifyDataSync
from models import SpotifyRepository, SpotifyConnection
from logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/spotify", tags=["spotify"])


# Response models
class SpotifyAuthURL(BaseModel):
    """OAuth authorization URL response"""
    auth_url: str
    state: str


class SpotifyConnectionStatus(BaseModel):
    """User's Spotify connection status"""
    connected: bool
    spotify_user_id: Optional[str] = None
    last_sync_at: Optional[datetime] = None
    sync_failure_count: int = 0
    needs_sync: bool = False


class PodcastShow(BaseModel):
    """Podcast show information"""
    id: str
    spotify_show_id: str
    name: str
    description: Optional[str]
    publisher: Optional[str]
    total_episodes: Optional[int]
    image_url: Optional[str]
    last_listened_at: Optional[datetime]
    total_episodes_played: int = 0


class PodcastEpisode(BaseModel):
    """Podcast episode information"""
    id: str
    spotify_episode_id: str
    podcast_id: str
    name: str
    description: Optional[str]
    duration_ms: Optional[int]
    release_date: Optional[datetime]
    played_at: datetime
    completion_percentage: float = 0
    is_fully_played: bool = False


class SyncStats(BaseModel):
    """Sync operation statistics"""
    new_shows: int = 0
    new_episodes: int = 0
    updated_shows: int = 0
    errors: List[str] = Field(default_factory=list)


class CostStats(BaseModel):
    """Spotify API cost statistics"""
    total_calls: int = 0
    total_cost: float = 0.0
    avg_response_time_ms: float = 0.0
    period_days: int = 7


# OAuth endpoints
@router.get("/auth/url", response_model=SpotifyAuthURL)
async def get_spotify_auth_url(
    current_user: User = Depends(get_current_user)
):
    """Get Spotify OAuth authorization URL"""
    oauth = SpotifyOAuth()
    
    # Generate PKCE and state
    code_verifier, code_challenge = oauth.generate_pkce_pair()
    state = oauth.generate_state()
    
    # Save state for callback verification
    SpotifyAuthState.save_state(
        state, 
        str(current_user.id), 
        code_verifier
    )
    
    # Generate authorization URL
    auth_url = oauth.get_authorization_url(state, code_challenge)
    
    return SpotifyAuthURL(auth_url=auth_url, state=state)


@router.get("/auth/callback")
async def spotify_auth_callback(
    code: str = Query(..., description="Authorization code from Spotify"),
    state: str = Query(..., description="State parameter for CSRF protection"),
    error: Optional[str] = Query(None, description="Error from Spotify"),
    db: Session = Depends(get_db)
):
    """Handle Spotify OAuth callback"""
    
    # Check for errors
    if error:
        logger.error(f"Spotify auth error: {error}")
        return RedirectResponse(url=f"/spotify/error?reason={error}")
    
    # Verify state
    state_data = SpotifyAuthState.get_state(state)
    if not state_data:
        logger.error("Invalid or expired state")
        return RedirectResponse(url="/spotify/error?reason=invalid_state")
    
    user_id = state_data['user_id']
    code_verifier = state_data['code_verifier']
    
    try:
        # Exchange code for tokens
        oauth = SpotifyOAuth()
        token_data = await oauth.exchange_code_for_tokens(
            code, 
            code_verifier,
            user_id
        )
        
        # Get user info from Spotify
        from src.spotify.client import SpotifyClient
        
        # Create temporary connection for getting user info
        temp_connection = SpotifyConnection(
            user_id=user_id,
            spotify_user_id='temp',
            access_token=token_data['access_token'],
            refresh_token=token_data['refresh_token'],
            token_expires_at=token_data['expires_at'],
            scopes=token_data['scope']
        )
        
        async with SpotifyClient(db, temp_connection) as client:
            spotify_user = await client.get_current_user()
        
        # Save connection to database
        await oauth.save_tokens(
            db,
            user_id,
            spotify_user['id'],
            token_data
        )
        
        # Initial sync
        sync_service = SpotifyDataSync()
        connection = db.query(SpotifyConnection).filter(
            SpotifyConnection.user_id == user_id
        ).first()
        
        if connection:
            await sync_service.sync_user_podcasts(db, connection)
        
        # Redirect to success page
        return RedirectResponse(url="/spotify/success")
        
    except Exception as e:
        logger.error(f"Failed to complete Spotify auth: {str(e)}")
        return RedirectResponse(url=f"/spotify/error?reason=token_exchange_failed")


# Connection management
@router.get("/connection/status", response_model=SpotifyConnectionStatus)
async def get_connection_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get user's Spotify connection status"""
    
    repository = SpotifyRepository(db)
    connection = repository.get_connection(current_user.id)
    
    if not connection:
        return SpotifyConnectionStatus(connected=False)
    
    return SpotifyConnectionStatus(
        connected=True,
        spotify_user_id=connection.spotify_user_id,
        last_sync_at=connection.last_sync_at,
        sync_failure_count=connection.sync_failure_count or 0,
        needs_sync=connection.needs_sync()
    )


@router.delete("/connection/disconnect")
async def disconnect_spotify(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Disconnect user's Spotify account"""
    
    connection = db.query(SpotifyConnection).filter(
        SpotifyConnection.user_id == current_user.id
    ).first()
    
    if connection:
        db.delete(connection)
        db.commit()
        
    return {"status": "disconnected"}


# Podcast data endpoints
@router.get("/podcasts", response_model=List[PodcastShow])
async def get_user_podcasts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100)
):
    """Get user's podcast shows"""
    
    repository = SpotifyRepository(db)
    shows = repository.get_user_podcasts(current_user.id, limit=limit)
    
    return [
        PodcastShow(
            id=str(show.id),
            spotify_show_id=show.spotify_show_id,
            name=show.show_name,
            description=show.show_description,
            publisher=show.publisher,
            total_episodes=show.total_episodes,
            image_url=show.image_url,
            last_listened_at=show.last_listened_at,
            total_episodes_played=show.total_episodes_played or 0
        )
        for show in shows
    ]


@router.get("/podcasts/{podcast_id}/episodes", response_model=List[PodcastEpisode])
async def get_podcast_episodes(
    podcast_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(100, ge=1, le=200)
):
    """Get episodes for a specific podcast"""
    
    repository = SpotifyRepository(db)
    episodes = repository.get_user_episodes(
        current_user.id, 
        podcast_id=podcast_id,
        limit=limit
    )
    
    return [
        PodcastEpisode(
            id=str(episode.id),
            spotify_episode_id=episode.spotify_episode_id,
            podcast_id=str(episode.podcast_id),
            name=episode.episode_name,
            description=episode.episode_description,
            duration_ms=episode.duration_ms,
            release_date=episode.release_date,
            played_at=episode.played_at,
            completion_percentage=float(episode.completion_percentage or 0),
            is_fully_played=episode.is_fully_played
        )
        for episode in episodes
    ]


@router.get("/episodes/recent", response_model=List[PodcastEpisode])
async def get_recent_episodes(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    limit: int = Query(50, ge=1, le=100)
):
    """Get user's recently played episodes"""
    
    repository = SpotifyRepository(db)
    episodes = repository.get_user_episodes(current_user.id, limit=limit)
    
    return [
        PodcastEpisode(
            id=str(episode.id),
            spotify_episode_id=episode.spotify_episode_id,
            podcast_id=str(episode.podcast_id),
            name=episode.episode_name,
            description=episode.episode_description,
            duration_ms=episode.duration_ms,
            release_date=episode.release_date,
            played_at=episode.played_at,
            completion_percentage=float(episode.completion_percentage or 0),
            is_fully_played=episode.is_fully_played
        )
        for episode in episodes
    ]


# Sync endpoints
@router.post("/sync", response_model=SyncStats)
async def sync_podcasts(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Manually trigger podcast sync for current user"""
    
    connection = db.query(SpotifyConnection).filter(
        SpotifyConnection.user_id == current_user.id
    ).first()
    
    if not connection:
        raise HTTPException(status_code=400, detail="No Spotify connection found")
    
    sync_service = SpotifyDataSync()
    stats = await sync_service.sync_user_podcasts(db, connection)
    
    return SyncStats(**stats)


# Cost tracking
@router.get("/costs", response_model=CostStats)
async def get_spotify_costs(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    days: int = Query(7, ge=1, le=30)
):
    """Get Spotify API usage costs for current user"""
    
    repository = SpotifyRepository(db)
    stats = repository.get_api_call_stats(current_user.id, days=days)
    
    return CostStats(
        total_calls=stats['total_calls'],
        total_cost=stats['total_cost'],
        avg_response_time_ms=stats['avg_response_time_ms'],
        period_days=days
    )


# Search endpoint
@router.get("/search")
async def search_podcasts(
    q: str = Query(..., description="Search query"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search for podcasts on Spotify"""
    
    connection = db.query(SpotifyConnection).filter(
        SpotifyConnection.user_id == current_user.id
    ).first()
    
    if not connection:
        raise HTTPException(status_code=400, detail="No Spotify connection found")
    
    async with SpotifyClient(db, connection) as client:
        results = await client.search_podcasts(q, limit=20)
        
    return results.get('shows', {}).get('items', [])
