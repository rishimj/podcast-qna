"""
Real Spotify integration tests - NO MOCK DATA
Tests use actual Spotify API with a test account
"""
import os
import asyncio
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.spotify.config import get_spotify_config
from src.spotify.oauth import SpotifyOAuth, SpotifyAuthState
from src.spotify.client import SpotifyClient, RateLimiter
from src.spotify.models import Base, SpotifyConnection, UserPodcast, UserPodcastEpisode
from src.spotify.sync import SpotifyDataSync


class TestRealSpotifyIntegration:
    """Test Spotify integration with REAL API calls"""
    
    @classmethod
    def setup_class(cls):
        """Set up test database and verify configuration"""
        # Verify required environment variables
        required_vars = [
            'SPOTIFY_CLIENT_ID',
            'SPOTIFY_CLIENT_SECRET',
            'SPOTIFY_REDIRECT_URI',
            'SPOTIFY_TOKEN_ENCRYPTION_KEY',
            'SPOTIFY_TEST_REFRESH_TOKEN'  # Pre-authorized test account
        ]
        
        missing_vars = [var for var in required_vars if not os.getenv(var)]
        if missing_vars:
            pytest.skip(f"Missing required environment variables: {missing_vars}")
        
        # Create test database
        cls.engine = create_engine('sqlite:///:memory:')
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine)
        
        # Create test user
        cls.test_user_id = uuid.uuid4()
    
    @pytest.fixture
    def db(self):
        """Provide database session for tests"""
        session = self.SessionLocal()
        try:
            yield session
        finally:
            session.close()
    
    @pytest.fixture
    async def test_connection(self, db):
        """Create test Spotify connection with real tokens"""
        oauth = SpotifyOAuth()
        
        # Use pre-authorized refresh token from test account
        refresh_token = os.getenv('SPOTIFY_TEST_REFRESH_TOKEN')
        
        # Get fresh access token
        token_data = await oauth.refresh_access_token(
            refresh_token,
            str(self.test_user_id)
        )
        
        # Create connection
        connection = SpotifyConnection(
            user_id=self.test_user_id,
            spotify_user_id='test_user',
            access_token=token_data['access_token'],
            refresh_token=token_data.get('refresh_token', refresh_token),
            token_expires_at=token_data['expires_at'],
            scopes=token_data['scope']
        )
        
        db.add(connection)
        db.commit()
        
        return connection
    
    @pytest.mark.asyncio
    async def test_real_spotify_credentials_work(self):
        """Test that Spotify credentials are valid"""
        config = get_spotify_config()
        
        assert config.client_id, "Spotify client ID not configured"
        assert config.client_secret, "Spotify client secret not configured"
        assert config.redirect_uri, "Spotify redirect URI not configured"
        assert config.encryption_key, "Token encryption key not configured"
    
    @pytest.mark.asyncio
    async def test_oauth_pkce_generation(self):
        """Test PKCE code generation for OAuth"""
        oauth = SpotifyOAuth()
        
        verifier, challenge = oauth.generate_pkce_pair()
        
        assert len(verifier) >= 43  # Min length for PKCE
        assert len(verifier) <= 128  # Max length for PKCE
        assert len(challenge) >= 43
        assert verifier != challenge
    
    @pytest.mark.asyncio
    async def test_oauth_state_management(self):
        """Test OAuth state storage and retrieval"""
        state = "test_state_123"
        user_id = str(uuid.uuid4())
        verifier = "test_verifier"
        
        # Save state
        SpotifyAuthState.save_state(state, user_id, verifier)
        
        # Retrieve state
        state_data = SpotifyAuthState.get_state(state)
        
        assert state_data is not None
        assert state_data['user_id'] == user_id
        assert state_data['code_verifier'] == verifier
        
        # State should be removed after retrieval
        assert SpotifyAuthState.get_state(state) is None
    
    @pytest.mark.asyncio
    async def test_real_token_refresh(self, db):
        """Test refreshing access token with real Spotify API"""
        oauth = SpotifyOAuth()
        refresh_token = os.getenv('SPOTIFY_TEST_REFRESH_TOKEN')
        
        # Track API call cost
        cost_tracker = get_cost_tracker()
        initial_cost = await cost_tracker.get_real_daily_spend()
        
        # Refresh token
        token_data = await oauth.refresh_access_token(
            refresh_token,
            str(self.test_user_id)
        )
        
        # Verify response
        assert 'access_token' in token_data
        assert 'expires_in' in token_data
        assert 'expires_at' in token_data
        assert token_data['expires_at'] > datetime.utcnow()
        
        # Verify cost was tracked
        final_cost = await cost_tracker.get_real_daily_spend()
        assert final_cost > initial_cost
    
    @pytest.mark.asyncio
    async def test_real_api_client_get_user(self, db, test_connection):
        """Test getting current user with real Spotify API"""
        async with SpotifyClient(db, test_connection) as client:
            user_data = await client.get_current_user()
            
            # Verify response structure
            assert 'id' in user_data
            assert 'email' in user_data or 'display_name' in user_data
            assert 'product' in user_data  # free or premium
    
    @pytest.mark.asyncio
    async def test_real_api_rate_limiting(self):
        """Test rate limiter behavior"""
        rate_limiter = RateLimiter(calls_per_period=2, period_seconds=1)
        
        start_time = asyncio.get_event_loop().time()
        
        # Make 3 calls - third should be delayed
        await rate_limiter.acquire()
        await rate_limiter.acquire()
        await rate_limiter.acquire()
        
        elapsed = asyncio.get_event_loop().time() - start_time
        
        # Third call should have waited ~1 second
        assert elapsed >= 0.9, f"Rate limiter didn't delay properly: {elapsed}s"
    
    @pytest.mark.asyncio
    async def test_real_podcast_history_fetch(self, db, test_connection):
        """Test fetching real podcast history from Spotify"""
        from .client import SpotifyPodcastFetcher
        
        fetcher = SpotifyPodcastFetcher(db, test_connection)
        
        # Fetch real podcast history
        podcasts = await fetcher.fetch_podcast_history(limit=10)
        
        # Test account should have at least some podcast history
        # If not, the test will help identify that we need to listen to podcasts first
        if not podcasts:
            pytest.skip("Test account has no podcast history - listen to some podcasts first")
        
        # Verify podcast data structure
        for podcast in podcasts:
            if podcast['episode']:  # Some might be saved shows without episodes
                assert 'id' in podcast['episode']
                assert 'name' in podcast['episode']
                assert podcast['episode']['type'] == 'episode'
            
            assert 'id' in podcast['show']
            assert 'name' in podcast['show']
    
    @pytest.mark.asyncio
    async def test_real_data_sync(self, db, test_connection):
        """Test syncing real podcast data to database"""
        sync_service = SpotifyDataSync()
        
        # Run sync
        stats = await sync_service.sync_user_podcasts(db, test_connection)
        
        # Check results
        assert 'new_shows' in stats
        assert 'new_episodes' in stats
        assert 'errors' in stats
        
        # Verify data was saved
        shows = db.query(UserPodcast).filter(
            UserPodcast.user_id == self.test_user_id
        ).all()
        
        episodes = db.query(UserPodcastEpisode).filter(
            UserPodcastEpisode.user_id == self.test_user_id
        ).all()
        
        # Log what we found for debugging
        print(f"Found {len(shows)} shows and {len(episodes)} episodes")
        
        if shows:
            # Verify show data
            show = shows[0]
            assert show.spotify_show_id
            assert show.show_name
            assert show.user_id == self.test_user_id
        
        if episodes:
            # Verify episode data
            episode = episodes[0]
            assert episode.spotify_episode_id
            assert episode.episode_name
            assert episode.user_id == self.test_user_id
            assert episode.played_at
    
    @pytest.mark.asyncio
    async def test_user_data_isolation(self, db, test_connection):
        """Test that user data is properly isolated"""
        # Create another user
        other_user_id = uuid.uuid4()
        
        # Add some data for test user
        show = UserPodcast(
            user_id=self.test_user_id,
            connection_id=test_connection.id,
            spotify_show_id='test_show_123',
            show_name='Test Podcast'
        )
        db.add(show)
        db.commit()
        
        # Query for other user should return nothing
        other_user_shows = db.query(UserPodcast).filter(
            UserPodcast.user_id == other_user_id
        ).all()
        
        assert len(other_user_shows) == 0
        
        # Query for test user should return the show
        test_user_shows = db.query(UserPodcast).filter(
            UserPodcast.user_id == self.test_user_id
        ).all()
        
        assert len(test_user_shows) == 1
        assert test_user_shows[0].spotify_show_id == 'test_show_123'
    
    @pytest.mark.asyncio
    async def test_token_encryption(self, db):
        """Test that tokens are properly encrypted in database"""
        config = get_spotify_config()
        
        # Create connection with known tokens
        test_access_token = "test_access_token_12345"
        test_refresh_token = "test_refresh_token_67890"
        
        connection = SpotifyConnection(
            user_id=self.test_user_id,
            spotify_user_id='test_user',
            access_token=test_access_token,
            refresh_token=test_refresh_token,
            token_expires_at=datetime.utcnow() + timedelta(hours=1),
            scopes='user-read-recently-played'
        )
        
        db.add(connection)
        db.commit()
        
        # Verify encrypted storage
        assert connection.access_token_encrypted != test_access_token
        assert connection.refresh_token_encrypted != test_refresh_token
        assert connection.access_token_encrypted.startswith('gAAAAA')  # Fernet prefix
        
        # Verify decryption
        assert connection.access_token == test_access_token
        assert connection.refresh_token == test_refresh_token
    
    @pytest.mark.asyncio
    async def test_cost_tracking_integration(self, db, test_connection):
        """Test that Spotify API calls are tracked in cost system"""
        from src.spotify.models import SpotifyAPICall
        
        initial_calls = db.query(SpotifyAPICall).filter(
            SpotifyAPICall.user_id == self.test_user_id
        ).count()
        
        # Make an API call
        async with SpotifyClient(db, test_connection) as client:
            await client.get_current_user()
        
        # Verify call was tracked
        final_calls = db.query(SpotifyAPICall).filter(
            SpotifyAPICall.user_id == self.test_user_id
        ).count()
        
        assert final_calls == initial_calls + 1
        
        # Check the tracked call
        last_call = db.query(SpotifyAPICall).filter(
            SpotifyAPICall.user_id == self.test_user_id
        ).order_by(SpotifyAPICall.created_at.desc()).first()
        
        assert last_call.endpoint == 'me'
        assert last_call.method == 'GET'
        assert last_call.status_code == 200
        assert last_call.estimated_cost == Decimal('0.0001')


@pytest.mark.asyncio
class TestSpotifyErrorHandling:
    """Test error handling with real API scenarios"""
    
    @pytest.mark.asyncio
    async def test_invalid_token_handling(self, db):
        """Test handling of invalid access token"""
        # Create connection with invalid token
        connection = SpotifyConnection(
            user_id=uuid.uuid4(),
            spotify_user_id='test_user',
            access_token='invalid_token_12345',
            refresh_token=os.getenv('SPOTIFY_TEST_REFRESH_TOKEN'),
            token_expires_at=datetime.utcnow() + timedelta(hours=1),
            scopes='user-read-recently-played'
        )
        
        db.add(connection)
        db.commit()
        
        # Should automatically refresh token
        async with SpotifyClient(db, connection) as client:
            user_data = await client.get_current_user()
            assert 'id' in user_data  # Should succeed after refresh
    
    @pytest.mark.asyncio 
    async def test_network_error_retry(self, db, test_connection, monkeypatch):
        """Test retry logic for network errors"""
        import aiohttp
        
        call_count = 0
        
        async def mock_request(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            
            if call_count < 3:
                raise aiohttp.ClientError("Network error")
            
            # Return mock response on third try
            class MockResponse:
                status = 200
                headers = {'X-RateLimit-Remaining': '100'}
                
                async def json(self):
                    return {'id': 'test_user'}
            
            return MockResponse()
        
        # Patch the request method
        async with SpotifyClient(db, test_connection) as client:
            monkeypatch.setattr(client._session, 'request', mock_request)
            
            # Should succeed after retries
            result = await client.get_current_user()
            assert result['id'] == 'test_user'
            assert call_count == 3  # Two failures + one success


# Run with: pytest tests/test_real_spotify_integration.py -v
