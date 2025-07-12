#!/usr/bin/env python3
"""
Spotify Top Songs Fetcher
Gets your top tracks from Spotify

Setup:
1. pip install spotipy
2. Create Spotify App at https://developer.spotify.com/dashboard
3. Set Redirect URI to: http://localhost:8888/callback
4. Add credentials to .env file or export as environment variables
"""

import os
import json
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException

# Spotify API credentials (set these as environment variables)
CLIENT_ID = '93678eeffc8a490c8fa53166491f069d'
CLIENT_SECRET = '583ff0c6001c4d2eb2ac7a4c30e8e33f'
REDIRECT_URI = 'http://127.0.0.1:8888/callback/'

def setup_spotify():
    print("SPOTIPY_REDIRECT_URI:", os.environ.get("SPOTIPY_REDIRECT_URI"))
    """Initialize Spotify client with authentication"""
    try:
        # Check for credentials
        if not CLIENT_ID or not CLIENT_SECRET:
            print("❌ Missing Spotify credentials!")
            print("\nTo fix this:")
            print("1. Go to https://developer.spotify.com/dashboard")
            print("2. Create an app and get Client ID and Client Secret")
            print("3. Set environment variables:")
            print("   On Windows (Command Prompt):")
            print("      set SPOTIFY_CLIENT_ID=your-client-id")
            print("      set SPOTIFY_CLIENT_SECRET=your-client-secret")
            print("   On macOS/Linux (Terminal):")
            print("      export SPOTIFY_CLIENT_ID=your-client-id")
            print("      export SPOTIFY_CLIENT_SECRET=your-client-secret")
            exit(1)
        
        # Set up authentication - changed scope for top tracks
        scope = "user-top-read"
        
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URI,
            scope=scope,
            open_browser=True,
            cache_path='.spotifycache'  # Cache tokens
        ))
        
        # Test connection
        user = sp.current_user()
        print(f"✓ Connected to Spotify as: {user['display_name']}")
        return sp
        
    except Exception as e:
        print(f"❌ Setup error: {e}")
        print("If the browser didn't open, manually visit the authorization URL printed in the console or check your redirect URI.")
        return None

def get_top_tracks(sp, time_range='medium_term', limit=50):
    """Get user's top tracks
    
    Args:
        sp: Spotify client
        time_range: 'short_term' (4 weeks), 'medium_term' (6 months), 'long_term' (all time)
        limit: Number of tracks to fetch (max 50)
    """
    try:
        print(f"\n🎵 Fetching top tracks ({time_range}, limit: {limit})...")
        
        results = sp.current_user_top_tracks(limit=limit, time_range=time_range)
        
        if not results or 'items' not in results:
            print("❌ No results returned from Spotify")
            return []
        
        tracks = []
        for track in results['items']:
            # Extract artist names
            artists = [artist['name'] for artist in track.get('artists', [])]
            
            track_info = {
                'name': track.get('name', 'Unknown'),
                'artists': artists,
                'album': track.get('album', {}).get('name', 'Unknown'),
                'popularity': track.get('popularity', 0),
                'duration_ms': track.get('duration_ms', 0),
                'external_urls': track.get('external_urls', {}).get('spotify', ''),
                'track_id': track.get('id', ''),
                'preview_url': track.get('preview_url', '')
            }
            tracks.append(track_info)
        
        print(f"✓ Found {len(tracks)} top tracks")
        return tracks
        
    except SpotifyException as e:
        print(f"❌ Spotify API error: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected error fetching tracks: {e}")
        return []

def display_tracks(tracks, time_range='medium_term'):
    """Display tracks in a nice format"""
    if not tracks:
        print("\n📭 No top tracks found")
        return
    
    time_range_labels = {
        'short_term': '4 weeks',
        'medium_term': '6 months', 
        'long_term': 'all time'
    }
    
    period = time_range_labels.get(time_range, time_range)
    
    print(f"\n🎵 Your Top Tracks ({period}):")
    print("=" * 60)
    
    for i, track in enumerate(tracks, 1):
        # Convert duration to minutes:seconds
        duration_min = track['duration_ms'] // 60000
        duration_sec = (track['duration_ms'] % 60000) // 1000
        duration_str = f"{duration_min}:{duration_sec:02d}"
        
        # Join artists
        artists_str = ', '.join(track['artists'])
        
        print(f"\n{i:2d}. {track['name']}")
        print(f"     by {artists_str}")
        print(f"     Album: {track['album']}")
        print(f"     Duration: {duration_str}")
        print(f"     Popularity: {track['popularity']}/100")
        if track['external_urls']:
            print(f"     Spotify: {track['external_urls']}")

def save_to_file(tracks, time_range='medium_term', filename=None):
    """Save track data to JSON file"""
    try:
        if not filename:
            filename = f'top_tracks_{time_range}.json'
        
        with open(filename, 'w') as f:
            json.dump(tracks, f, indent=2)
        print(f"\n💾 Saved to {filename}")
    except Exception as e:
        print(f"❌ Error saving file: {e}")

def main():
    """Main function"""
    print("🎵 Spotify Top Songs Fetcher")
    print("=" * 30)
    
    # Setup Spotify connection
    sp = setup_spotify()
    if not sp:
        return
    
    # Get top tracks for different time periods
    time_ranges = ['short_term', 'medium_term', 'long_term']
    
    for time_range in time_ranges:
        tracks = get_top_tracks(sp, time_range=time_range, limit=20)
        
        if tracks:
            display_tracks(tracks, time_range)
            save_to_file(tracks, time_range)
        
        print("\n" + "-" * 60)
    
    print("\n✅ Done! Check the generated JSON files for your data.")

if __name__ == "__main__":
    print("SPOTIPY_REDIRECT_URI:", os.environ.get("SPOTIPY_REDIRECT_URI"))
    main()