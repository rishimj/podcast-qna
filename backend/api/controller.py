#!/usr/bin/env python3
"""
Flask Backend API for Podcast RAG Chatbot
Provides REST endpoints for search and chat functionality
"""

import logging
import os
import re
import sys
import time
from datetime import datetime
from functools import wraps
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, request, jsonify
from flask_cors import CORS
from langchain_ollama import OllamaLLM

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from search.podcast_semantic_search_complete import PodcastTwoTierSearch
from search.summarization_service import PodcastSummarizationService
from search.email_service import EmailService
from search.corrective_rag import run_corrective_rag, init_rag_resources

load_dotenv(Path(__file__).parent.parent.parent / '.env')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)


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

llm = None
summarization_service = None
email_service = None
current_sessions = {}

def init_services():
    """Initialize LLM, summarization, and email services."""
    global llm, summarization_service, email_service

    try:
        logger.info("Initializing LLM...")
        llm = OllamaLLM(
            model="llama3",
            temperature=0.7,
            base_url="http://localhost:11434"
        )
        llm.invoke("Hello")
        logger.info("LLM initialized")

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

def get_search_system():
    """Create a new search system instance (one per request)."""
    return PodcastTwoTierSearch()


def require_services(f):
    """Decorator to ensure services are initialized before handling a request."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global llm, summarization_service, email_service
        if llm is None or summarization_service is None or email_service is None:
            logger.info("Services not initialized, reinitializing...")
            if not init_services():
                return jsonify({
                    'error': 'Services not initialized',
                    'message': 'Please ensure Ollama is running and database exists'
                }), 503
        return f(*args, **kwargs)
    return decorated_function


# ──────────────────────────── Health ────────────────────────────

@app.route('/api/health', methods=['GET'])
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
    
    return jsonify(status)

# ──────────────────────────── Search ────────────────────────────

@app.route('/api/search', methods=['POST'])
@require_services
def search_podcasts():
    """
    Search for podcasts using two-tiered semantic search
    
    Request body:
    {
        "query": "consciousness and AI",
        "top_k": 5
    }
    """
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        top_k = data.get('top_k', 5)
        
        if not query:
            return jsonify({'error': 'Query is required'}), 400
        
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
                'confidence': round(result['final_score'], 3),
                'confidence_percent': round(result['final_score'] * 100, 1),
                'content_preview': result['content_preview'],
                'scoring': {
                    'title': round(result['title_similarity'], 3),
                    'intro': round(result['intro_similarity'], 3),
                    'content': round(result['chunks_similarity'], 3),
                    'outro': round(result['outro_similarity'], 3)
                }
            })
        
        return jsonify({
            'query': query,
            'results': formatted_results,
            'count': len(formatted_results),
            'search_time_ms': round(search_time * 1000, 2)
        })
        
    except Exception as e:
        logger.error("Search error: %s", e)
        return jsonify({'error': str(e)}), 500

# ──────────────────────────── Podcasts ──────────────────────────

@app.route('/api/podcasts', methods=['GET'])
@require_services
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
            
            return jsonify({
                'podcasts': podcasts,
                'count': len(podcasts)
            })
        finally:
            search_system.close()
        
    except Exception as e:
        logger.error("List podcasts error: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/podcast/<int:podcast_id>', methods=['GET'])
@require_services
def get_podcast(podcast_id):
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
                return jsonify({'error': 'Podcast not found'}), 404
            
            # Get chunk count
            cursor.execute('SELECT COUNT(*) FROM chunks WHERE podcast_id = ?', (podcast_id,))
            chunk_count = cursor.fetchone()[0]
            
            podcast = {
                'id': row[0],
                'filename': row[1],
                'title': row[2],
                'content': row[3][:1000] + '...' if len(row[3]) > 1000 else row[3],
                'char_count': row[4],
                'indexed_at': row[5],
                'chunk_count': chunk_count,
                'duration_estimate': f"{row[4] // 150} min"
            }
            
            return jsonify(podcast)
        finally:
            search_system.close()
        
    except Exception as e:
        logger.error("Get podcast error: %s", e)
        return jsonify({'error': str(e)}), 500

# ──────────────────────────── Chat ──────────────────────────────

@app.route('/api/chat', methods=['POST'])
@require_services
def chat():
    """
    Chat with selected podcast
    
    Request body:
    {
        "podcast_id": 1,
        "message": "What did they discuss about AI?",
        "session_id": "optional-session-id"
    }
    """
    try:
        data = request.get_json()
        podcast_id = data.get('podcast_id')
        message = data.get('message', '').strip()
        session_id = data.get('session_id', f'session_{int(time.time())}')
        
        if not podcast_id or not message:
            return jsonify({'error': 'podcast_id and message are required'}), 400
        
        # Get or create session
        if session_id not in current_sessions:
            current_sessions[session_id] = {
                'podcast_id': podcast_id,
                'history': []
            }
        
        session = current_sessions[session_id]
        
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
        
        return jsonify({
            'response': response,
            'session_id': session_id,
            'podcast_id': podcast_id,
            'podcast_title': rag_result.get('podcast_title', ''),
            'response_time_ms': round(response_time * 1000, 2),
            'rag_info': {
                'used_fallback': rag_result.get('used_fallback', False),
                'nodes_visited': rag_result.get('nodes_visited', []),
                'relevant_chunks': len(rag_result.get('relevant_docs', [])),
            }
        })
        
    except Exception as e:
        logger.error("Chat error: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/chat/session/<session_id>', methods=['GET'])
def get_session(session_id):
    """Get chat session history"""
    if session_id not in current_sessions:
        return jsonify({'error': 'Session not found'}), 404
    
    session = current_sessions[session_id]
    return jsonify({
        'session_id': session_id,
        'podcast_id': session['podcast_id'],
        'history': session['history']
    })

# ──────────────────────────── Statistics ────────────────────────

@app.route('/api/stats', methods=['GET'])
@require_services
def get_stats():
    """Get system statistics"""
    try:
        search_system = get_search_system()
        try:
            stats = search_system.get_stats()
        finally:
            search_system.close()
        
        return jsonify({
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
            }
        })
        
    except Exception as e:
        logger.error("Stats error: %s", e)
        return jsonify({'error': str(e)}), 500

# ──────────────────────────── Summaries ─────────────────────────

@app.route('/api/summary/generate', methods=['POST'])
@require_services
def generate_summary():
    """
    Generate summary for a podcast
    
    Request body:
    {
        "podcast_id": 1,
        "force_regenerate": false
    }
    """
    try:
        data = request.get_json()
        podcast_id = data.get('podcast_id')
        force_regenerate = data.get('force_regenerate', False)
        
        if not podcast_id:
            return jsonify({'error': 'podcast_id is required'}), 400
        
        # Generate summary
        start_time = time.time()
        result = summarization_service.get_or_generate_summary(podcast_id, force_regenerate)
        generation_time = time.time() - start_time
        
        if result['success']:
            return jsonify({
                'success': True,
                'podcast_id': podcast_id,
                'summary': result['summary'],
                'cached': result.get('cached', False),
                'podcast_title': result.get('podcast_title', ''),
                'generation_time_ms': round(generation_time * 1000, 2)
            })
        else:
            return jsonify({
                'success': False,
                'error': result.get('error', 'Failed to generate summary'),
                'podcast_id': podcast_id
            }), 500
            
    except Exception as e:
        logger.error("Summary generation error: %s", e)
        return jsonify({'error': str(e)}), 500

@app.route('/api/summary/email', methods=['POST'])
@require_services
def email_summary():
    """
    Generate and email summary for a podcast
    
    Request body:
    {
        "podcast_id": 1,
        "email": "user@example.com",
        "force_regenerate": false
    }
    """
    try:
        data = request.get_json()
        podcast_id = data.get('podcast_id')
        user_email = data.get('email', '').strip()
        force_regenerate = data.get('force_regenerate', False)
        
        logger.info("Email summary request - Podcast ID: %s, Email: %s", podcast_id, user_email)

        if not podcast_id or not user_email:
            return jsonify({'error': 'podcast_id and email are required'}), 400

        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user_email):
            return jsonify({'error': 'Invalid email format'}), 400

        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('SELECT id, title FROM podcasts WHERE id = ?', (podcast_id,))
            podcast_check = cursor.fetchone()

            if not podcast_check:
                cursor.execute('SELECT id, title FROM podcasts LIMIT 5')
                available = cursor.fetchall()
                return jsonify({
                    'error': f'Podcast with ID {podcast_id} not found',
                    'available_podcasts': [{'id': p[0], 'title': p[1]} for p in available]
                }), 404
        finally:
            search_system.close()

        start_time = time.time()
        summary_result = summarization_service.generate_summary_for_email(podcast_id)

        if not summary_result['success']:
            return jsonify({
                'success': False,
                'error': summary_result.get('error', 'Failed to generate summary'),
                'podcast_id': podcast_id
            }), 500

        email_result = email_service.send_summary_email(
            to_email=user_email,
            subject=summary_result['subject'],
            html_content=summary_result['email_content'],
            podcast_title=summary_result['podcast_title']
        )

        total_time = time.time() - start_time

        if email_result['success']:
            return jsonify({
                'success': True,
                'message': f'Summary sent to {user_email}',
                'podcast_id': podcast_id,
                'podcast_title': summary_result['podcast_title'],
                'email': user_email,
                'cached': summary_result.get('cached', False),
                'sent_at': email_result.get('sent_at'),
                'total_time_ms': round(total_time * 1000, 2)
            })
        else:
            return jsonify({
                'success': False,
                'error': email_result.get('error', 'Failed to send email'),
                'podcast_id': podcast_id,
                'email': user_email
            }), 500

    except Exception as e:
        logger.error("Email summary error: %s", e, exc_info=True)
        return jsonify({'error': str(e)}), 500

# ──────────────────────────── Error Handlers ────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ──────────────────────────── Main ──────────────────────────────

if __name__ == '__main__':
    services_ready = init_services()

    if services_ready:
        logger.info("All services initialized successfully")
    else:
        logger.warning(
            "Service initialization failed — ensure Ollama is running "
            "(ollama serve) and the database exists"
        )

    app.run(debug=True, host='127.0.0.1', port=3000)