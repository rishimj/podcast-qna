"""
Spotify API client with rate limiting, retries, and cost tracking
"""
import asyncio
import time
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Any
from urllib.parse import urlencode

import aiohttp
from aiohttp import ClientSession, ClientTimeout
from sqlalchemy.orm import Session

from src.spotify.config import get_spotify_config
from src.spotify.models import SpotifyConnection, SpotifyAPICall
from src.spotify.oauth import SpotifyOAuth
from src.spotify.utils.logging import get_logger

logger = get_logger(__name__)


class RateLimiter:
    """Token bucket rate limiter for Spotify API"""
    
    def __init__(self, calls_per_period: int, period_seconds: int):
        self.calls_per_period = calls_per_period
        self.period_seconds = period_seconds
        self.calls = []
        self._lock = asyncio.Lock()
    
    async def acquire(self):
        """Wait if necessary to respect rate limit"""
        async with self._lock:
            now = time.time()
            # Remove calls outside the current period
            self.calls = [call_time for call_time in self.calls 
                         if now - call_time < self.period_seconds]
            
            if len(self.calls) >= self.calls_per_period:
                # Need to wait
                sleep_time = self.period_seconds - (now - self.calls[0]) + 0.1
                logger.warning(f"Rate limit reached, sleeping for {sleep_time:.2f} seconds")
                await asyncio.sleep(sleep_time)
                # Recursive call after sleep
                return await self.acquire()
            
            self.calls.append(now)


class SpotifyClient:
    """Spotify API client with comprehensive error handling"""
    
    def __init__(self, db: Session, connection: SpotifyConnection):
        self.db = db
        self.connection = connection
        self.config = get_spotify_config()
        self.oauth = SpotifyOAuth()
        self.cost_tracker = get_cost_tracker()
        
        # Rate limiting
        self.rate_limiter = RateLimiter(
            self.config.rate_limit_calls,
            self.config.rate_limit_period
        )
        
        # Session configuration
        self.timeout = ClientTimeout(total=30)
        self._session: Optional[ClientSession] = None
    
    async def __aenter__(self):
        """Async context manager entry"""
        self._session = ClientSession(timeout=self.timeout)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self._session:
            await self._session.close()
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """Make API request with retries and error handling"""
        
        # Ensure valid token
        access_token = await self.oauth.ensure_valid_token(self.db, self.connection)
        
        # Check budget before making request
        can_proceed = await self.cost_tracker.check_budget_before_operation(
            str(self.connection.user_id),
            f"spotify_api_{endpoint}",
            Decimal(str(self.config.estimated_cost_per_api_call))
        )
        
        if not can_proceed:
            raise Exception("Budget limit exceeded for Spotify API calls")
        
        # Rate limiting
        await self.rate_limiter.acquire()
        
        url = f"{self.config.api_base_url}/{endpoint}"
        if params:
            url = f"{url}?{urlencode(params)}"
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        start_time = time.time()
        
        try:
            async with self._session.request(
                method, 
                url, 
                headers=headers, 
                json=data
            ) as response:
                response_time_ms = int((time.time() - start_time) * 1000)
                
                # Track API call
                api_call = SpotifyAPICall(
                    user_id=self.connection.user_id,
                    endpoint=endpoint,
                    method=method,
                    status_code=response.status,
                    response_time_ms=response_time_ms,
                    rate_limit_remaining=int(response.headers.get('X-RateLimit-Remaining', -1)),
                    estimated_cost=Decimal(str(self.config.estimated_cost_per_api_call))
                )
                self.db.add(api_call)
                self.db.commit()
                
                # Track cost
                await self.cost_tracker.track_api_call(
                    str(self.connection.user_id),
                    f"spotify_api_{endpoint}",
                    Decimal(str(self.config.estimated_cost_per_api_call))
                )
                
                # Handle token expiration
                if response.status == 401:
                    # Token expired, refresh and retry
                    self.connection.token_expires_at = datetime.utcnow()
                    return await self._make_request(
                        method, endpoint, params, data, retry_count + 1
                    )

                # Handle rate limiting
                if response.status == 429:
                    retry_after = int(response.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, retry after {retry_after} seconds")
                    
                    if retry_count < self.config.max_retries:
                        await asyncio.sleep(retry_after)
                        return await self._make_request(
                            method, endpoint, params, data, retry_count + 1
                        )
                    raise Exception("Rate limit exceeded after max retries")

                # Handle other errors
                if response.status >= 400:
                    error_data = await response.text()
                    logger.error(f"Spotify API error: {response.status} - {error_data}")
                    raise Exception(f"Spotify API error: {response.status}")

                return await response.json()
        except aiohttp.ClientError as e:
            logger.error(f"Network error calling Spotify API: {str(e)}")
            
            if retry_count < 3:
                logger.warning(f"Retrying request to {endpoint} after error: {str(e)}")
                await asyncio.sleep(2 ** retry_count)  # Exponential backoff
                return await self._make_request(method, endpoint, params, data, retry_count + 1)
            raise
        except Exception as e:
            raise Exception(f"Failed to make request to {endpoint}: {str(e)}")

        except aiohttp.ClientError as e:
            logger.error(f"Network error calling Spotify API: {str(e)}")
            
            if retry_count < self.config.max_retries:
                wait_time = self.config.backoff_factor * (2 ** retry_count)
                logger.info(f"Retrying after {wait_time} seconds...")
                await asyncio.sleep(wait_time)
                return await self._make_request(
                    method, endpoint, params, data, retry_count + 1
                )
            raise
    
    async def get_current_user(self) -> Dict[str, Any]:
        """Get current user's profile"""
        return await self._make_request('GET', 'me')
    
    async def get_recently_played(
        self, 
        limit: int = 50,
        after: Optional[int] = None,
        before: Optional[int] = None
    ) -> Dict[str, Any]:
        """Get user's recently played items"""
        params = {'limit': min(limit, 50)}
        
        if after:
            params['after'] = after
        elif before:
            params['before'] = before
        
        return await self._make_request('GET', 'me/player/recently-played', params)
    
    async def get_show(self, show_id: str) -> Dict[str, Any]:
        """Get detailed information about a podcast show"""
        return await self._make_request('GET', f'shows/{show_id}')
    
    async def get_episode(self, episode_id: str) -> Dict[str, Any]:
        """Get detailed information about a podcast episode"""
        return await self._make_request('GET', f'episodes/{episode_id}')
    
    async def get_shows(self, show_ids: List[str]) -> Dict[str, Any]:
        """Get multiple shows in a single request (max 50)"""
        ids = ','.join(show_ids[:50])
        return await self._make_request('GET', 'shows', {'ids': ids})
    
    async def get_episodes(self, episode_ids: List[str]) -> Dict[str, Any]:
        """Get multiple episodes in a single request (max 50)"""
        ids = ','.join(episode_ids[:50])
        return await self._make_request('GET', 'episodes', {'ids': ids})
    
    async def get_saved_shows(self, limit: int = 50, offset: int = 0) -> Dict[str, Any]:
        """Get user's saved podcast shows"""
        params = {
            'limit': min(limit, 50),
            'offset': offset
        }
        return await self._make_request('GET', 'me/shows', params)
    
    async def search_podcasts(
        self, 
        query: str, 
        limit: int = 20,
        offset: int = 0
    ) -> Dict[str, Any]:
        """Search for podcast shows"""
        params = {
            'q': query,
            'type': 'show',
            'limit': min(limit, 50),
            'offset': offset
        }
        return await self._make_request('GET', 'search', params)


class SpotifyPodcastFetcher:
    """High-level interface for fetching podcast data"""
    
    def __init__(self, db: Session, connection: SpotifyConnection):
        self.db = db
        self.connection = connection
        self.client = SpotifyClient(db, connection)
    
    async def fetch_podcast_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch user's podcast listening history"""
        podcasts = []
        seen_episodes = set()
        
        async with self.client:
            # Get recently played items
            recently_played = await self.client.get_recently_played(limit=limit)
            
            for item in recently_played.get('items', []):
                track = item.get('track', {})
                
                # Check if it's a podcast episode (not music)
                if track.get('type') == 'episode':
                    episode_id = track.get('id')
                    
                    if episode_id and episode_id not in seen_episodes:
                        seen_episodes.add(episode_id)
                        
                        podcast_data = {
                            'played_at': item.get('played_at'),
                            'episode': track,
                            'show': track.get('show', {})
                        }
                        
                        # Get additional show details if needed
                        if not podcast_data['show'].get('total_episodes'):
                            try:
                                show_details = await self.client.get_show(
                                    podcast_data['show']['id']
                                )
                                podcast_data['show'].update(show_details)
                            except Exception as e:
                                logger.warning(f"Failed to get show details: {e}")
                        
                        podcasts.append(podcast_data)
            
            # Also check saved shows
            saved_shows = await self.client.get_saved_shows(limit=20)
            
            for item in saved_shows.get('items', []):
                show = item.get('show', {})
                if show.get('id'):
                    # Add to podcast list if not already there
                    if not any(p['show']['id'] == show['id'] for p in podcasts):
                        podcasts.append({
                            'played_at': None,  # Unknown play time for saved shows
                            'episode': None,
                            'show': show
                        })
        
        return podcasts
