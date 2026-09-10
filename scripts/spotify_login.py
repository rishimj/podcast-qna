#!/usr/bin/env python3
"""One-time interactive Spotify login for the daily refresh job.

Run this after rotating Spotify app credentials (or when daily_refresh.log says
"SPOTIFY RE-AUTH NEEDED"). It opens a browser for login and writes the token to
the cache that daily_refresh.sh / spotify_fetcher.py actually read.
"""
import os
from pathlib import Path

import spotipy
from spotipy.oauth2 import SpotifyOAuth

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "backend" / "data_collection" / ".spotifycache"

# Same parsing as daily_refresh.sh; config.env is not safe to `source` in a shell.
for line in open(ROOT / "config" / "env" / "config.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

# A token from a previous app can never refresh under new credentials.
CACHE.unlink(missing_ok=True)

auth = SpotifyOAuth(
    client_id=os.environ["SPOTIFY_CLIENT_ID"],
    client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
    redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback/"),
    scope="user-library-read",
    open_browser=True,
    cache_path=str(CACHE),
)
sp = spotipy.Spotify(auth_manager=auth)
print(f"✓ Connected as {sp.current_user()['display_name']}")
print(f"✓ Saved episodes visible: {sp.current_user_saved_episodes(limit=1)['total']}")
print(f"✓ Token cached at {CACHE.relative_to(ROOT)}")
