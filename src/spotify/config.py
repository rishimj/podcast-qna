"""
Spotify Integration Configuration
"""
import os
from typing import List, Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator
from cryptography.fernet import Fernet


class SpotifyConfig(BaseSettings):
    """Spotify API configuration with validation"""
    
    # Required Spotify App Credentials
    client_id: str = Field(..., env="SPOTIFY_CLIENT_ID")
    client_secret: str = Field(..., env="SPOTIFY_CLIENT_SECRET")
    redirect_uri: str = Field(..., env="SPOTIFY_REDIRECT_URI")
    encryption_key: str = Field(..., env="SPOTIFY_TOKEN_ENCRYPTION_KEY")
    
    # Optional Configuration with Defaults
    scopes: List[str] = Field(
        default=[
            "user-read-recently-played",
            "user-library-read",
            "user-read-playback-position",
            "user-read-email",
            "user-read-private"
        ]
    )
    
    api_base_url: str = Field(default="https://api.spotify.com/v1")
    auth_base_url: str = Field(default="https://accounts.spotify.com")
    
    max_retries: int = Field(default=3)
    backoff_factor: float = Field(default=1.0)
    rate_limit_calls: int = Field(default=180)  # Spotify allows ~180 calls/min
    rate_limit_period: int = Field(default=60)  # seconds
    
    sync_interval_hours: int = Field(default=4)
    max_episodes_per_sync: int = Field(default=50)
    

    
    class Config:
        env_file = "config.env"
        case_sensitive = False
    
    @validator("encryption_key")
    def validate_encryption_key(cls, v):
        """Ensure encryption key is valid Fernet key"""
        try:
            Fernet(v.encode() if isinstance(v, str) else v)
        except Exception:
            raise ValueError("Invalid encryption key. Generate with: Fernet.generate_key()")
        return v
    
    @property
    def scope_string(self) -> str:
        """Get OAuth scopes as space-separated string"""
        return " ".join(self.scopes)
    
    @property
    def fernet(self) -> Fernet:
        """Get Fernet instance for encryption/decryption"""
        return Fernet(self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key)


# Singleton instance
_spotify_config: Optional[SpotifyConfig] = None


def get_spotify_config() -> SpotifyConfig:
    """Get or create Spotify configuration singleton"""
    global _spotify_config
    if _spotify_config is None:
        _spotify_config = SpotifyConfig()
    return _spotify_config
