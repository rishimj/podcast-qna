# Podcast RAG Chatbot 🎧🤖

A RAG-based chatbot that connects to your Spotify account, downloads transcripts from your saved podcast episodes via YouTube, and lets you query and chat about the content using AI.

## 🚀 What It Does

1. **Connects to Spotify** - Fetches your saved/liked podcast episodes
2. **Downloads Transcripts** - Automatically finds and downloads transcripts from YouTube videos
3. **Creates Embeddings** - Uses vector embeddings for semantic search and retrieval
4. **RAG Chatbot** - Chat with your podcasts using LangChain and various LLMs (Ollama, local models)

## ✨ Features

- 🎵 **Spotify Integration** - Automatically sync your saved podcast episodes
- 📺 **YouTube Transcript Extraction** - Smart matching and transcript downloading from YouTube
- 🔍 **Semantic Search** - Vector embeddings for finding relevant content chunks
- 🤖 **Multiple LLM Options** - Support for Ollama (Llama3), local GGUF models, and more
- 💬 **Interactive Chat** - Natural language queries about your podcast content
- 📊 **High Success Rate** - ~90% success rate for popular podcasts

## 🛠️ Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Spotify Setup

1. Create a Spotify App at [developer.spotify.com](https://developer.spotify.com/dashboard)
2. Set redirect URI to: `http://127.0.0.1:8888/callback/`
3. Update credentials in `spotify-fetcher-podcasts.py`:

```python
CLIENT_ID = 'your_spotify_client_id'
CLIENT_SECRET = 'your_spotify_client_secret'
```

### 3. Get Your Saved Podcasts

```bash
python3 spotify-fetcher-podcasts.py
```

This creates `saved_podcasts.json` with all your saved podcast episodes.

### 4. Download Transcripts

**Option A: YouTube Auto-Download (Recommended)**

```bash
# Download transcripts for ALL your saved episodes
python3 download_youtube_transcripts.py --auto-search --auto-confirm

# Or test with first 10 episodes
python3 download_youtube_transcripts.py --auto-search --max-episodes 10
```

**Option B: RSS Feeds (Limited shows)**

```bash
# For Software Engineering Daily
python3 download_podcast_transcripts.py --method rss --shows "Software Engineering Daily"
```

### 5. Install and Run Ollama

```bash
# Install Ollama (macOS)
brew install ollama

# Start Ollama server
ollama serve

# Download Llama3 model (in another terminal)
ollama pull llama3
```

## 🎯 Usage

### 🌐 Web UI (Recommended)

```bash
# Terminal 1: Start the backend API
python3 controller.py

# Terminal 2: Start the frontend
cd frontend
npm run dev
```

Then open: **http://localhost:5173**

**Features:**

- 🔍 Semantic search across all podcasts
- 💬 Interactive chat with selected podcasts
- 🎨 Beautiful dark theme interface
- ⚡ Real-time responses with loading indicators

### 💻 Command Line Interface

```bash
python3 podcast_rag.py
```

Commands:

- `list` - Show available transcripts
- `load filename.txt` - Load a specific transcript
- `clear` - Clear current transcript
- Ask questions about the loaded podcast!

### Advanced RAG Systems

**Full RAG with Local Models:**

```bash
python3 rag_sed.py --transcript-dir transcripts
```

**Fast RAG (Speed Optimized):**

```bash
python3 rag_sed_fast.py --transcript-dir transcripts
```

**Ultra-Fast RAG:**

```bash
python3 rag_sed_ultrafast.py --transcript-dir transcripts
```

## 📁 Project Structure

```
podcast-q&a/
├── spotify-fetcher-podcasts.py    # Get saved podcasts from Spotify
├── saved_podcasts.json           # Your saved episodes (auto-generated)
├── download_youtube_transcripts.py # Download transcripts from YouTube
├── download_podcast_transcripts.py # Multi-method transcript downloader
├── transcripts/                   # Downloaded transcript files
├── podcast_rag.py                # Interactive chatbot (Ollama)
├── rag_sed.py                    # Full RAG system (local models)
├── rag_sed_fast.py               # Speed-optimized RAG
└── rag_sed_ultrafast.py          # Ultra-fast RAG
```

## 🔧 How It Works

### 1. Spotify Integration

- Uses Spotify Web API to fetch your saved/liked episodes
- Extracts metadata: episode name, show, duration, save date

### 2. YouTube Transcript Extraction

- Searches YouTube for each podcast episode
- Smart matching algorithm finds correct videos
- Downloads auto-generated captions (90-95% accuracy)
- Works with most popular podcasts (All-In, Lex Fridman, etc.)

### 3. RAG Pipeline

- **Text Chunking**: Splits transcripts into semantic chunks
- **Embeddings**: Creates vector embeddings using Sentence Transformers
- **Vector Store**: Uses FAISS for fast similarity search
- **Retrieval**: Finds most relevant chunks for user queries
- **Generation**: LLM generates answers based on retrieved context

### 4. LLM Options

- **Ollama**: Llama3, Llama3.2 (recommended for local use)
- **Local GGUF**: Mistral, Dolly, GPT4All models
- **Streaming**: Real-time response streaming

## 📊 Supported Podcasts

**High Success Rate (YouTube transcripts):**

- All-In with Chamath, Jason, Sacks & Friedberg
- Lex Fridman Podcast
- Latent Space: The AI Engineer Podcast
- Y Combinator Startup Podcast
- Dwarkesh Podcast
- Around the Prompt
- And many more!

**RSS Transcripts:**

- Software Engineering Daily (human transcripts)

## 🎮 Example Workflows

**Quick Start:**

```bash
# 1. Get your podcasts
python3 spotify-fetcher-podcasts.py

# 2. Download all transcripts
python3 download_youtube_transcripts.py --auto-search --auto-confirm

# 3. Start Ollama
ollama serve

# 4. Chat with your podcasts
python3 podcast_rag.py
```

**Advanced Usage:**

```bash
# Build vector index for all transcripts
python3 rag_sed.py --transcript-dir transcripts --k 4

# Query specific topics across all podcasts
> What did guests say about AI in programming?
> Find discussions about startup fundraising
> What are the different views on remote work?
```

## 🔍 Technical Details

- **Embeddings**: Sentence Transformers (all-MiniLM-L6-v2)
- **Vector DB**: FAISS with efficient similarity search
- **Text Splitting**: Recursive character splitter (1000 chars, 200 overlap)
- **LLM Framework**: LangChain with multiple model backends
- **Transcript Quality**: YouTube auto-captions ~90-95% accuracy

## 🚧 Future Enhancements

- [ ] Web interface (FastAPI + React)
- [ ] Multi-user support with authentication
- [ ] Audio transcription for non-YouTube podcasts
- [ ] Advanced search filters (date, show, topic)
- [ ] Podcast recommendations based on content
- [ ] Export conversations and insights

## 🤝 Contributing

This is a personal project, but feel free to:

- Report issues
- Suggest improvements
- Share your own podcast RAG setups!

## 📄 License

MIT License - feel free to use and modify for your own podcast RAG adventures!

---

**Start chatting with your podcasts in minutes!** 🎧✨
