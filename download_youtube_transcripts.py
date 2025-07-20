#!/usr/bin/env python3
"""
download_youtube_transcripts.py

Download transcripts from YouTube for podcast episodes.
Many popular podcasts are uploaded to YouTube with auto-generated captions.

Setup:
pip install youtube-transcript-api yt-dlp

Usage:
python download_youtube_transcripts.py --auto-search
python download_youtube_transcripts.py --episode-name "DHH Ruby on Rails" --show "Lex Fridman"
"""

import json
import os
import re
import argparse
from typing import List, Dict, Optional
from pathlib import Path
import time

try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api.formatters import TextFormatter
except ImportError:
    print("❌ Missing dependencies. Install with:")
    print("pip install youtube-transcript-api yt-dlp")
    exit(1)

try:
    import yt_dlp
except ImportError:
    print("❌ Missing yt-dlp. Install with: pip install yt-dlp")
    exit(1)

# Configuration
OUTPUT_DIR = "transcripts"
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    """Clean filename for filesystem compatibility"""
    return re.sub(r'[^A-Za-z0-9 _\-.]', '_', name).strip()[:200]

def search_youtube_for_episode(episode_name: str, show_name: str, max_results: int = 5) -> List[Dict]:
    """Search YouTube for a specific podcast episode"""
    
    # Create search query
    search_query = f"{show_name} {episode_name} podcast"
    print(f"🔍 Searching YouTube for: {search_query}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True,
    }
    
    results = []
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Search for videos
            search_results = ydl.extract_info(
                f"ytsearch{max_results}:{search_query}",
                download=False
            )
            
            if search_results and 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry:
                        results.append({
                            'video_id': entry['id'],
                            'title': entry['title'],
                            'url': f"https://www.youtube.com/watch?v={entry['id']}",
                            'duration': entry.get('duration'),
                            'uploader': entry.get('uploader', 'Unknown')
                        })
    
    except Exception as e:
        print(f"❌ Error searching YouTube: {e}")
    
    return results

def get_transcript_from_youtube(video_id: str) -> Optional[str]:
    """Download transcript from YouTube video"""
    
    try:
        # Try to get transcript in English first, then any available language
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        transcript = None
        
        # Try English first
        try:
            transcript = transcript_list.find_transcript(['en', 'en-US', 'en-GB'])
        except:
            # Fall back to any available transcript
            try:
                transcript = transcript_list.find_manually_created_transcript(['en'])
            except:
                try:
                    # Try auto-generated
                    transcript = transcript_list.find_generated_transcript(['en'])
                except:
                    # Get any available transcript
                    available_transcripts = list(transcript_list)
                    if available_transcripts:
                        transcript = available_transcripts[0]
        
        if not transcript:
            return None
        
        # Fetch the actual transcript
        transcript_data = transcript.fetch()
        
        # Format as plain text
        formatter = TextFormatter()
        text = formatter.format_transcript(transcript_data)
        
        return text
    
    except Exception as e:
        print(f"  ❌ Error getting transcript: {e}")
        return None

def process_saved_podcasts(auto_confirm: bool = False, max_episodes: Optional[int] = None):
    """Process episodes from saved_podcasts.json"""
    
    try:
        with open("saved_podcasts.json", "r") as f:
            episodes = json.load(f)
    except FileNotFoundError:
        print("❌ saved_podcasts.json not found")
        return
    
    print(f"📱 Processing {len(episodes)} saved episodes...")
    
    if max_episodes:
        episodes = episodes[:max_episodes]
        print(f"🔢 Limited to first {max_episodes} episodes")
    
    success_count = 0
    
    for i, episode in enumerate(episodes):
        print(f"\n📍 Episode {i+1}/{len(episodes)}: {episode['name'][:50]}...")
        print(f"   Show: {episode['show']}")
        
        # Check if transcript already exists
        date_str = episode.get("saved_at", "unknown_date")[:10]
        filename = f"{date_str}_{sanitize_filename(episode['show'])}_{sanitize_filename(episode['name'])}.txt"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        if os.path.exists(output_path):
            print(f"  ⏭️  Already exists: {filename}")
            continue
        
        # Search YouTube for this episode
        search_results = search_youtube_for_episode(episode['name'], episode['show'])
        
        if not search_results:
            print(f"  ❌ No YouTube results found")
            continue
        
        print(f"  🔍 Found {len(search_results)} YouTube results:")
        
        best_match = None
        
        for j, result in enumerate(search_results):
            print(f"     {j+1}. {result['title'][:60]}...")
            print(f"        Channel: {result['uploader']}")
            
            # Simple heuristic to find best match
            title_lower = result['title'].lower()
            episode_name_lower = episode['name'].lower()
            show_name_lower = episode['show'].lower()
            
            # Check if title contains key terms from episode and show
            episode_words = set(episode_name_lower.split())
            show_words = set(show_name_lower.split())
            title_words = set(title_lower.split())
            
            episode_match_score = len(episode_words.intersection(title_words))
            show_match_score = len(show_words.intersection(title_words))
            
            if episode_match_score > 0 or show_match_score > 1:
                best_match = result
                print(f"        ✅ Good match (episode: {episode_match_score}, show: {show_match_score})")
                break
        
        if not best_match:
            best_match = search_results[0]  # Use first result as fallback
        
        # Ask for confirmation unless auto_confirm is True
        if not auto_confirm:
            confirm = input(f"  ❓ Download transcript for: {best_match['title'][:60]}? [Y/n/s(kip)]: ").strip().lower()
            if confirm in ['n', 'no']:
                print(f"  ⏭️  Skipped")
                continue
            elif confirm in ['s', 'skip']:
                print(f"  ⏭️  Skipped")
                continue
        
        # Download transcript
        print(f"  ⬇️  Downloading transcript from YouTube...")
        transcript_text = get_transcript_from_youtube(best_match['video_id'])
        
        if transcript_text:
            # Add metadata to transcript
            metadata = f"""# Podcast Transcript
# Show: {episode['show']}
# Episode: {episode['name']}
# YouTube URL: {best_match['url']}
# Downloaded: {time.strftime('%Y-%m-%d %H:%M:%S')}

"""
            
            full_transcript = metadata + transcript_text
            
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(full_transcript)
            
            print(f"  ✅ Saved transcript: {filename}")
            success_count += 1
        else:
            print(f"  ❌ Could not download transcript")
        
        time.sleep(1)  # Be respectful to YouTube
    
    print(f"\n🎉 Successfully downloaded {success_count} transcripts!")
    print(f"📂 Saved to: {OUTPUT_DIR}/")

def process_single_episode(episode_name: str, show_name: str):
    """Process a single episode by name"""
    
    print(f"🎯 Searching for: '{episode_name}' from '{show_name}'")
    
    search_results = search_youtube_for_episode(episode_name, show_name)
    
    if not search_results:
        print("❌ No YouTube results found")
        return
    
    print(f"🔍 Found {len(search_results)} results:")
    
    for i, result in enumerate(search_results):
        print(f"  {i+1}. {result['title']}")
        print(f"     Channel: {result['uploader']}")
        print(f"     URL: {result['url']}")
    
    # Ask user to choose
    try:
        choice = int(input(f"\nChoose video (1-{len(search_results)}): ")) - 1
        if choice < 0 or choice >= len(search_results):
            print("❌ Invalid choice")
            return
    except ValueError:
        print("❌ Invalid input")
        return
    
    chosen_video = search_results[choice]
    
    # Download transcript
    print(f"\n⬇️  Downloading transcript for: {chosen_video['title']}")
    transcript_text = get_transcript_from_youtube(chosen_video['video_id'])
    
    if transcript_text:
        filename = f"{sanitize_filename(show_name)}_{sanitize_filename(episode_name)}.txt"
        output_path = os.path.join(OUTPUT_DIR, filename)
        
        metadata = f"""# Podcast Transcript
# Show: {show_name}
# Episode: {episode_name}
# YouTube URL: {chosen_video['url']}
# Downloaded: {time.strftime('%Y-%m-%d %H:%M:%S')}

"""
        
        full_transcript = metadata + transcript_text
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(full_transcript)
        
        print(f"✅ Saved transcript: {filename}")
    else:
        print("❌ Could not download transcript")

def main():
    parser = argparse.ArgumentParser(description="Download podcast transcripts from YouTube")
    parser.add_argument("--auto-search", action="store_true", 
                        help="Automatically process all episodes from saved_podcasts.json")
    parser.add_argument("--episode-name", help="Name of specific episode to search for")
    parser.add_argument("--show", help="Name of podcast show")
    parser.add_argument("--auto-confirm", action="store_true", 
                        help="Auto-confirm transcript downloads (don't ask for confirmation)")
    parser.add_argument("--max-episodes", type=int, help="Maximum episodes to process")
    
    args = parser.parse_args()
    
    print("📺 YouTube Podcast Transcript Downloader")
    print("=" * 50)
    
    if args.auto_search:
        process_saved_podcasts(auto_confirm=args.auto_confirm, max_episodes=args.max_episodes)
    
    elif args.episode_name and args.show:
        process_single_episode(args.episode_name, args.show)
    
    else:
        print("Usage options:")
        print("1. Process all saved episodes: --auto-search")
        print("2. Process specific episode: --episode-name 'Episode Name' --show 'Show Name'")
        print("\nOptional flags:")
        print("  --auto-confirm: Don't ask for confirmation")
        print("  --max-episodes N: Limit to first N episodes")
        
        # Interactive mode
        choice = input("\nStart interactive mode? [Y/n]: ").strip().lower()
        if choice not in ['n', 'no']:
            process_saved_podcasts(auto_confirm=False)

if __name__ == "__main__":
    main() 