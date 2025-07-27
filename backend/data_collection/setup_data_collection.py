#!/usr/bin/env python3
"""
Setup script for the data collection pipeline
Installs dependencies and prepares the environment
"""

import subprocess
import sys
import os
from pathlib import Path

def install_package(package):
    """Install a Python package using pip"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        return False

def main():
    print("🚀 Setting up Podcast Data Collection Pipeline")
    print("=" * 50)
    
    # Required packages
    packages = [
        "spotipy",
        "youtube-transcript-api", 
        "yt-dlp",
        "python-dotenv"
    ]
    
    print("📦 Installing required packages...")
    for package in packages:
        print(f"   Installing {package}...")
        if install_package(package):
            print(f"   ✅ {package} installed successfully")
        else:
            print(f"   ❌ Failed to install {package}")
            return 1
    
    # Create data directories (relative to project root)
    print("\n📁 Creating data directories...")
    project_root = Path(__file__).parent.parent.parent
    data_dirs = [
        "data/transcripts",
        "data/databases", 
        "data/exports",
        "data/cache"
    ]
    
    for dir_path in data_dirs:
        full_path = project_root / dir_path
        full_path.mkdir(parents=True, exist_ok=True)
        print(f"   ✅ Created {full_path}")
    
    # Check config file
    config_path = project_root / "config/env/config.env"
    config_example = project_root / "config/env/config.env.example"
    
    print("\n⚙️ Checking configuration...")
    if not config_path.exists():
        if config_example.exists():
            print(f"   📋 Please copy {config_example} to {config_path}")
            print(f"   📋 Then add your Spotify API credentials")
        else:
            print(f"   ⚠️ Configuration template not found")
    else:
        print(f"   ✅ Configuration file exists: {config_path}")
    
    print("\n" + "=" * 50)
    print("✅ Setup completed!")
    print("\n📋 Next steps:")
    print("1. Copy config/env/config.env.example to config/env/config.env")
    print("2. Add your Spotify API credentials to config.env")
    print("3. Run: python collect_transcripts.py")
    print("\n💡 For Spotify API credentials:")
    print("   Visit: https://developer.spotify.com/dashboard")
    print("   Create an app and get Client ID & Secret")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())