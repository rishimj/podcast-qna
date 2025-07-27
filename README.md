# Podcast Q&A System

An AI-powered podcast search and Q&A system with semantic search and conversational interface.

## Architecture

- **Backend**: Flask API with semantic search and RAG capabilities
- **Frontend**: React application with modern UI
- **AI**: Ollama for embeddings and chat completion
- **Database**: SQLite for podcast data and embeddings


## Quick Start

### 1. Setup Dependencies
```bash
# Backend dependencies
cd backend
pip install -r requirements.txt

# Frontend dependencies  
cd frontend
npm install

# Data collection dependencies
cd backend/data_collection
python setup_data_collection.py
```

### 2. Configure API Keys
```bash
# Copy template and add your Spotify credentials
cp config/env/config.env.example config/env/config.env
# Edit config.env with your Spotify Client ID & Secret
```

### 3. Collect Podcast Data
```bash
# Fetch your Spotify episodes and download transcripts
python collect_podcasts.py --limit 10
```

### 4. Start Services

**Option A: Quick Start**
```bash
python run_server.py    # Backend on port 3000
cd frontend && npm start # Frontend on port 8080
```

**Option B: Manual Start**
```bash
# Terminal 1: Backend
cd backend/api
python controller.py

# Terminal 2: Frontend  
cd frontend
npm start
```

### 5. Access Application
- Frontend: http://localhost:8080
- Backend API: http://localhost:3000/api/health

## Features

- **Semantic Search**: Two-tier search with title, intro, and content matching
- **Chat Interface**: Ask questions about specific podcast episodes
- **Data Collection**: Automated transcript download from multiple sources
- **Modern UI**: Clean, responsive React interface
- **RESTful API**: Well-documented endpoints for search and chat

## API Endpoints

- `GET /api/health` - Service health check
- `POST /api/search` - Semantic search for podcasts
- `POST /api/chat` - Chat with selected podcast
- `GET /api/stats` - System statistics
- `GET /api/podcasts` - List all podcasts

## Dependencies

### Backend
- Flask 3.1+ for web framework
- Ollama for AI embeddings and chat
- SQLite for data storage
- LangChain for RAG pipeline

### Frontend  
- React 18+ for UI framework
- Tailwind CSS for styling
- Axios for API calls
- Lucide React for icons
