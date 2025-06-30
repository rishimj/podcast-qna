#!/usr/bin/env python3
"""
download_sed_transcripts.py

Fetch the Software Engineering Daily RSS feed, grab the last 5 episodes’
transcript links (the .txt URLs inside <content:encoded>), and download them.
"""

import os
import re
import requests
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime

# --- Configuration ---
FEED_URL        = "https://softwareengineeringdaily.com/feed/"   # note trailing slash
EPISODES_TO_GET = 5
OUTPUT_DIR      = "transcripts"

# Spoof a real browser
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/114.0.0.0 Safari/537.36"
    )
}

# create output dir if needed
os.makedirs(OUTPUT_DIR, exist_ok=True)

def sanitize_filename(name: str) -> str:
    """Strip out characters that don’t play nice in file names."""
    return re.sub(r'[^A-Za-z0-9 _\-.]', '_', name).strip()

def main():
    # 1) download raw RSS XML with headers
    resp = requests.get(FEED_URL, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    xml = resp.text

    # 2) parse with XML parser
    soup = BeautifulSoup(xml, "xml")
    items = soup.find_all("item")[:EPISODES_TO_GET]

    for item in items:
        title = item.title.text or "untitled"
        pubdate = item.pubDate.text or ""
        # normalize to YYYY-MM-DD
        try:
            dt = parsedate_to_datetime(pubdate)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = "unknown_date"

        # 3) pull the HTML inside <content:encoded>
        content_encoded = item.find("content:encoded")
        if not content_encoded or not content_encoded.string:
            print(f"• [{title}] no <content:encoded>, skipping")
            continue

        html = content_encoded.string
        html_soup = BeautifulSoup(html, "html.parser")

        # find the first <a href="… .txt">
        a = html_soup.find("a", href=re.compile(r"\.txt$"))
        if not a:
            print(f"• [{title}] no .txt link found, skipping")
            continue

        transcript_url = a["href"]
        ext = transcript_url.rsplit(".", 1)[-1]
        fname = f"{date_str}_{sanitize_filename(title)}.{ext}"
        out_path = os.path.join(OUTPUT_DIR, fname)

        # 4) download transcript with same headers
        try:
            print(f"Downloading transcript for “{title}” …")
            tx = requests.get(transcript_url, headers=HEADERS, timeout=10)
            tx.raise_for_status()
        except Exception as e:
            print(f"  ERROR fetching {transcript_url}: {e}")
            continue

        with open(out_path, "wb") as f:
            f.write(tx.content)
        print(f"  → saved to {out_path}")

    print("\n✅ Done!")

if __name__ == "__main__":
    main()
