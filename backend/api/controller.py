#!/usr/bin/env python3
"""
FastAPI backend for the Podcast RAG chatbot.
Provides REST endpoints for search, chat and summaries.
"""

import logging
import os
import re
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from search.claude_llm import ClaudeLLM
from search.podcast_semantic_search_complete import PodcastTwoTierSearch
from search.summarization_service import PodcastSummarizationService
from search.email_service import EmailService
from search.corrective_rag import run_corrective_rag, init_rag_resources
from api.safeguards import (MAX_MESSAGE_CHARS, MAX_QUERY_CHARS, MAX_SESSION_ID_CHARS,
                            MAX_TOP_K, install_fastapi, remember_session)

load_dotenv(Path(__file__).parent.parent.parent / '.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Podcast Q&A API")


def _load_config():
    """Load environment variables from config/env/config.env."""
    config_path = Path(__file__).parent.parent.parent / 'config' / 'env' / 'config.env'

    if not config_path.exists():
        logger.warning("Config file not found: %s", config_path)
        return

    with open(config_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ[key.strip()] = value.strip()

    logger.info("Configuration loaded from %s", config_path)
    smtp_user = os.getenv('SMTP_USERNAME')
    if smtp_user:
        logger.info("Email configured for: %s", smtp_user)
    else:
        logger.warning("SMTP_USERNAME not found in config")


_load_config()

# Rate limits, spend caps, body-size cap and the optional access code; see
# api/safeguards.py. Added before CORS so that CORS wraps it and the browser
# can read a 429/401 body instead of seeing a blocked cross-origin response.
guard = install_fastapi(app)

# Browser origins allowed to call the API (ALLOWED_ORIGINS, comma-separated; * = any).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in os.getenv('ALLOWED_ORIGINS', '*').split(',') if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)

llm = None
summarization_service = None
email_service = None
current_sessions = {}

def init_services():
    """Initialize LLM, summarization, and email services."""
    global llm, summarization_service, email_service

    try:
        logger.info("Initializing LLM...")
        llm = ClaudeLLM(purpose="chat")
        logger.info("LLM initialized (%s)", llm.model)

        logger.info("Initializing corrective RAG pipeline...")
        try:
            rag_search = PodcastTwoTierSearch()
            init_rag_resources(search=rag_search, llm=llm)
            logger.info("Corrective RAG pipeline initialized")
        except Exception as e:
            logger.error("Failed to initialize corrective RAG: %s", e, exc_info=True)

        logger.info("Initializing summarization service...")
        project_root = Path(__file__).parent.parent.parent
        db_path = project_root / "data" / "databases" / "podcast_index_v2.db"
        summarization_service = PodcastSummarizationService(db_path=str(db_path))
        logger.info("Summarization service initialized")

        logger.info("Initializing email service...")
        email_service = EmailService()
        logger.info("Email service initialized")

        return True
    except Exception as e:
        logger.error("Failed to initialize services: %s", e, exc_info=True)
        return False

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "databases" / "podcast_index_v2.db"


def get_podcast_title(podcast_id):
    """Title of an indexed podcast, or None if it doesn't exist.

    Read-only connection: a wrong path raises instead of creating an empty DB.
    """
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT title FROM podcasts WHERE id = ?", (podcast_id,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


def get_search_system():
    """Create a new search system instance (one per request)."""
    return PodcastTwoTierSearch()


def error(status_code: int, detail: str, **extra) -> JSONResponse:
    """An error response in this API's shape: {"error": detail, **extra}.

    Extra keys pass through as-is, including `message` (used by the 503 body).
    """
    return JSONResponse({'error': detail, **extra}, status_code=status_code)


class ServicesUnavailable(Exception):
    """The LLM, summarization or email service could not be started."""


def require_services():
    """Start services on first use; respond 503 if they can't start."""
    if llm is None or summarization_service is None or email_service is None:
        logger.info("Services not initialized, reinitializing...")
        if not init_services():
            raise ServicesUnavailable()


SERVICES = [Depends(require_services)]


# ──────────────────────────── Request bodies ────────────────────
# Fields default to empty values so each handler's own checks still produce
# their specific 400 messages; a wrong type fails validation (also a 400).

# Length caps keep a single request from burning a large token budget.

class SearchRequest(BaseModel):
    query: str = Field('', max_length=MAX_QUERY_CHARS)
    top_k: int = Field(5, ge=1, le=MAX_TOP_K)


class ChatRequest(BaseModel):
    podcast_id: int | None = None
    message: str = Field('', max_length=MAX_MESSAGE_CHARS)
    session_id: str | None = Field(None, max_length=MAX_SESSION_ID_CHARS)


class SummaryRequest(BaseModel):
    podcast_id: int | None = None
    force_regenerate: bool = False


class EmailSummaryRequest(BaseModel):
    podcast_id: int | None = None
    email: str = Field('', max_length=254)
    force_regenerate: bool = False


# ──────────────────────────── Error Handlers ────────────────────

@app.exception_handler(ServicesUnavailable)
async def services_unavailable(request: Request, exc: ServicesUnavailable):
    return error(503, 'Services not initialized',
                 message='Please ensure ANTHROPIC_API_KEY is set, Ollama is running '
                         '(embeddings), and the database exists')


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    """Report bad input as 400 {"error": ...} rather than FastAPI's 422 {"detail": [...]}."""
    errors = exc.errors()
    # A non-integer /api/podcast/<id> was an unmatched route under Flask.
    if any(tuple(e.get('loc', ()))[:1] == ('path',) for e in errors):
        return error(404, 'Endpoint not found')
    whole_body = [e for e in errors if e.get('type') == 'json_invalid'
                  or tuple(e.get('loc', ())) == ('body',)]
    if whole_body:
        return error(400, 'Request body must be a JSON object')
    first = errors[0]
    field = '.'.join(str(part) for part in tuple(first.get('loc', ()))[1:]) or 'request'
    return error(400, f"Invalid {field}: {first.get('msg')}")


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 404:
        return error(404, 'Endpoint not found')
    return error(exc.status_code, str(exc.detail))


@app.exception_handler(Exception)
async def server_error(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, exc, exc_info=True)
    return error(500, 'Internal server error')


# ──────────────────────────── Health ────────────────────────────

@app.get('/api/health')
def health_check():
    """Check if all services are running"""
    status = {
        'api': 'running',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'search_system': True,  # Always available since we create per request
            'llm': llm is not None,
            'summarization_service': summarization_service is not None,
            'email_service': email_service is not None
        }
    }

    # Test database + Pinecone connection
    try:
        search_system = get_search_system()
        stats = search_system.get_stats()
        status['database'] = {
            'connected': True,
            'podcasts': stats['podcasts'],
            'chunks': stats['chunks']
        }
        status['pinecone'] = {
            'connected': True,
            'vectors': stats.get('pinecone_vectors', 0)
        }
        search_system.close()
    except Exception as e:
        logger.error("Database stats error: %s", e)
        status['database'] = {
            'connected': False,
            'podcasts': 0,
            'chunks': 0,
            'error': str(e)
        }
        status['pinecone'] = {
            'connected': False,
            'error': str(e)
        }

    return status

# ──────────────────────────── Search ────────────────────────────

@app.post('/api/search', dependencies=SERVICES)
def search_podcasts(body: SearchRequest):
    """Search for podcasts using two-tiered semantic search"""
    try:
        query = body.query.strip()
        top_k = body.top_k

        if not query:
            return error(400, 'Query is required')

        # Perform search
        start_time = time.time()
        search_system = get_search_system()
        try:
            results = search_system.search_two_tier(query, top_k=top_k)
        finally:
            search_system.close()
        search_time = time.time() - start_time

        # Format results
        formatted_results = []
        for result in results:
            formatted_results.append({
                'podcast_id': result['podcast_id'],
                'title': result['title'],
                'filename': result['filename'],
                # Display-friendly rescaling of the reranker score; see
                # rerank_to_match_score. The raw score stays under 'scoring'.
                'confidence': round(result['match_score'], 3),
                'confidence_percent': round(result['match_score'] * 100, 1),
                'content_preview': result['content_preview'],
                'scoring': {
                    'title': round(result['title_similarity'], 3),
                    'intro': round(result['intro_similarity'], 3),
                    'content': round(result['chunks_similarity'], 3),
                    'outro': round(result['outro_similarity'], 3),
                    'rerank': round(result['final_score'], 4)
                }
            })

        return {
            'query': query,
            'results': formatted_results,
            'count': len(formatted_results),
            'search_time_ms': round(search_time * 1000, 2)
        }

    except Exception as e:
        logger.error("Search error: %s", e)
        return error(500, str(e))

# ──────────────────────────── Podcasts ──────────────────────────

@app.get('/api/podcasts', dependencies=SERVICES)
def list_podcasts():
    """Get list of all indexed podcasts"""
    try:
        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('''
                SELECT id, filename, title, char_count, indexed_at
                FROM podcasts
                ORDER BY indexed_at DESC
            ''')

            podcasts = []
            for row in cursor.fetchall():
                podcasts.append({
                    'id': row[0],
                    'filename': row[1],
                    'title': row[2],
                    'char_count': row[3],
                    'indexed_at': row[4],
                    'has_embeddings': True,
                    'duration_estimate': f"{row[3] // 150} min"
                })

            return {
                'podcasts': podcasts,
                'count': len(podcasts)
            }
        finally:
            search_system.close()

    except Exception as e:
        logger.error("List podcasts error: %s", e)
        return error(500, str(e))

@app.get('/api/podcast/{podcast_id}', dependencies=SERVICES)
def get_podcast(podcast_id: int):
    """Get details of a specific podcast"""
    try:
        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('''
                SELECT id, filename, title, content, char_count, indexed_at
                FROM podcasts
                WHERE id = ?
            ''', (podcast_id,))

            row = cursor.fetchone()
            if not row:
                return error(404, 'Podcast not found')

            # Get chunk count
            cursor.execute('SELECT COUNT(*) FROM chunks WHERE podcast_id = ?', (podcast_id,))
            chunk_count = cursor.fetchone()[0]

            return {
                'id': row[0],
                'filename': row[1],
                'title': row[2],
                'content': row[3][:1000] + '...' if len(row[3]) > 1000 else row[3],
                'char_count': row[4],
                'indexed_at': row[5],
                'chunk_count': chunk_count,
                'duration_estimate': f"{row[4] // 150} min"
            }
        finally:
            search_system.close()

    except Exception as e:
        logger.error("Get podcast error: %s", e)
        return error(500, str(e))

# ──────────────────────────── Chat ──────────────────────────────

@app.post('/api/chat', dependencies=SERVICES)
def chat(body: ChatRequest):
    """Chat with the selected podcast"""
    try:
        podcast_id = body.podcast_id
        message = body.message.strip()
        # time-based ids collided for chats started in the same second
        session_id = body.session_id or f'session_{uuid.uuid4().hex}'

        if not podcast_id or not message:
            return error(400, 'podcast_id and message are required')

        # Unknown ids used to run the whole RAG graph (and bill Claude) against nothing.
        title = get_podcast_title(podcast_id)
        if title is None:
            return error(404, 'Podcast not found', podcast_id=podcast_id)

        # A session belongs to one podcast; never carry another episode's history over.
        session = current_sessions.get(session_id)
        if session is None or session['podcast_id'] != podcast_id:
            session = remember_session(current_sessions, session_id,
                                       {'podcast_id': podcast_id, 'history': []},
                                       guard.settings.max_sessions)

        # Run corrective RAG graph
        start_time = time.time()
        rag_result = run_corrective_rag(
            query=message,
            podcast_id=podcast_id,
            history=session['history'][-5:],
        )
        response = rag_result["generation"]
        response_time = time.time() - start_time

        # Save to history
        session['history'].append({
            'human': message,
            'assistant': response
        })

        return {
            'response': response,
            'session_id': session_id,
            'podcast_id': podcast_id,
            'podcast_title': rag_result.get('podcast_title') or title,
            'response_time_ms': round(response_time * 1000, 2),
            'rag_info': {
                'used_fallback': rag_result.get('used_fallback', False),
                'nodes_visited': rag_result.get('nodes_visited', []),
                'relevant_chunks': len(rag_result.get('relevant_docs', [])),
            }
        }

    except Exception as e:
        logger.error("Chat error: %s", e)
        return error(500, str(e))

@app.get('/api/chat/session/{session_id}')
def get_session(session_id: str):
    """Get chat session history"""
    if session_id not in current_sessions:
        return error(404, 'Session not found')

    session = current_sessions[session_id]
    return {
        'session_id': session_id,
        'podcast_id': session['podcast_id'],
        'history': session['history']
    }

# ──────────────────────────── Statistics ────────────────────────

@app.get('/api/stats', dependencies=SERVICES)
def get_stats():
    """Get system statistics"""
    try:
        search_system = get_search_system()
        try:
            stats = search_system.get_stats()
        finally:
            search_system.close()

        return {
            'database': {
                'total_podcasts': stats['podcasts'],
                'total_chunks': stats['chunks'],
            },
            'pinecone': {
                'total_vectors': stats.get('pinecone_vectors', 0),
            },
            'sessions': {
                'active': len(current_sessions),
                'total_messages': sum(len(s['history']) for s in current_sessions.values())
            },
            'system': {
                'search_ready': stats.get('pinecone_vectors', 0) > 0,
            },
            'features': {
                'email_summary': guard.settings.email_enabled,
            }
        }

    except Exception as e:
        logger.error("Stats error: %s", e)
        return error(500, str(e))

# ──────────────────────────── Summaries ─────────────────────────

@app.post('/api/summary/generate', dependencies=SERVICES)
def generate_summary(body: SummaryRequest):
    """Generate a summary for a podcast"""
    try:
        podcast_id = body.podcast_id
        force_regenerate = body.force_regenerate

        if not podcast_id:
            return error(400, 'podcast_id is required')

        if get_podcast_title(podcast_id) is None:
            return error(404, 'Podcast not found', podcast_id=podcast_id)

        # Generate summary
        start_time = time.time()
        result = summarization_service.get_or_generate_summary(podcast_id, force_regenerate)
        generation_time = time.time() - start_time

        if result['success']:
            return {
                'success': True,
                'podcast_id': podcast_id,
                'summary': result['summary'],
                'cached': result.get('cached', False),
                'podcast_title': result.get('podcast_title', ''),
                'generation_time_ms': round(generation_time * 1000, 2)
            }
        return error(500, result.get('error', 'Failed to generate summary'),
                     success=False, podcast_id=podcast_id)

    except Exception as e:
        logger.error("Summary generation error: %s", e)
        return error(500, str(e))

@app.post('/api/summary/email', dependencies=SERVICES)
def email_summary(body: EmailSummaryRequest):
    """Generate and email a summary for a podcast"""
    try:
        podcast_id = body.podcast_id
        user_email = body.email.strip()

        logger.info("Email summary request - Podcast ID: %s, Email: %s", podcast_id, user_email)

        if not podcast_id or not user_email:
            return error(400, 'podcast_id and email are required')

        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user_email):
            return error(400, 'Invalid email format')

        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('SELECT id, title FROM podcasts WHERE id = ?', (podcast_id,))
            podcast_check = cursor.fetchone()

            if not podcast_check:
                cursor.execute('SELECT id, title FROM podcasts LIMIT 5')
                available = cursor.fetchall()
                return error(404, f'Podcast with ID {podcast_id} not found',
                             available_podcasts=[{'id': p[0], 'title': p[1]} for p in available])
        finally:
            search_system.close()

        start_time = time.time()
        summary_result = summarization_service.generate_summary_for_email(podcast_id)

        if not summary_result['success']:
            return error(500, summary_result.get('error', 'Failed to generate summary'),
                         success=False, podcast_id=podcast_id)

        email_result = email_service.send_summary_email(
            to_email=user_email,
            subject=summary_result['subject'],
            html_content=summary_result['email_content'],
            podcast_title=summary_result['podcast_title']
        )

        total_time = time.time() - start_time

        if email_result['success']:
            return {
                'success': True,
                'message': f'Summary sent to {user_email}',
                'podcast_id': podcast_id,
                'podcast_title': summary_result['podcast_title'],
                'email': user_email,
                'cached': summary_result.get('cached', False),
                'sent_at': email_result.get('sent_at'),
                'total_time_ms': round(total_time * 1000, 2)
            }
        return error(500, email_result.get('error', 'Failed to send email'),
                     success=False, podcast_id=podcast_id, email=user_email)

    except Exception as e:
        logger.error("Email summary error: %s", e, exc_info=True)
        return error(500, str(e))

# ──────────────────────────── Main ──────────────────────────────

if __name__ == '__main__':
    import uvicorn

    services_ready = init_services()

    if services_ready:
        logger.info("All services initialized successfully")
    else:
        logger.warning(
            "Service initialization failed — ensure ANTHROPIC_API_KEY is set in "
            "config/env/config.env, Ollama is running for embeddings (ollama serve), "
            "and the database exists"
        )

    uvicorn.run(app, host='127.0.0.1', port=3000)
