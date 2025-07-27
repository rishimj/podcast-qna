# Data Collection Pipeline

A unified script to fetch your Spotify saved episodes and download transcripts from YouTube.

## 🚀 Quick Start

### 1. Setup (First Time Only)
```bash
# Install dependencies and create directories
python setup_data_collection.py

# Configure your Spotify API credentials
cp config/env/config.env.example config/env/config.env
# Edit config.env with your real Spotify Client ID & Secret
```

### 2. Run Data Collection
```bash
# From project root (recommended)
python collect_podcasts.py

# From data collection directory  
cd backend/data_collection
python collect_transcripts.py

# Interactive mode (with prompts)
python collect_podcasts.py --interactive

# Limit to 10 episodes
python collect_podcasts.py --limit 10
```

## 📋 What It Does

The pipeline consists of two main steps:

### Step 1: Spotify Episode Fetcher
- Connects to your Spotify account using OAuth
- Fetches your saved (♥) podcast episodes
- Saves episode metadata to `data/exports/saved_podcasts.json`
- Uses secure environment variables for API credentials

### Step 2: YouTube Transcript Downloader  
- Reads the saved episodes from Step 1
- Searches YouTube for matching podcast episodes
- Downloads transcripts using YouTube's auto-captions
- Saves transcripts to `data/transcripts/`
- Handles filename sanitization and error cases

## 🔧 Configuration

### Spotify API Setup
1. Visit [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Set redirect URI: `http://127.0.0.1:8888/callback/`
4. Copy Client ID and Secret to `config/env/config.env`

### Environment Variables
Required in `config/env/config.env`:
```bash
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback/
```

## 📁 Data Structure

After running the pipeline:
```
data/
├── exports/
│   └── saved_podcasts.json      # Spotify episode metadata
├── transcripts/
│   ├── 2025-01-15_Show Name_Episode Title.txt
│   └── 2025-01-16_Another Show_Episode.txt
└── databases/
    └── podcast_index_v2.db       # Embeddings database
```

## 🎛️ Usage Options

### Basic Usage
```bash
python collect_podcasts.py
```
Auto-download mode (default) - downloads transcripts without prompts.

### Advanced Options
```bash
# Interactive mode with prompts for each download
python collect_podcasts.py --interactive

# Limit Spotify episodes fetched
python collect_podcasts.py --limit 25

# Only update Spotify episodes, skip transcripts
python collect_podcasts.py --update-only

# Only download transcripts, skip Spotify fetch
python collect_podcasts.py --transcripts-only

# Limit transcript downloads
python collect_podcasts.py --max-transcripts 10

# Skip dependency checks (faster)
python collect_podcasts.py --skip-checks
```

### Update Workflows
```bash
# Daily: Get new episodes only
python collect_podcasts.py --update-only

# Weekly: Full sync with limit
python collect_podcasts.py --limit 20

# Batch: Large collection
python collect_podcasts.py --limit 100
```

## 📊 Pipeline Output

The script provides detailed logging and progress updates:

```
🚀 Starting Podcast Data Collection Pipeline
📅 Started at: 2025-01-27 15:30:45

==============================================================
STEP 1: Fetching Spotify Episodes
==============================================================
📄 Loading environment from config/env/config.env
✅ All dependencies are installed
✅ Environment variables are configured
🎵 Fetching saved episodes from Spotify...
✓ Connected as Your Name
✓ Retrieved 25 episodes
✅ Saved 25 episodes to data/exports/saved_podcasts.json

==============================================================
STEP 2: Downloading YouTube Transcripts
==============================================================
📺 Downloading transcripts from YouTube...
🔍 Searching YouTube for: Lex Fridman DHH Ruby on Rails podcast
📥 Downloading transcript for: DHH: Ruby on Rails...
✅ YouTube transcript download completed

==============================================================
📊 COLLECTION SUMMARY
==============================================================
🎵 Spotify Episodes: 25
📺 Downloaded Transcripts: 15
💾 Total Size: 2.3 MB
📅 Latest Download: 2025-01-27 15:45:12

📁 Data Locations:
   Episodes: data/exports/saved_podcasts.json
   Transcripts: data/transcripts/
   Database: data/databases/podcast_index_v2.db

🚀 Next Steps:
   1. Run: python run_server.py
   2. Open: http://localhost:3000/api/health
   3. Start frontend: cd frontend && npm start
==============================================================
```

## 🔍 Logging and Debugging

### Log Files
- Console output: Real-time progress
- File log: `data_collection.log` 

### Common Issues

**Missing Dependencies:**
```bash
python setup_data_collection.py
```

**Spotify Auth Issues:**
- Check your Client ID/Secret in config.env
- Verify redirect URI: `http://127.0.0.1:8888/callback/`
- Browser should open for OAuth flow

**YouTube Download Failures:**
- Some podcasts may not have YouTube versions
- Auto-captions might not be available
- Network issues can cause timeouts

**Permission Errors:**
- Ensure write access to `data/` directory
- Check file permissions on existing files

### Debug Mode
For detailed debugging, run with Python logging:
```bash
PYTHONPATH=. python -m logging collect_transcripts.py --auto
```

## 🔧 Advanced Configuration

### Custom Output Paths
Edit the scripts to change default paths:
- Spotify output: `data/exports/saved_podcasts.json`
- Transcripts: `data/transcripts/`

### Rate Limiting
Spotify API has built-in rate limiting. For large collections:
- Use `--limit` to fetch in batches
- The script respects Spotify's rate limits automatically

### YouTube Search Optimization
The script searches YouTube using:
- Show name + episode title + "podcast"
- Falls back to simplified searches
- Handles various podcast naming conventions

## 🚦 Integration with Main App

After collecting transcripts:

1. **Index the data:**
   ```bash
   cd backend/search
   python podcast_semantic_search_complete.py
   ```

2. **Start the API server:**
   ```bash
   python run_server.py
   ```

3. **Start the frontend:**
   ```bash
   cd frontend && npm start
   ```

4. **Access the app:**
   - Frontend: http://localhost:8080
   - API: http://localhost:3000

## 📅 Automation

### Daily Collection
```bash
# Add to crontab for daily updates
0 9 * * * cd /path/to/podcast-q&a && python collect_transcripts.py --update-only --auto >> daily_collection.log 2>&1
```

### Weekly Full Sync
```bash
# Weekly full collection
0 9 * * 0 cd /path/to/podcast-q&a && python collect_transcripts.py --limit 50 --auto >> weekly_collection.log 2>&1
```

---

**Ready to collect your podcast data!** 🎧✨