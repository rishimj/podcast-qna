#!/usr/bin/env python3
"""
download_podcast_transcripts.py

Comprehensive podcast transcript fetcher that handles multiple approaches:
1. RSS feeds with transcript links (like Software Engineering Daily)
2. Audio transcription using OpenAI Whisper API
3. Local Whisper transcription
4. Web scraping for show-specific transcript pages

Usage:
    python download_podcast_transcripts.py --method rss --shows "Software Engineering Daily"
    python download_podcast_transcripts.py --method whisper-api --api-key YOUR_KEY
    python download_podcast_transcripts.py --method whisper-local
"""

import json
import os
import re
import requests
import argparse
from datetime import datetime
from pathlib import Path
import time
import subprocess
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

# Configuration
OUTPUT_DIR = "../../data/transcripts"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
}

# Create output directory
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    """Clean filename for filesystem compatibility"""
    return re.sub(r'[^A-Za-z0-9 _\-.]', '_', name).strip()[:200]

def get_rss_feeds():
    """Known RSS feeds for podcasts that provide transcripts"""
    return {
        "Software Engineering Daily": "https://softwareengineeringdaily.com/feed/",
        # Add more as discovered
    }

def download_from_rss(show_names: List[str], max_episodes: int = 5):
    """Download transcripts from RSS feeds (Method 1)"""
    print(f"📡 Downloading transcripts via RSS feeds...")
    
    rss_feeds = get_rss_feeds()
    
    for show_name in show_names:
        if show_name not in rss_feeds:
            print(f"❌ No RSS feed configured for '{show_name}'")
            continue
            
        rss_url = rss_feeds[show_name]
        print(f"\n🔍 Processing {show_name}...")
        
        try:
            resp = requests.get(rss_url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            
            soup = BeautifulSoup(resp.text, "xml")
            items = soup.find_all("item")[:max_episodes]
            
            for item in items:
                title = item.title.text if item.title else "untitled"
                pubdate = item.pubDate.text if item.pubDate else ""
                
                # Parse date
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pubdate)
                    date_str = dt.strftime("%Y-%m-%d")
                except:
                    date_str = "unknown_date"
                
                # Look for transcript links
                content_encoded = item.find("content:encoded")
                if not content_encoded or not content_encoded.string:
                    continue
                
                html_soup = BeautifulSoup(content_encoded.string, "html.parser")
                transcript_link = html_soup.find("a", href=re.compile(r"\.txt$"))
                
                if not transcript_link:
                    continue
                
                transcript_url = transcript_link["href"]
                filename = f"{date_str}_{sanitize_filename(title)}.txt"
                output_path = os.path.join(OUTPUT_DIR, filename)
                
                if os.path.exists(output_path):
                    print(f"  ⏭️  Already exists: {filename}")
                    continue
                
                # Download transcript
                print(f"  ⬇️  Downloading: {title[:50]}...")
                try:
                    tx_resp = requests.get(transcript_url, headers=HEADERS, timeout=10)
                    tx_resp.raise_for_status()
                    
                    with open(output_path, "wb") as f:
                        f.write(tx_resp.content)
                    
                    print(f"  ✅ Saved: {filename}")
                except Exception as e:
                    print(f"  ❌ Error downloading transcript: {e}")
                
                time.sleep(0.5)  # Be respectful
        
        except Exception as e:
            print(f"❌ Error processing {show_name}: {e}")

def get_episode_audio_info(episode_data: Dict) -> Optional[str]:
    """
    Try to get audio URL for episode. 
    Note: Spotify doesn't provide direct audio URLs, so this is a placeholder
    for when we implement audio discovery methods.
    """
    # This would need to be implemented based on:
    # 1. Show-specific RSS feeds that include audio URLs
    # 2. Web scraping show websites
    # 3. Third-party APIs
    
    print(f"  ℹ️  Audio discovery not yet implemented for Spotify episodes")
    return None

def transcribe_with_openai_whisper(audio_file_path: str, api_key: str) -> str:
    """Transcribe audio using OpenAI Whisper API"""
    import openai
    
    client = openai.OpenAI(api_key=api_key)
    
    print(f"  🎙️  Transcribing with OpenAI Whisper API...")
    
    with open(audio_file_path, "rb") as audio_file:
        transcript = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text"
        )
    
    return transcript

def transcribe_with_local_whisper(audio_file_path: str, model: str = "base") -> str:
    """Transcribe audio using local Whisper installation"""
    print(f"  🎙️  Transcribing with local Whisper (model: {model})...")
    
    try:
        # Use whisper command line tool
        cmd = ["whisper", audio_file_path, "--model", model, "--output_format", "txt", "--output_dir", "/tmp"]
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        
        # Read the generated transcript
        audio_basename = os.path.splitext(os.path.basename(audio_file_path))[0]
        transcript_path = f"/tmp/{audio_basename}.txt"
        
        if os.path.exists(transcript_path):
            with open(transcript_path, "r") as f:
                transcript = f.read()
            os.remove(transcript_path)  # Cleanup
            return transcript
        else:
            raise Exception("Transcript file not generated")
    
    except subprocess.CalledProcessError as e:
        raise Exception(f"Whisper command failed: {e}")
    except FileNotFoundError:
        raise Exception("Whisper not installed. Install with: pip install openai-whisper")

def download_from_saved_episodes(method: str, **kwargs):
    """Download transcripts for episodes from saved_podcasts.json"""
    
    # Load saved episodes
    try:
        with open("saved_podcasts.json", "r") as f:
            episodes = json.load(f)
    except FileNotFoundError:
        print("❌ saved_podcasts.json not found")
        return
    
    print(f"🎧 Processing {len(episodes)} saved episodes using method: {method}")
    
    for i, episode in enumerate(episodes):
        print(f"\n📍 Episode {i+1}/{len(episodes)}: {episode['name'][:50]}...")
        print(f"   Show: {episode['show']}")
        
        date_str = episode.get("saved_at", "unknown_date")[:10]  # YYYY-MM-DD
        filename = f"{date_str}_{sanitize_filename(episode['show'])}_{sanitize_filename(episode['name'])}.txt"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        if os.path.exists(output_path):
            print(f"  ⏭️  Already exists: {filename}")
            continue
        
        if method == "whisper-api" or method == "whisper-local":
            # Try to get audio URL
            audio_url = get_episode_audio_info(episode)
            
            if not audio_url:
                print(f"  ❌ No audio URL available for this episode")
                print(f"      Consider checking show website or RSS feed for audio links")
                continue
            
            # Download audio (placeholder - would need implementation)
            print(f"  ⬇️  Audio download not yet implemented")
            continue
        
        elif method == "web-scrape":
            # Try to find transcript on show website
            transcript_text = scrape_transcript_from_web(episode)
            
            if transcript_text:
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(transcript_text)
                print(f"  ✅ Saved transcript: {filename}")
            else:
                print(f"  ❌ No transcript found via web scraping")

def scrape_transcript_from_web(episode_data: Dict) -> Optional[str]:
    """
    Try to scrape transcript from show websites
    This is show-specific and would need custom logic for each podcast
    """
    
    show_name = episode_data["show"]
    episode_name = episode_data["name"]
    
    # Show-specific scraping logic would go here
    if "Software Engineering Daily" in show_name:
        return scrape_sed_transcript(episode_data)
    elif "All-In" in show_name:
        return scrape_allin_transcript(episode_data)
    # Add more show-specific scrapers
    
    return None

def scrape_sed_transcript(episode_data: Dict) -> Optional[str]:
    """Scrape transcript from Software Engineering Daily website"""
    # This would implement SED-specific scraping
    print("  ℹ️  SED web scraping not implemented - use RSS method instead")
    return None

def scrape_allin_transcript(episode_data: Dict) -> Optional[str]:
    """Scrape transcript from All-In podcast website"""
    # All-In doesn't typically provide transcripts, but we could check
    print("  ℹ️  All-In typically doesn't provide transcripts")
    return None

def suggest_manual_approaches():
    """Suggest manual approaches for getting transcripts"""
    print("\n💡 MANUAL APPROACHES FOR TRANSCRIPTS:")
    print("\n1. Check Show Websites:")
    print("   - Many shows post transcripts on their websites")
    print("   - Look for 'transcript' or 'show notes' sections")
    
    print("\n2. Community Resources:")
    print("   - Reddit communities often share transcripts")
    print("   - Fan sites and blogs")
    print("   - Podcast databases like PodcastNotes.org")
    
    print("\n3. Audio Transcription Services:")
    print("   - Otter.ai (upload audio files)")
    print("   - Rev.com (professional transcription)")
    print("   - Descript (AI transcription with editing)")
    
    print("\n4. YouTube Transcripts:")
    print("   - Many podcasts upload to YouTube with auto-generated captions")
    print("   - Use youtube-dl + YouTube caption extraction")
    
    print("\n5. Browser Extensions:")
    print("   - Some extensions can transcribe audio in real-time")
    print("   - Useful for listening and generating transcripts simultaneously")

def main():
    parser = argparse.ArgumentParser(description="Download podcast transcripts using various methods")
    parser.add_argument("--method", choices=["rss", "whisper-api", "whisper-local", "web-scrape", "suggest"], 
                        default="suggest", help="Transcript acquisition method")
    parser.add_argument("--shows", nargs="+", help="Show names to process (for RSS method)")
    parser.add_argument("--api-key", help="OpenAI API key (for whisper-api method)")
    parser.add_argument("--max-episodes", type=int, default=5, help="Maximum episodes to process per show")
    parser.add_argument("--whisper-model", default="base", help="Whisper model size (for local whisper)")
    
    args = parser.parse_args()
    
    print("🎙️  Podcast Transcript Downloader")
    print("=" * 50)
    
    if args.method == "rss":
        if not args.shows:
            print("❌ --shows required for RSS method")
            print("Available shows with RSS transcripts:")
            for show in get_rss_feeds():
                print(f"  - {show}")
            return
        
        download_from_rss(args.shows, args.max_episodes)
    
    elif args.method == "whisper-api":
        if not args.api_key:
            print("❌ --api-key required for OpenAI Whisper API method")
            return
        
        download_from_saved_episodes(args.method, api_key=args.api_key)
    
    elif args.method == "whisper-local":
        download_from_saved_episodes(args.method, model=args.whisper_model)
    
    elif args.method == "web-scrape":
        download_from_saved_episodes(args.method)
    
    elif args.method == "suggest":
        suggest_manual_approaches()
    
    print(f"\n✅ Transcripts saved to: {OUTPUT_DIR}/")
    print("🤖 Use with your existing RAG scripts: podcast_rag.py, rag_sed.py, etc.")

if __name__ == "__main__":
    main() 