#!/usr/bin/env python3
"""
check_podcast_transcripts.py

Check which saved podcasts have transcripts available via RSS feeds.
Based on the existing download_sed_transcripts.py pattern.
"""

import json
import requests
import re
from bs4 import BeautifulSoup
import time

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
}

def get_known_rss_feeds():
    """Return known RSS feeds for popular podcasts"""
    return {
        "Software Engineering Daily": "https://softwareengineeringdaily.com/feed/",
    }

def check_rss_for_transcripts(rss_url, show_name):
    """Check if RSS feed contains transcript links"""
    try:
        print(f"Checking RSS feed for {show_name}...")
        resp = requests.get(rss_url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        
        soup = BeautifulSoup(resp.text, "xml")
        items = soup.find_all("item")[:3]
        
        transcript_found = False
        for item in items:
            title = item.title.text if item.title else "Unknown"
            
            content_encoded = item.find("content:encoded")
            if content_encoded and content_encoded.string:
                html = content_encoded.string
                html_soup = BeautifulSoup(html, "html.parser")
                
                transcript_links = html_soup.find_all("a", href=re.compile(r"\.(txt|pdf|doc)$"))
                if transcript_links:
                    transcript_found = True
                    print(f"  ✅ Found transcript links in '{title[:50]}...'")
                    break
        
        if not transcript_found:
            print(f"  ❌ No transcript links found")
        
        return transcript_found
    
    except Exception as e:
        print(f"  ❌ Error checking {show_name}: {e}")
        return False

def analyze_saved_podcasts():
    """Analyze saved podcasts for transcript availability"""
    try:
        with open("saved_podcasts.json", "r") as f:
            podcasts = json.load(f)
    except FileNotFoundError:
        print("❌ saved_podcasts.json not found")
        return
    
    print(f"📊 Analyzing {len(podcasts)} saved podcast episodes...")
    
    shows = {}
    for ep in podcasts:
        show = ep["show"]
        if show not in shows:
            shows[show] = []
        shows[show].append(ep)
    
    print(f"📻 Found {len(shows)} unique shows:")
    for show in shows:
        print(f"  - {show} ({len(shows[show])} episodes)")
    
    print("\n" + "="*60)
    print("TRANSCRIPT AVAILABILITY CHECK")
    print("="*60)
    
    known_feeds = get_known_rss_feeds()
    transcript_available = []
    no_transcripts = []
    
    for show_name in shows:
        print(f"\n🔍 Checking: {show_name}")
        
        if show_name in known_feeds:
            rss_url = known_feeds[show_name]
            print(f"  📡 Known RSS: {rss_url}")
            
            has_transcripts = check_rss_for_transcripts(rss_url, show_name)
            if has_transcripts:
                transcript_available.append({
                    "show": show_name,
                    "rss_url": rss_url,
                    "episodes": len(shows[show_name])
                })
            else:
                no_transcripts.append(show_name)
        else:
            print(f"  ❓ RSS feed unknown - try YouTube approach")
            no_transcripts.append(show_name)
        
        time.sleep(0.5)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    if transcript_available:
        print(f"\n✅ SHOWS WITH RSS TRANSCRIPTS ({len(transcript_available)}):")
        for item in transcript_available:
            print(f"  - {item['show']} ({item['episodes']} episodes)")
            print(f"    RSS: {item['rss_url']}")
    
    if no_transcripts:
        print(f"\n📺 SHOWS FOR YOUTUBE APPROACH ({len(no_transcripts)}):")
        for show in no_transcripts:
            episodes = len(shows[show])
            print(f"  - {show} ({episodes} episodes)")
    
    print(f"\n💡 RECOMMENDED WORKFLOW:")
    print("1. Use RSS approach for shows with transcript links")
    print("2. Use YouTube approach for most others:")
    print("   python3 download_youtube_transcripts.py --auto-search --auto-confirm")

if __name__ == "__main__":
    analyze_saved_podcasts() 