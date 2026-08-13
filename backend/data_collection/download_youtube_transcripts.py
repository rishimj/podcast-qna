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
PROJECT_ROOT = Path(__file__).parent.parent.parent
OUTPUT_DIR = str(PROJECT_ROOT / "data" / "transcripts")
SAVED_PODCASTS_PATH = PROJECT_ROOT / "data" / "exports" / "saved_podcasts.json"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# --- Episode match verification --------------------------------------------
# Spotify gives us episode metadata but no transcript, so we find the episode
# on YouTube. A wrong match is worse than no match: the bot then answers
# confidently about an episode the user never saved. Every candidate must be
# corroborated by runtime and title before we accept it.

STOPWORDS = {
    'a', 'an', 'and', 'the', 'of', 'for', 'to', 'in', 'on', 'with', 'at',
    'by', 'from', 'is', 'it', 'its', 'as', 'or', 'vs', 'ep', 'episode',
    'part', 'podcast', 'show', 'w', 'ft', 'feat', 'featuring', 'full',
}

# Runtime within this fraction of Spotify's is treated as the same episode...
DURATION_TOLERANCE_FRAC = 0.05
# ...as is anything inside this absolute window (ads/intros shift short episodes).
DURATION_TOLERANCE_ABS_S = 60
# Past this relative gap it is a clip or a different episode entirely.
DURATION_MISMATCH_FRAC = 0.25

# Share of episode-title words that must appear in the video title.
MIN_TITLE_RECALL = 0.4
# A lower bar is acceptable when the channel clearly identifies the show.
MIN_TITLE_RECALL_WITH_SHOW = 0.25
MIN_SHOW_RECALL = 0.5
# A higher bar when YouTube gave us no runtime to cross-check.
MIN_TITLE_RECALL_NO_DURATION = 0.6


def sanitize_filename(name: str) -> str:
    """Clean filename for filesystem compatibility"""
    return re.sub(r'[^A-Za-z0-9 _\-.]', '_', name).strip()[:200]


def content_tokens(text: Optional[str]) -> set:
    """Lowercase word tokens, punctuation and filler words removed."""
    words = re.findall(r"[a-z0-9']+", (text or '').lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def overlap_ratio(wanted: set, found: set) -> float:
    """Share of `wanted` tokens present in `found`."""
    if not wanted:
        return 0.0
    return len(wanted & found) / len(wanted)


def compare_duration(spotify_ms: Optional[int], youtube_s: Optional[int]):
    """Compare runtimes.

    Returns (verdict, score) where verdict is 'match', 'weak', 'mismatch'
    or 'unknown'.
    """
    if not spotify_ms or not youtube_s:
        return 'unknown', 0.0

    spotify_s = spotify_ms / 1000.0
    delta = abs(youtube_s - spotify_s)

    if delta <= DURATION_TOLERANCE_ABS_S or delta / spotify_s <= DURATION_TOLERANCE_FRAC:
        return 'match', 1.0
    if delta / spotify_s >= DURATION_MISMATCH_FRAC:
        return 'mismatch', 0.0

    # Between the two cutoffs: partial credit decaying toward the mismatch line.
    return 'weak', 1.0 - (delta / spotify_s) / DURATION_MISMATCH_FRAC


def evaluate_candidate(episode: Dict, result: Dict) -> Dict:
    """Decide whether a YouTube result really is this Spotify episode."""
    title_recall = overlap_ratio(
        content_tokens(episode.get('name')),
        content_tokens(result.get('title')),
    )
    show_recall = overlap_ratio(
        content_tokens(episode.get('show')),
        content_tokens(result.get('title')) | content_tokens(result.get('uploader')),
    )
    duration_verdict, duration_score = compare_duration(
        episode.get('duration_ms'), result.get('duration')
    )

    if duration_verdict == 'mismatch':
        accepted = False
        reason = 'runtime differs from Spotify (clip or different episode)'
    elif duration_verdict == 'unknown':
        accepted = title_recall >= MIN_TITLE_RECALL_NO_DURATION
        reason = ('title strongly matches, but no runtime to verify'
                  if accepted else 'no runtime to verify and title overlap too low')
    else:
        accepted = (
            title_recall >= MIN_TITLE_RECALL
            or (title_recall >= MIN_TITLE_RECALL_WITH_SHOW and show_recall >= MIN_SHOW_RECALL)
        )
        reason = ('title and runtime agree' if accepted else 'title overlap too low')

    confidence = 0.5 * title_recall + 0.2 * min(show_recall, 1.0) + 0.3 * duration_score

    return {
        'accepted': accepted,
        'reason': reason,
        'confidence': round(confidence, 3),
        'title_recall': round(title_recall, 3),
        'show_recall': round(show_recall, 3),
        'duration_verdict': duration_verdict,
    }


def pick_best_match(episode: Dict, results: List[Dict]):
    """Return (best_result, evaluation) or (None, best_rejected_evaluation).

    Every candidate is scored; we no longer stop at the first plausible one,
    and we never fall back to "just take result #1".
    """
    scored = [(result, evaluate_candidate(episode, result)) for result in results]
    scored.sort(key=lambda pair: pair[1]['confidence'], reverse=True)

    for result, evaluation in scored:
        if evaluation['accepted']:
            return result, evaluation

    return None, (scored[0][1] if scored else None)

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
                            # Flat search results expose the channel under
                            # either key depending on yt-dlp version.
                            'uploader': (entry.get('uploader')
                                         or entry.get('channel')
                                         or 'Unknown')
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

def process_saved_podcasts(auto_confirm: bool = False, max_episodes: Optional[int] = None,
                           allow_unverified: bool = False):
    """Process episodes from saved_podcasts.json"""

    # Prefer the canonical export location, but keep honouring a copy in the
    # working directory (collect_transcripts.py stages one there).
    for candidate in (Path("saved_podcasts.json"), SAVED_PODCASTS_PATH):
        if candidate.exists():
            with open(candidate, "r") as f:
                episodes = json.load(f)
            break
    else:
        print(f"❌ saved_podcasts.json not found (looked in ./ and {SAVED_PODCASTS_PATH})")
        return

    print(f"📱 Processing {len(episodes)} saved episodes...")

    if max_episodes:
        episodes = episodes[:max_episodes]
        print(f"🔢 Limited to first {max_episodes} episodes")

    success_count = 0
    unverified_count = 0

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
        for j, result in enumerate(search_results):
            print(f"     {j+1}. {result['title'][:60]}...")
            print(f"        Channel: {result['uploader']}")

        best_match, evaluation = pick_best_match(episode, search_results)

        if best_match:
            print(f"  ✅ Verified match ({evaluation['reason']}, "
                  f"confidence {evaluation['confidence']}): {best_match['title'][:60]}")
        else:
            detail = evaluation['reason'] if evaluation else 'no candidates'
            print(f"  ⚠️  No verifiable match — {detail}")

            if not allow_unverified:
                # Skipping is deliberate: a wrong transcript silently corrupts
                # answers for this episode, which is worse than omitting it.
                print(f"  ⏭️  Skipped (use --allow-unverified to accept best guess)")
                unverified_count += 1
                continue

            best_match = search_results[0]
            print(f"  ⚠️  Falling back to best guess: {best_match['title'][:60]}")

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
            match_note = (
                f"{evaluation['reason']} (confidence {evaluation['confidence']}, "
                f"title {evaluation['title_recall']}, runtime {evaluation['duration_verdict']})"
                if evaluation else "unverified best guess"
            )
            metadata = f"""# Podcast Transcript
# Show: {episode['show']}
# Episode: {episode['name']}
# YouTube URL: {best_match['url']}
# YouTube Title: {best_match['title']}
# Match: {match_note}
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
    if unverified_count:
        print(f"⚠️  Skipped {unverified_count} episode(s) with no verifiable YouTube match")
        print(f"   Re-run with --allow-unverified to accept best guesses instead")
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
    parser.add_argument("--allow-unverified", action="store_true",
                        help="Accept the top YouTube result even when the runtime and "
                             "title cannot confirm it is the same episode (may produce "
                             "transcripts for the wrong episode)")

    args = parser.parse_args()
    
    print("📺 YouTube Podcast Transcript Downloader")
    print("=" * 50)
    
    if args.auto_search:
        process_saved_podcasts(auto_confirm=args.auto_confirm,
                               max_episodes=args.max_episodes,
                               allow_unverified=args.allow_unverified)
    
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