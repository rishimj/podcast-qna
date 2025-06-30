"""
Background sync service for updating user podcast data
"""
import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Optional, Set
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.spotify.client import SpotifyPodcastFetcher
from src.spotify.models import (
    SpotifyConnection, UserPodcast, UserPodcastEpisode,
    SpotifyRepository
)
from src.spotify.config import get_spotify_config
from src.spotify.utils.logging import get_logger
from src.spotify.database_init import get_db_session

logger = get_logger(__name__)


class SpotifyDataSync:
    """Sync Spotify podcast data for all users"""
    
    def __init__(self):
        self.config = get_spotify_config()
        self.repository = None
    
    async def sync_user_podcasts(
        self, 
        db: Session, 
        connection: SpotifyConnection
    ) -> dict:
        """Sync podcast data for a single user"""
        
        user_id = connection.user_id
        stats = {
            'new_shows': 0,
            'new_episodes': 0,
            'updated_shows': 0,
            'errors': []
        }
        
        try:
            logger.info(f"Starting podcast sync for user {user_id}")
            
            # Mark sync start
            connection.last_sync_at = datetime.utcnow()
            db.commit()
            
            # Fetch podcast history
            fetcher = SpotifyPodcastFetcher(db, connection)
            podcast_history = await fetcher.fetch_podcast_history(
                limit=self.config.max_episodes_per_sync
            )
            
            # Process each podcast item
            existing_shows = {}
            existing_episodes = set()
            
            # Load existing data
            user_shows = db.query(UserPodcast).filter(
                UserPodcast.user_id == user_id
            ).all()
            
            for show in user_shows:
                existing_shows[show.spotify_show_id] = show
                
            user_episodes = db.query(UserPodcastEpisode.spotify_episode_id).filter(
                UserPodcastEpisode.user_id == user_id
            ).all()
            
            existing_episodes = {ep[0] for ep in user_episodes}
            
            # Process fetched data
            for item in podcast_history:
                show_data = item['show']
                episode_data = item['episode']
                played_at = item['played_at']
                
                if not show_data or not show_data.get('id'):
                    continue
                
                # Process show
                show_id = show_data['id']
                
                if show_id in existing_shows:
                    # Update existing show
                    show = existing_shows[show_id]
                    show.last_listened_at = played_at or show.last_listened_at
                    show.total_episodes = show_data.get('total_episodes', show.total_episodes)
                    show.updated_at = datetime.utcnow()
                    stats['updated_shows'] += 1
                else:
                    # Create new show
                    show = UserPodcast(
                        user_id=user_id,
                        connection_id=connection.id,
                        spotify_show_id=show_id,
                        show_name=show_data.get('name', 'Unknown Show'),
                        show_description=show_data.get('description'),
                        publisher=show_data.get('publisher'),
                        total_episodes=show_data.get('total_episodes'),
                        language=show_data.get('languages', [''])[0] if show_data.get('languages') else None,
                        explicit=show_data.get('explicit'),
                        image_url=show_data.get('images', [{}])[0].get('url') if show_data.get('images') else None,
                        external_urls=show_data.get('external_urls'),
                        first_listened_at=played_at,
                        last_listened_at=played_at
                    )
                    db.add(show)
                    db.flush()  # Get the ID
                    existing_shows[show_id] = show
                    stats['new_shows'] += 1
                
                # Process episode if available
                if episode_data and episode_data.get('id') and played_at:
                    episode_id = episode_data['id']
                    
                    # Create unique key for episode play
                    episode_key = f"{episode_id}_{played_at}"
                    
                    if episode_id not in existing_episodes:
                        # Calculate completion percentage
                        duration_ms = episode_data.get('duration_ms', 0)
                        progress_ms = episode_data.get('resume_position_ms', 0)
                        
                        completion = 0
                        if duration_ms > 0:
                            completion = min((progress_ms / duration_ms) * 100, 100)
                        
                        # Create new episode
                        episode = UserPodcastEpisode(
                            user_id=user_id,
                            podcast_id=show.id,
                            spotify_episode_id=episode_id,
                            episode_name=episode_data.get('name', 'Unknown Episode'),
                            episode_description=episode_data.get('description'),
                            duration_ms=duration_ms,
                            release_date=datetime.fromisoformat(
                                episode_data['release_date'].replace('Z', '+00:00')
                            ).date() if episode_data.get('release_date') else None,
                            episode_type=episode_data.get('type'),
                            played_at=datetime.fromisoformat(
                                played_at.replace('Z', '+00:00')
                            ) if isinstance(played_at, str) else played_at,
                            progress_ms=progress_ms,
                            completion_percentage=Decimal(str(completion)),
                            audio_preview_url=episode_data.get('audio_preview_url'),
                            external_urls=episode_data.get('external_urls')
                        )
                        db.add(episode)
                        existing_episodes.add(episode_id)
                        stats['new_episodes'] += 1
                        
                        # Update show episode count
                        show.total_episodes_played = (show.total_episodes_played or 0) + 1
            
            # Commit all changes
            db.commit()
            
            # Clear any sync errors
            connection.sync_failure_count = 0
            connection.last_sync_error = None
            db.commit()
            
            logger.info(
                f"Sync completed for user {user_id}: "
                f"{stats['new_shows']} new shows, "
                f"{stats['new_episodes']} new episodes"
            )
            
        except Exception as e:
            logger.error(f"Sync failed for user {user_id}: {str(e)}")
            stats['errors'].append(str(e))
            
            # Update failure tracking
            connection.sync_failure_count = (connection.sync_failure_count or 0) + 1
            connection.last_sync_error = str(e)
            db.commit()
            
            # Don't retry if too many failures
            if connection.sync_failure_count >= 5:
                logger.error(f"Too many sync failures for user {user_id}, disabling sync")
        
        return stats
    
    async def sync_all_users(self) -> dict:
        """Sync podcast data for all users with valid connections"""
        
        total_stats = {
            'users_synced': 0,
            'total_new_shows': 0,
            'total_new_episodes': 0,
            'failed_users': []
        }
        
        async with get_db_session() as db:
            # Get all active connections that need syncing
            connections = db.query(SpotifyConnection).filter(
                SpotifyConnection.sync_failure_count < 5
            ).all()
            
            for connection in connections:
                if connection.needs_sync(hours=self.config.sync_interval_hours):
                    try:
                        stats = await self.sync_user_podcasts(db, connection)
                        
                        if not stats['errors']:
                            total_stats['users_synced'] += 1
                            total_stats['total_new_shows'] += stats['new_shows']
                            total_stats['total_new_episodes'] += stats['new_episodes']
                        else:
                            total_stats['failed_users'].append({
                                'user_id': str(connection.user_id),
                                'errors': stats['errors']
                            })
                            
                    except Exception as e:
                        logger.error(f"Unexpected error syncing user {connection.user_id}: {e}")
                        total_stats['failed_users'].append({
                            'user_id': str(connection.user_id),
                            'errors': [str(e)]
                        })
                    
                    # Add delay between users to respect rate limits
                    await asyncio.sleep(2)
        
        logger.info(
            f"Sync completed: {total_stats['users_synced']} users, "
            f"{total_stats['total_new_shows']} new shows, "
            f"{total_stats['total_new_episodes']} new episodes"
        )
        
        return total_stats


class SpotifySyncScheduler:
    """Schedule periodic syncs for all users"""
    
    def __init__(self):
        self.sync_service = SpotifyDataSync()
        self.config = get_spotify_config()
        self._running = False
    
    async def start(self):
        """Start the sync scheduler"""
        self._running = True
        logger.info("Starting Spotify sync scheduler")
        
        while self._running:
            try:
                # Run sync for all users
                await self.sync_service.sync_all_users()
                
                # Wait for next sync interval
                await asyncio.sleep(self.config.sync_interval_hours * 3600)
                
            except Exception as e:
                logger.error(f"Sync scheduler error: {e}")
                # Wait a bit before retrying
                await asyncio.sleep(300)  # 5 minutes
    
    def stop(self):
        """Stop the sync scheduler"""
        self._running = False
        logger.info("Stopping Spotify sync scheduler")


# Background task runner
async def run_sync_scheduler():
    """Run the sync scheduler as a background task"""
    scheduler = SpotifySyncScheduler()
    
    try:
        await scheduler.start()
    except KeyboardInterrupt:
        scheduler.stop()
        logger.info("Sync scheduler stopped by user")
