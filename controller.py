#!/usr/bin/env python3
"""
Flask Backend API for Podcast RAG Chatbot
Provides REST endpoints for search and chat functionality
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import os
import sys
from datetime import datetime
import logging
from functools import wraps
import time

# Import our existing modules
from podcast_semantic_search_complete import PodcastTwoTierSearch
from langchain_ollama import OllamaLLM

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global instances
llm = None
current_sessions = {}  # Store chat sessions

def init_services():
    """Initialize LLM (search system will be created per request)"""
    global llm
    
    try:
        # Initialize LLM
        logger.info("Initializing LLM...")
        llm = OllamaLLM(
            model="llama3",
            temperature=0.7,
            base_url="http://localhost:11434"
        )
        # Test LLM connection
        logger.info("Testing LLM connection...")
        test_response = llm.invoke("Hello")
        logger.info("✓ LLM initialized")
        
        return True
    except Exception as e:
        logger.error(f"Failed to initialize services: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def get_search_system():
    """Get a new search system instance for this thread"""
    return PodcastTwoTierSearch()

def require_services(f):
    """Decorator to ensure services are initialized"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        global llm
        if llm is None:
            logger.info("Services not initialized, reinitializing...")
            if not init_services():
                return jsonify({
                    'error': 'Services not initialized',
                    'message': 'Please ensure Ollama is running and database exists'
                }), 503
        return f(*args, **kwargs)
    return decorated_function

# ========== HEALTH CHECK ==========

@app.route('/api/health', methods=['GET'])
def health_check():
    """Check if all services are running"""
    status = {
        'api': 'running',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'search_system': True,  # Always available since we create per request
            'llm': llm is not None
        }
    }
    
    # Test database connection
    try:
        search_system = get_search_system()
        stats = search_system.get_stats()
        status['database'] = {
            'connected': True,
            'podcasts': stats['podcasts'],
            'chunks': stats['chunks']
        }
        search_system.close()
    except Exception as e:
        logger.error(f"Database stats error: {e}")
        status['database'] = {
            'connected': False,
            'podcasts': 0,
            'chunks': 0,
            'error': str(e)
        }
    
    return jsonify(status)

# ========== SEARCH ENDPOINTS ==========

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
        logger.error(f"Search error: {e}")
        return jsonify({'error': str(e)}), 500

# ========== PODCAST ENDPOINTS ==========

@app.route('/api/podcasts', methods=['GET'])
@require_services
def list_podcasts():
    """Get list of all indexed podcasts"""
    try:
        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('''
                SELECT id, filename, title, char_count, indexed_at,
                       CASE WHEN title_embedding IS NOT NULL THEN 1 ELSE 0 END as has_embeddings
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
                    'has_embeddings': bool(row[5]),
                    'duration_estimate': f"{row[3] // 150} min"  # Rough estimate
                })
            
            return jsonify({
                'podcasts': podcasts,
                'count': len(podcasts)
            })
        finally:
            search_system.close()
        
    except Exception as e:
        logger.error(f"List podcasts error: {e}")
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
        logger.error(f"Get podcast error: {e}")
        return jsonify({'error': str(e)}), 500

# ========== CHAT ENDPOINTS ==========

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
        
        # Get podcast content
        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('SELECT title, content FROM podcasts WHERE id = ?', (podcast_id,))
            result = cursor.fetchone()
        finally:
            search_system.close()
        
        if not result:
            return jsonify({'error': 'Podcast not found'}), 404
        
        title, content = result
        
        # Get or create session
        if session_id not in current_sessions:
            current_sessions[session_id] = {
                'podcast_id': podcast_id,
                'history': []
            }
        
        session = current_sessions[session_id]
        
        # Build conversation history
        history_str = ""
        for h in session['history'][-5:]:  # Last 5 exchanges
            history_str += f"Human: {h['human']}\nAssistant: {h['assistant']}\n\n"
        
        # Create prompt
        prompt = f"""You are a helpful assistant for answering questions about podcasts based on their transcripts.

IMPORTANT INSTRUCTIONS:
- Answer questions based ONLY on the podcast transcript provided below
- If information is not in the transcript, say "I don't find that information in the transcript"
- Quote relevant parts from the transcript when answering
- Be specific and accurate
- The podcast is titled: {title}

PODCAST TRANSCRIPT:
{content}

CONVERSATION HISTORY:
{history_str}

CURRENT QUESTION: {message}

Please answer the question based on the podcast transcript above."""
        
        # Get response from LLM
        start_time = time.time()
        response = llm.invoke(prompt)
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
            'podcast_title': title,
            'response_time_ms': round(response_time * 1000, 2)
        })
        
    except Exception as e:
        logger.error(f"Chat error: {e}")
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

# ========== STATISTICS ENDPOINT ==========

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
                'podcasts_with_embeddings': stats['title_embeddings'],
                'total_chunks': stats['chunks'],
                'embedded_chunks': stats['embedded_chunks']
            },
            'sessions': {
                'active': len(current_sessions),
                'total_messages': sum(len(s['history']) for s in current_sessions.values())
            },
            'system': {
                'search_ready': stats['title_embeddings'] > 0,
                'embedding_coverage': round((stats['embedded_chunks'] / stats['chunks'] * 100), 1) if stats['chunks'] > 0 else 0
            }
        })
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        return jsonify({'error': str(e)}), 500

# ========== ERROR HANDLERS ==========

@app.errorhandler(404)
def not_found(e):
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def server_error(e):
    return jsonify({'error': 'Internal server error'}), 500

# ========== MAIN ==========

if __name__ == '__main__':
    print("🚀 Starting Podcast RAG API Server\n")
    
    # Initialize services
    services_ready = init_services()
    
    if services_ready:
        print("✅ LLM service initialized successfully")
        print("✅ Search system will be initialized per request")
    else:
        print("⚠️ LLM service failed to initialize - API will start but functionality may be limited")
        print("Check the logs above for details")
        print("\nTo fix:")
        print("1. Make sure Ollama is running: ollama serve")
        print("2. Make sure database exists: python podcast_semantic_search_complete.py")
    
    print("\n📡 API Endpoints:")
    print("  GET    /api/health        - Health check")
    print("  POST   /api/search        - Search for podcasts")
    print("  POST   /api/chat          - Chat with podcast")
    print("  GET    /api/podcasts      - List all podcasts")
    print("  GET    /api/podcast/<id>  - Get podcast details")
    print("  GET    /api/stats         - System statistics")
    print(f"\n🌐 Starting server on http://localhost:3000")
    
    app.run(debug=True, host='0.0.0.0', port=3000)