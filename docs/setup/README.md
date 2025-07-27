# Podcast RAG Chatbot 🎧🤖

An intelligent podcast search and chat system that connects to your Spotify account, downloads transcripts, creates semantic embeddings, and provides a beautiful web interface for searching and chatting with your podcast content using AI.

## 🎯 What It Does

This project transforms your saved podcast episodes into an intelligent, searchable knowledge base:

1. **🎵 Spotify Integration** - Automatically fetches your saved/liked podcast episodes
2. **📺 YouTube Transcript Extraction** - Downloads high-quality transcripts from YouTube using smart matching
3. **🧠 Advanced Semantic Search** - Creates vector embeddings for title, intro, content, and outro sections
4. **🤖 RAG-Powered Chat** - Interactive conversations about podcast content using LangChain + Ollama
5. **🌐 Modern Web Interface** - React frontend with real-time search and chat capabilities

## 🏗️ Architecture Overview

### **Three-Tier System Architecture**

```
┌─────────────────┐    ┌───────────────────┐    ┌──────────────────┐
│   React Frontend│    │  Flask Backend    │    │ Data Processing  │
│                 │◄──►│                   │◄──►│                  │
│ • Search UI     │    │ • REST API        │    │ • Transcript DL  │
│ • Chat Interface│    │ • Semantic Search │    │ • Embedding Gen  │
│ • Real-time UX  │    │ • LLM Integration │    │ • SQLite Storage │
└─────────────────┘    └───────────────────┘    └──────────────────┘
```

### **Data Flow Pipeline**

```
Spotify API → saved_podcasts.json → YouTube Search → Transcript Download
     ↓
SQLite Database ← Embeddings Generation ← Text Chunking ← Transcript Processing
     ↓
Two-Tier Search System → LLM Context → Generated Responses → Web UI
```

## 🧠 Technical Architecture

### **1. Data Collection Layer**

**Spotify Integration** (`spotify-*.py`)

- Uses Spotify Web API to fetch saved episodes
- Extracts metadata: episode name, show, duration, description
- Stores results in `saved_podcasts.json`

**YouTube Transcript Downloader** (`download_youtube_transcripts.py`)

- Smart matching algorithm finds correct YouTube videos for episodes
- Downloads auto-generated captions (90-95% accuracy for popular podcasts)
- Supports batch processing with auto-confirmation
- Handles rate limiting and error recovery

### **2. Semantic Processing Engine**

**Two-Tiered Search System** (`podcast_semantic_search_complete.py`)

- **Title Embeddings**: Semantic vectors for episode titles
- **Section Embeddings**: Intro (first 1000 chars), outro (last 1000 chars)
- **Content Chunks**: 1000-character overlapping chunks with 200-char overlap
- **Weighted Scoring**: Title (60%), Intro (20%), Chunks (15%), Outro (5%)

**Embedding Generation**

- Uses Ollama's `nomic-embed-text:latest` model
- Vector dimensions: 768 (configurable)
- Stored as JSON arrays in SQLite database
- Supports cosine similarity search

### **3. Backend API Layer**

**Flask REST API** (`controller.py`)

- **Thread-Safe Architecture**: Per-request SQLite connections
- **Real-time Search**: `/api/search` endpoint with semantic matching
- **Chat Interface**: `/api/chat` with conversation context
- **Health Monitoring**: `/api/health` and `/api/stats` endpoints
- **CORS Enabled**: Full frontend integration support

**Endpoints:**

- `POST /api/search` - Semantic search across all podcasts
- `POST /api/chat` - RAG-powered conversation with selected podcast
- `GET /api/stats` - Database and system statistics
- `GET /api/health` - Service health check

### **4. Frontend Application**

**React Web Interface** (`frontend/`)

- **Modern UI**: Dark theme with Tailwind CSS
- **Real-time Search**: Instant results with confidence scores
- **Interactive Chat**: Conversation interface with selected podcasts
- **Responsive Design**: Works on desktop and mobile
- **Loading States**: Smooth UX with loading indicators

**Key Features:**

- Search across all podcast content
- Confidence scoring for search results
- Session-based chat conversations
- Error handling and connection status
- Statistics dashboard

## 📁 Current Project Structure

```
podcast-q&a/
├── 🔧 Core Backend
│   ├── controller.py                      # Flask API server (430 lines)
│   ├── podcast_semantic_search_complete.py # Two-tier search engine (556 lines)
│   ├── podcast_rag.py                     # CLI chatbot interface (270 lines)
│   └── controller_tests.py                # API endpoint tests (293 lines)
│
├── 🌐 Frontend Application
│   ├── frontend/
│   │   ├── src/
│   │   │   ├── App.js                     # Main React component (371 lines)
│   │   │   ├── index.js                   # React entry point
│   │   │   └── index.css                  # Tailwind CSS styles
│   │   ├── public/index.html              # HTML template
│   │   ├── package.json                   # Dependencies & scripts
│   │   └── tailwind.config.js             # Tailwind configuration
│
├── 📡 Data Collection
│   ├── spotify-fetcher-podcasts.py       # Spotify API integration (80 lines)
│   ├── download_youtube_transcripts.py   # YouTube transcript downloader (323 lines)
│   ├── download_podcast_transcripts.py   # Multi-method transcript downloader (325 lines)
│   ├── download_sed_transcripts.py       # Software Engineering Daily RSS (93 lines)
│   └── check_podcast_transcripts.py      # Transcript availability checker (137 lines)
│
├── 💾 Data Storage
│   ├── podcast_index_v2.db              # Main SQLite database (21MB)
│   ├── podcast_index.db                 # Legacy database (34MB)
│   ├── saved_podcasts.json              # Spotify episode metadata (16KB)
│   ├── transcripts/                      # Downloaded transcript files
│   └── embeddings_export.csv            # Embedding export (387KB)
│
├── 🔬 Analysis & Utilities
│   ├── explore_embeddings.py            # Embedding analysis tools (189 lines)
│   ├── scripts/                         # Utility scripts
│   └── tests/                           # Test suites
│
├── 📚 Documentation
│   ├── README.md                        # This file
│   ├── FRONTEND_SETUP.md               # Frontend setup guide
│   ├── TRANSCRIPT_GUIDE.md             # Transcript acquisition guide
│   └── docs/                           # Additional documentation
│
└── ⚙️ Configuration
    ├── requirements.txt                 # Python dependencies
    ├── pyproject.toml                  # Project configuration
    ├── config.env                      # Environment variables
    └── Makefile                        # Build automation
```

## 🚀 Setup & Installation

### **Prerequisites**

- Python 3.8+
- Node.js 16+
- Ollama (for LLM inference)
- Spotify Developer Account

### **1. Clone & Install Dependencies**

```bash
# Clone repository
git clone <your-repo-url>
cd podcast-q&a

# Install Python dependencies
pip install -r requirements.txt

# Install frontend dependencies
cd frontend
npm install
cd ..
```

### **2. Configure Services**

**Spotify API Setup:**

1. Create app at [developer.spotify.com](https://developer.spotify.com/dashboard)
2. Set redirect URI: `http://127.0.0.1:8888/callback/`
3. Update credentials in `spotify-fetcher-podcasts.py`

**Ollama Setup:**

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama server
ollama serve

# Download required models
ollama pull llama3
ollama pull nomic-embed-text
```

### **3. Data Collection**

```bash
# Step 1: Get your saved podcasts from Spotify
python3 spotify-fetcher-podcasts.py

# Step 2: Download transcripts (choose one)
# Option A: Download all transcripts (recommended)
python3 download_youtube_transcripts.py --auto-search --auto-confirm

# Option B: Test with limited episodes
python3 download_youtube_transcripts.py --auto-search --max-episodes 10

# Step 3: Index transcripts and generate embeddings
python3 podcast_semantic_search_complete.py
```

### **4. Run the Application**

```bash
# Terminal 1: Start backend API
python3 controller.py
# ✓ API runs on http://localhost:3000

# Terminal 2: Start frontend
cd frontend
npm start
# ✓ Frontend runs on http://localhost:8080
```

## 🎮 Usage Guide

### **Web Interface**

1. **Search Podcasts**: Enter queries like "AI programming", "startup advice", or specific guest names
2. **Review Results**: See confidence scores and content previews
3. **Start Chatting**: Click on any result to begin an AI conversation
4. **Ask Questions**: Query the podcast content in natural language

### **API Endpoints**

**Search Podcasts:**

```bash
curl -X POST http://localhost:3000/api/search \
  -H "Content-Type: application/json" \
  -d '{"query": "artificial intelligence", "top_k": 5}'
```

**Chat with Podcast:**

```bash
curl -X POST http://localhost:3000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"podcast_id": "123", "message": "What are the main points?", "session_id": "session_1"}'
```

### **Command Line Interface**

```bash
# Interactive CLI chatbot
python3 podcast_rag.py

# Available commands:
# list              - Show available transcripts
# load filename.txt - Load specific transcript
# clear            - Clear current context
# <your question>  - Ask about loaded content
```

## 🔍 Technical Deep Dive

### **Database Schema**

**Podcasts Table:**

```sql
CREATE TABLE podcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    filename TEXT UNIQUE NOT NULL,           -- Source file identifier
    title TEXT NOT NULL,                     -- Extracted episode title
    content TEXT NOT NULL,                   -- Full transcript content
    char_count INTEGER,                      -- Content length
    title_embedding TEXT,                    -- JSON array of title vectors
    intro_embedding TEXT,                    -- JSON array of intro vectors
    outro_embedding TEXT,                    -- JSON array of outro vectors
    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Chunks Table:**

```sql
CREATE TABLE chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    podcast_id INTEGER NOT NULL,             -- Foreign key to podcasts
    chunk_index INTEGER NOT NULL,            -- Order within episode
    content TEXT NOT NULL,                   -- Chunk text content
    char_start INTEGER,                      -- Start position in transcript
    char_end INTEGER,                        -- End position in transcript
    embedding TEXT,                          -- JSON array of content vectors
    FOREIGN KEY (podcast_id) REFERENCES podcasts (id)
);
```

### **Two-Tier Search Algorithm**

```python
# Scoring weights
TITLE_WEIGHT = 0.6      # Highest priority for title matches
INTRO_WEIGHT = 0.2      # Episode introduction/summary
CHUNKS_WEIGHT = 0.15    # Content body chunks
OUTRO_WEIGHT = 0.05     # Episode conclusion

# Final score calculation
final_score = (
    title_similarity * TITLE_WEIGHT +
    intro_similarity * INTRO_WEIGHT +
    max_chunk_similarity * CHUNKS_WEIGHT +
    outro_similarity * OUTRO_WEIGHT
)
```

### **Embedding Model Details**

- **Model**: `nomic-embed-text:latest` via Ollama
- **Dimensions**: 768-dimensional vectors
- **Context Window**: Up to 8192 tokens
- **Storage**: JSON arrays in SQLite TEXT fields
- **Similarity**: Cosine similarity for relevance matching

### **Chat Context Management**

- **Session-based**: Each conversation gets unique session ID
- **Context Retrieval**: Top-K relevant chunks based on query
- **LLM Integration**: Llama3 via Ollama with temperature 0.7
- **Streaming**: Real-time response generation (if supported)

## 📊 Performance Metrics

### **Transcript Success Rates**

- **Popular Podcasts**: 90-95% success (All-In, Lex Fridman, etc.)
- **Technical Shows**: 85-90% success (Software Engineering Daily, etc.)
- **Niche Content**: 70-80% success rate
- **Overall Average**: ~85% transcript acquisition success

### **Search Performance**

- **Database Size**: ~50MB for 100 episodes
- **Search Latency**: <200ms for semantic search
- **Embedding Generation**: ~2-3 seconds per episode
- **Memory Usage**: ~500MB during processing

### **Supported Podcast Shows**

**High Success Rate:**

- All-In with Chamath, Jason, Sacks & Friedberg
- Lex Fridman Podcast
- Latent Space: The AI Engineer Podcast
- Y Combinator Startup Podcast
- Software Engineering Daily
- The Tim Ferriss Show
- Joe Rogan Experience

## 🔮 Future Enhancements

### **Planned Features**

- [ ] **Multi-user Support**: User authentication and data isolation
- [ ] **Advanced Search**: Date filters, show filters, topic clustering
- [ ] **Audio Transcription**: Whisper integration for non-YouTube content
- [ ] **Export Features**: Conversation history, insights export
- [ ] **Mobile App**: React Native companion app
- [ ] **Plugin System**: Extensible architecture for custom integrations

### **Technical Improvements**

- [ ] **Vector Database**: Migration to Pinecone/Weaviate for scale
- [ ] **Caching Layer**: Redis for improved response times
- [ ] **Async Processing**: Background job queue for transcript processing
- [ ] **Monitoring**: Prometheus metrics and Grafana dashboards
- [ ] **Cloud Deployment**: Docker containers and Kubernetes manifests

## 🛠️ Development & Contributing

### **Development Setup**

```bash
# Install development dependencies
pip install -e .
pip install pytest black flake8

# Run tests
python -m pytest tests/

# Code formatting
black *.py
flake8 *.py
```

### **Project Standards**

- **Code Style**: Black formatter, PEP 8 compliance
- **Testing**: Pytest with coverage reporting
- **Documentation**: Inline docstrings, API documentation
- **Git Workflow**: Feature branches, pull request reviews

## 📄 License

MIT License - Feel free to use, modify, and distribute for your own podcast RAG adventures!

---

## 🎯 Quick Start Summary

```bash
# 1. Setup
pip install -r requirements.txt
cd frontend && npm install && cd ..

# 2. Start Ollama
ollama serve
ollama pull llama3 nomic-embed-text

# 3. Get Data
python3 spotify-fetcher-podcasts.py
python3 download_youtube_transcripts.py --auto-search --auto-confirm

# 4. Run App
python3 controller.py &           # Backend on :3000
cd frontend && npm start          # Frontend on :8080
```

**🌐 Open http://localhost:8080 and start chatting with your podcasts!** 🎧✨
