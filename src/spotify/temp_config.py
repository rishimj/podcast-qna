import os

# Set minimal required environment variables for testing
os.environ['SPOTIFY_CLIENT_ID'] = 'test_client_id'
os.environ['SPOTIFY_CLIENT_SECRET'] = 'test_client_secret'
os.environ['SPOTIFY_REDIRECT_URI'] = 'http://localhost:8000/callback'
os.environ['SPOTIFY_TOKEN_ENCRYPTION_KEY'] = 'test_encryption_key'
