#!/usr/bin/env python3
"""
Spotify Saved Podcasts Fetcher
Gets your saved (♥) podcast episodes from Spotify

Setup:
1. pip install spotipy
2. Create Spotify App at https://developer.spotify.com/dashboard
3. Register Redirect URI: http://127.0.0.1:8888/callback/
4. Add credentials to .env or export as environment variables
"""

import os, json
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyOAuth

CLIENT_ID     = '93678eeffc8a490c8fa53166491f069d'
CLIENT_SECRET = '583ff0c6001c4d2eb2ac7a4c30e8e33f'
REDIRECT_URI  = 'http://127.0.0.1:8888/callback/'

def setup_spotify():
    scope = "user-library-read"
    auth = SpotifyOAuth(
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        redirect_uri=REDIRECT_URI,
        scope=scope,
        open_browser=True,
        cache_path='.spotifycache')
    sp = spotipy.Spotify(auth_manager=auth)
    user = sp.current_user()
    print(f"✓ Connected as {user['display_name']}")
    return sp

def get_saved_episodes(sp, limit=50):
    print(f"\nFetching up to {limit} saved episodes…")
    results = sp.current_user_saved_episodes(limit=limit)
    items = results.get('items', [])
    eps = []
    for item in items:
        ep = item['episode']
        eps.append({
            'name': ep['name'],
            'show': ep['show']['name'],
            'saved_at': item['added_at'],
            'duration_ms': ep['duration_ms'],
            'url': ep['external_urls']['spotify'],
            'id': ep['id']
        })
    print(f"✓ Retrieved {len(eps)} episodes")
    return eps

def display_episodes(eps):
    if not eps:
        print("📭 No saved episodes found.")
        return
    print("\n🎧 Your Saved Episodes:")
    for i, ep in enumerate(eps,1):
        dt = datetime.fromisoformat(ep['saved_at'].replace('Z','+00:00'))
        m, s = divmod(ep['duration_ms']//1000, 60)
        print(f"{i:2d}. {ep['name']} (Show: {ep['show']})")
        print(f"     Saved at: {dt:%Y-%m-%d %H:%M:%S}")
        print(f"     Duration: {m}:{s:02d} | ▶ {ep['url']}")

def save_to_file(eps, fn='saved_podcasts.json'):
    with open(fn,'w') as f:
        json.dump(eps, f, indent=2)
    print(f"💾 Saved to {fn}")

def main():
    sp = setup_spotify()
    eps = get_saved_episodes(sp, limit=50)
    display_episodes(eps)
    if eps:
        save_to_file(eps)

if __name__=="__main__":
    main()
