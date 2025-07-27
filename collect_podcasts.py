#!/usr/bin/env python3
"""
Podcast Collection Launcher
Simple wrapper to run the data collection pipeline from the project root
"""

import subprocess
import sys
from pathlib import Path

def main():
    # Path to the actual collection script
    script_path = Path(__file__).parent / 'backend' / 'data_collection' / 'collect_transcripts.py'
    
    if not script_path.exists():
        print(f"❌ Collection script not found: {script_path}")
        return 1
    
    # Pass all arguments to the collection script
    cmd = [sys.executable, str(script_path)] + sys.argv[1:]
    
    try:
        return subprocess.call(cmd)
    except KeyboardInterrupt:
        print("\n⚠️ Collection interrupted by user")
        return 1

if __name__ == "__main__":
    sys.exit(main())