"""
Spotify Integration Package

This package provides complete Spotify integration for the podcast Q&A system,
including OAuth authentication, API client, data syncing, and cost tracking.
"""

from src.spotify.config import get_spotify_config
from src.spotify.oauth import SpotifyOAuth, SpotifyAuthState
from src.spotify.client import SpotifyClient, SpotifyPodcastFetcher
from src.spotify.models import SpotifyConnection, UserPodcast, UserPodcastEpisode, SpotifyAPICall, SpotifyRepository
from src.spotify.sync import SpotifyDataSync, run_sync_scheduler
from src.spotify.utils.logging import get_logger

__all__ = [
    'get_spotify_config',
    'SpotifyOAuth',
    'SpotifyAuthState', 
    'SpotifyClient',
    'SpotifyPodcastFetcher',
    'SpotifyConnection',
    'UserPodcast',
    'UserPodcastEpisode',
    'SpotifyAPICall',
    'SpotifyRepository',
    'SpotifyDataSync',
    'run_sync_scheduler'
] 