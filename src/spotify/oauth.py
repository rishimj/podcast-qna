"""
Spotify OAuth 2.0 implementation with PKCE for enhanced security
"""
import base64
import hashlib
import json
import secrets
import urllib.parse
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple
import aiohttp
from sqlalchemy.orm import Session
from typing import Dict, Optional, Tuple
import aiohttp
from sqlalchemy.orm import Session

from src.spotify.config import get_spotify_config
from src.spotify.models import SpotifyConnection
from src.spotify.utils.logging import get_logger

logger = get_logger(__name__)


class SpotifyOAuth:
    """Handle Spotify OAuth 2.0 flow with PKCE"""
    
    def __init__(self):
        self.config = get_spotify_config()
        self.cost_tracker = get_cost_tracker()
        
    def generate_pkce_pair(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge"""
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    def generate_state(self) -> str:
        """Generate secure random state for CSRF protection"""
        return secrets.token_urlsafe(32)
    
    def get_authorization_url(self, state: str, code_challenge: str) -> str:
        """Build Spotify authorization URL with PKCE"""
        params = {
            'client_id': self.config.client_id,
            'response_type': 'code',
            'redirect_uri': self.config.redirect_uri,
            'scope': self.config.scope_string,
            'state': state,
            'code_challenge_method': 'S256',
            'code_challenge': code_challenge,
            'show_dialog': 'false'
        }
        
        return f"{self.config.auth_base_url}/authorize?{urllib.parse.urlencode(params)}"
    
    async def exchange_code_for_tokens(
        self, 
        code: str, 
        code_verifier: str,
        user_id: str
    ) -> Dict[str, any]:
        """Exchange authorization code for access and refresh tokens"""
        
        # Track API call cost
        can_proceed = await self.cost_tracker.check_budget_before_operation(
            user_id,
            "spotify_token_exchange", 
            self.config.estimated_cost_per_api_call
        )
        
        if not can_proceed:
            raise Exception("Budget limit exceeded for Spotify API calls")
        
        url = f"{self.config.auth_base_url}/api/token"
        
        data = {
            'grant_type': 'authorization_code',
            'code': code,
            'redirect_uri': self.config.redirect_uri,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret,
            'code_verifier': code_verifier
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    # Track the API call
                    await self.cost_tracker.track_api_call(
                        user_id,
                        "spotify_token_exchange",
                        self.config.estimated_cost_per_api_call
                    )
                    
                    if response.status != 200:
                        error_data = await response.text()
                        logger.error(f"Token exchange failed: {response.status} - {error_data}")
                        raise Exception(f"Token exchange failed: {response.status}")
                    
                    token_data = await response.json()
                    
                    # Add expiration timestamp
                    token_data['expires_at'] = datetime.utcnow() + timedelta(
                        seconds=token_data['expires_in']
                    )
                    
                    return token_data
                    
        except Exception as e:
            logger.error(f"Token exchange error: {str(e)}")
            raise
    
    async def refresh_access_token(
        self, 
        refresh_token: str,
        user_id: str
    ) -> Dict[str, any]:
        """Refresh expired access token"""
        
        # Check budget
        can_proceed = await self.cost_tracker.check_budget_before_operation(
            user_id,
            "spotify_token_refresh",
            self.config.estimated_cost_per_api_call
        )
        
        if not can_proceed:
            raise Exception("Budget limit exceeded for Spotify API calls")
        
        url = f"{self.config.auth_base_url}/api/token"
        
        data = {
            'grant_type': 'refresh_token',
            'refresh_token': refresh_token,
            'client_id': self.config.client_id,
            'client_secret': self.config.client_secret
        }
        
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data, headers=headers) as response:
                    # Track the API call
                    await self.cost_tracker.track_api_call(
                        user_id,
                        "spotify_token_refresh",
                        self.config.estimated_cost_per_api_call
                    )
                    
                    if response.status != 200:
                        error_data = await response.text()
                        logger.error(f"Token refresh failed: {response.status} - {error_data}")
                        raise Exception(f"Token refresh failed: {response.status}")
                    
                    token_data = await response.json()
                    
                    # Add expiration timestamp
                    token_data['expires_at'] = datetime.utcnow() + timedelta(
                        seconds=token_data['expires_in']
                    )
                    
                    return token_data
                    
        except Exception as e:
            logger.error(f"Token refresh error: {str(e)}")
            raise
    
    async def save_tokens(
        self,
        db: Session,
        user_id: str,
        spotify_user_id: str,
        token_data: Dict[str, any]
    ) -> SpotifyConnection:
        """Save or update Spotify connection with encrypted tokens"""
        
        connection = db.query(SpotifyConnection).filter(
            SpotifyConnection.user_id == user_id
        ).first()
        
        if connection:
            # Update existing connection
            connection.spotify_user_id = spotify_user_id
            connection.access_token = token_data['access_token']
            connection.refresh_token = token_data.get('refresh_token', connection.refresh_token)
            connection.token_expires_at = token_data['expires_at']
            connection.scopes = token_data['scope']
            connection.sync_failure_count = 0  # Reset on successful auth
        else:
            # Create new connection
            connection = SpotifyConnection(
                user_id=user_id,
                spotify_user_id=spotify_user_id,
                access_token=token_data['access_token'],
                refresh_token=token_data['refresh_token'],
                token_expires_at=token_data['expires_at'],
                scopes=token_data['scope']
            )
            db.add(connection)
        
        db.commit()
        logger.info(f"Saved Spotify connection for user {user_id}")
        
        return connection
    
    async def ensure_valid_token(
        self,
        db: Session,
        connection: SpotifyConnection
    ) -> str:
        """Ensure connection has valid access token, refresh if needed"""
        
        if not connection.is_token_expired:
            return connection.access_token
        
        logger.info(f"Refreshing expired token for user {connection.user_id}")
        
        try:
            # Refresh the token
            token_data = await self.refresh_access_token(
                connection.refresh_token,
                str(connection.user_id)
            )
            
            # Update stored tokens
            connection.access_token = token_data['access_token']
            if 'refresh_token' in token_data:
                connection.refresh_token = token_data['refresh_token']
            connection.token_expires_at = token_data['expires_at']
            
            db.commit()
            
            return connection.access_token
            
        except Exception as e:
            logger.error(f"Failed to refresh token: {str(e)}")
            connection.sync_failure_count += 1
            connection.last_sync_error = str(e)
            db.commit()
            raise


class SpotifyAuthState:
    """Manage OAuth state during authorization flow"""
    
    # In production, use Redis or similar for distributed state storage
    _states: Dict[str, Dict[str, any]] = {}
    
    @classmethod
    def save_state(
        cls, 
        state: str, 
        user_id: str, 
        code_verifier: str,
        expires_in: int = 600  # 10 minutes
    ):
        """Save OAuth state data"""
        cls._states[state] = {
            'user_id': user_id,
            'code_verifier': code_verifier,
            'expires_at': datetime.utcnow() + timedelta(seconds=expires_in)
        }
        
        # Clean expired states
        cls._clean_expired_states()
    
    @classmethod
    def get_state(cls, state: str) -> Optional[Dict[str, any]]:
        """Retrieve and remove OAuth state data"""
        cls._clean_expired_states()
        return cls._states.pop(state, None)
    
    @classmethod
    def _clean_expired_states(cls):
        """Remove expired states"""
        now = datetime.utcnow()
        expired_states = [
            state for state, data in cls._states.items()
            if data['expires_at'] < now
        ]
        for state in expired_states:
            del cls._states[state]
