#!/usr/bin/env python3
"""
Podcast Data Collection Pipeline
Fetches your saved Spotify episodes and downloads transcripts from YouTube

This script:
1. Connects to your Spotify account
2. Fetches your saved podcast episodes
3. Searches YouTube for matching episodes
4. Downloads transcripts using YouTube's auto-captions
5. Saves everything to the organized data structure

Usage:
    python collect_transcripts.py                    # Auto-download mode (default)
    python collect_transcripts.py --interactive     # Interactive mode with prompts
    python collect_transcripts.py --limit 10        # Limit to 10 episodes
    python collect_transcripts.py --update-only     # Only fetch new Spotify episodes
"""

import os
import sys
import subprocess
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
import argparse

# Add current directory to path for imports
current_dir = Path(__file__).parent
sys.path.insert(0, str(current_dir))

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('data_collection.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def check_dependencies():
    """Check if required dependencies are installed"""
    required_packages = [
        ('spotipy', 'pip install spotipy'),
        ('youtube_transcript_api', 'pip install youtube-transcript-api'),
        ('yt_dlp', 'pip install yt-dlp')
    ]
    
    missing = []
    for package, install_cmd in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing.append((package, install_cmd))
    
    if missing:
        logger.error("❌ Missing dependencies:")
        for package, install_cmd in missing:
            logger.error(f"   {install_cmd}")
        logger.error("\nPlease install missing dependencies and try again.")
        return False
    
    logger.info("✅ All dependencies are installed")
    return True

def check_environment():
    """Check if required environment variables are set"""
    required_vars = ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET']
    missing = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing.append(var)
    
    if missing:
        logger.error("❌ Missing environment variables:")
        for var in missing:
            logger.error(f"   {var}")
        logger.error("\nPlease set these in config/env/config.env")
        logger.error("See config/env/config.env.example for template")
        return False
    
    logger.info("✅ Environment variables are configured")
    return True

def load_environment():
    """Load environment variables from config file"""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'env' / 'config.env'
    
    if config_path.exists():
        logger.info(f"📄 Loading environment from {config_path}")
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    else:
        logger.warning(f"⚠️ Config file not found: {config_path}")
        logger.info("💡 Copy config/env/config.env.example to config/env/config.env")

def run_spotify_fetcher(limit: int = 50) -> bool:
    """Run the Spotify fetcher script"""
    logger.info("🎵 Fetching saved episodes from Spotify...")
    
    script_path = current_dir / 'spotify_fetcher.py'
    
    try:
        # Change to the script directory so relative paths work
        original_cwd = os.getcwd()
        os.chdir(script_path.parent)
        
        # Import and run the spotify fetcher
        sys.path.insert(0, str(script_path.parent))
        
        # Set the output path for saved episodes
        output_path = Path(__file__).parent.parent.parent / 'data' / 'exports' / 'saved_podcasts.json'
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        from spotify_fetcher import setup_spotify, get_saved_episodes, save_to_file
        
        # Run the Spotify fetcher
        sp = setup_spotify()
        episodes = get_saved_episodes(sp, limit=limit)
        
        if episodes:
            save_to_file(episodes, str(output_path))
            logger.info(f"✅ Saved {len(episodes)} episodes to {output_path}")
            return True
        else:
            logger.warning("⚠️ No episodes found in your Spotify saved episodes")
            return False
            
    except Exception as e:
        logger.error(f"❌ Error fetching Spotify episodes: {e}")
        return False
    finally:
        os.chdir(original_cwd)

def run_youtube_transcript_downloader(auto_confirm: bool = False, max_episodes: Optional[int] = None) -> bool:
    """Run the YouTube transcript downloader"""
    logger.info("📺 Downloading transcripts from YouTube...")
    
    script_path = current_dir / 'download_youtube_transcripts.py'
    saved_podcasts_path = Path(__file__).parent.parent.parent / 'data' / 'exports' / 'saved_podcasts.json'
    
    if not saved_podcasts_path.exists():
        logger.error(f"❌ Saved podcasts file not found: {saved_podcasts_path}")
        return False
    
    try:
        # Change to the script directory
        original_cwd = os.getcwd()
        os.chdir(script_path.parent)
        
        # Copy saved_podcasts.json to the working directory temporarily
        import shutil
        temp_saved_podcasts = script_path.parent / 'saved_podcasts.json'
        shutil.copy2(saved_podcasts_path, temp_saved_podcasts)
        
        # Import and run the YouTube transcript downloader
        sys.path.insert(0, str(script_path.parent))
        from download_youtube_transcripts import process_saved_podcasts
        
        # Run the transcript downloader with auto-confirm enabled by default
        process_saved_podcasts(auto_confirm=True, max_episodes=max_episodes)
        
        # Clean up temporary file
        if temp_saved_podcasts.exists():
            temp_saved_podcasts.unlink()
        
        logger.info("✅ YouTube transcript download completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Error downloading YouTube transcripts: {e}")
        return False
    finally:
        os.chdir(original_cwd)

def get_transcript_stats() -> Dict:
    """Get statistics about downloaded transcripts"""
    transcript_dir = Path(__file__).parent.parent.parent / 'data' / 'transcripts'
    
    if not transcript_dir.exists():
        return {'count': 0, 'total_size': 0}
    
    transcript_files = list(transcript_dir.glob('*.txt'))
    total_size = sum(f.stat().st_size for f in transcript_files)
    
    return {
        'count': len(transcript_files),
        'total_size': total_size,
        'total_size_mb': round(total_size / (1024 * 1024), 2),
        'newest': max((f.stat().st_mtime for f in transcript_files), default=0)
    }

def display_summary():
    """Display a summary of the collection results"""
    logger.info("\n" + "="*60)
    logger.info("📊 COLLECTION SUMMARY")
    logger.info("="*60)
    
    # Spotify episodes
    saved_podcasts_path = Path(__file__).parent.parent.parent / 'data' / 'exports' / 'saved_podcasts.json'
    if saved_podcasts_path.exists():
        with open(saved_podcasts_path) as f:
            episodes = json.load(f)
        logger.info(f"🎵 Spotify Episodes: {len(episodes)}")
    else:
        logger.info("🎵 Spotify Episodes: 0 (not fetched)")
    
    # Transcripts
    stats = get_transcript_stats()
    logger.info(f"📺 Downloaded Transcripts: {stats['count']}")
    logger.info(f"💾 Total Size: {stats['total_size_mb']} MB")
    
    if stats['newest'] > 0:
        newest_date = datetime.fromtimestamp(stats['newest'])
        logger.info(f"📅 Latest Download: {newest_date.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Data locations
    logger.info(f"\n📁 Data Locations:")
    logger.info(f"   Episodes: data/exports/saved_podcasts.json")
    logger.info(f"   Transcripts: data/transcripts/")
    logger.info(f"   Database: data/databases/podcast_index_v2.db")
    
    logger.info("\n🚀 Next Steps:")
    logger.info("   1. Run: python run_server.py")
    logger.info("   2. Open: http://localhost:3000/api/health")
    logger.info("   3. Start frontend: cd frontend && npm start")
    logger.info("="*60)

def main():
    parser = argparse.ArgumentParser(description="Podcast Data Collection Pipeline")
    parser.add_argument("--interactive", action="store_true", 
                       help="Interactive mode with prompts (default is auto-download)")
    parser.add_argument("--limit", type=int, default=50,
                       help="Limit number of Spotify episodes to fetch (default: 50)")
    parser.add_argument("--max-transcripts", type=int,
                       help="Maximum number of transcripts to download")
    parser.add_argument("--update-only", action="store_true",
                       help="Only fetch new Spotify episodes, skip transcript download")
    parser.add_argument("--transcripts-only", action="store_true",
                       help="Only download transcripts, skip Spotify fetch")
    parser.add_argument("--skip-checks", action="store_true",
                       help="Skip dependency and environment checks")
    
    args = parser.parse_args()
    
    logger.info("🚀 Starting Podcast Data Collection Pipeline")
    logger.info(f"📅 Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load environment
    load_environment()
    
    # Run checks
    if not args.skip_checks:
        if not check_dependencies():
            return 1
        
        if not check_environment():
            return 1
    
    success = True
    
    # Step 1: Fetch Spotify episodes (unless skipping)
    if not args.transcripts_only:
        logger.info("\n" + "="*60)
        logger.info("STEP 1: Fetching Spotify Episodes")
        logger.info("="*60)
        
        if not run_spotify_fetcher(limit=args.limit):
            logger.error("❌ Failed to fetch Spotify episodes")
            success = False
        
        if args.update_only:
            logger.info("✅ Update-only mode: Spotify episodes updated")
            display_summary()
            return 0 if success else 1
    
    # Step 2: Download YouTube transcripts (unless skipping)
    if not args.update_only:
        logger.info("\n" + "="*60)
        logger.info("STEP 2: Downloading YouTube Transcripts")
        logger.info("="*60)
        
        if not run_youtube_transcript_downloader(
            auto_confirm=not args.interactive,  # Auto-confirm unless interactive mode is requested
            max_episodes=args.max_transcripts
        ):
            logger.error("❌ Failed to download YouTube transcripts")
            success = False
    
    # Display summary
    display_summary()
    
    if success:
        logger.info("🎉 Data collection pipeline completed successfully!")
        return 0
    else:
        logger.error("❌ Data collection pipeline completed with errors")
        return 1

if __name__ == "__main__":
    try:
        exit_code = main()
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️ Collection interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)