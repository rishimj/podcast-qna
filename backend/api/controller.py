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

# ADD THIS: Load environment variables from config file
def load_config():
    """Load environment variables from config.env file"""
    from pathlib import Path
    # Path to config file (from backend/api/ to config/env/config.env)
    config_path = Path(__file__).parent.parent.parent / 'config' / 'env' / 'config.env'
    
    if config_path.exists():
        logger.info(f"📄 Loading configuration from {config_path}")
        with open(config_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
        logger.info("✓ Configuration loaded successfully")
        
        # Log loaded email config (without password)
        if os.getenv('SMTP_USERNAME'):
            logger.info(f"✓ Email configured for: {os.getenv('SMTP_USERNAME')}")
        else:
            logger.warning("⚠️  SMTP_USERNAME not found in config")
    else:
        logger.error(f"❌ Config file not found: {config_path}")
        logger.info("💡 Please ensure config/env/config.env exists with your SMTP credentials")
        
# Import our existing modules
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
from search.podcast_semantic_search_complete import PodcastTwoTierSearch
from search.summarization_service import PodcastSummarizationService
from search.email_service import EmailService
from langchain_ollama import OllamaLLM

# Initialize Flask app
app = Flask(__name__)
CORS(app)  # Enable CORS for React frontend

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_config()

# Global instances
llm = None
summarization_service = None
email_service = None
current_sessions = {}  # Store chat sessions

def init_services():
    """Initialize LLM, summarization, and email services"""
    global llm, summarization_service, email_service
    
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
        
        # Initialize summarization service
        logger.info("Initializing summarization service...")
        try:
            # Manually specify the correct database path
            from pathlib import Path
            api_dir = Path(__file__).parent  # backend/api
            project_root = api_dir.parent.parent  # project root
            db_path = project_root / "data" / "databases" / "podcast_index_v2.db"
            logger.info(f"🗃️ Using database path: {db_path}")
            
            summarization_service = PodcastSummarizationService(db_path=str(db_path))
            logger.info("✓ Summarization service initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize summarization service: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        
        # Initialize email service
        logger.info("Initializing email service...")
        try:
            email_service = EmailService()
            logger.info("✓ Email service initialized")
        except Exception as e:
            logger.error(f"❌ Failed to initialize email service: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        
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

# ========== HEALTH CHECK ==========

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

# ========== SUMMARY ENDPOINTS ==========

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
        logger.error(f"Summary generation error: {e}")
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
        
        logger.info(f"📧 Email summary request - Podcast ID: {podcast_id}, Email: {user_email}")
        
        if not podcast_id or not user_email:
            logger.error("❌ Missing required fields: podcast_id or email")
            return jsonify({'error': 'podcast_id and email are required'}), 400
        
        # Validate email format (basic check)
        import re
        email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(email_pattern, user_email):
            logger.error(f"❌ Invalid email format: {user_email}")
            return jsonify({'error': 'Invalid email format'}), 400
        
        # First check if podcast exists
        search_system = get_search_system()
        try:
            cursor = search_system.conn.cursor()
            cursor.execute('SELECT id, title FROM podcasts WHERE id = ?', (podcast_id,))
            podcast_check = cursor.fetchone()
            
            if not podcast_check:
                cursor.execute('SELECT id, title FROM podcasts LIMIT 5')
                available = cursor.fetchall()
                logger.error(f"❌ Podcast {podcast_id} not found. Available IDs: {[p[0] for p in available]}")
                return jsonify({
                    'error': f'Podcast with ID {podcast_id} not found',
                    'available_podcasts': [{'id': p[0], 'title': p[1]} for p in available]
                }), 404
            
            logger.info(f"✅ Found podcast: {podcast_check[1]}")
        finally:
            search_system.close()
        
        # Generate summary for email
        start_time = time.time()
        logger.info("🤖 Generating summary...")
        summary_result = summarization_service.generate_summary_for_email(podcast_id)
        
        if not summary_result['success']:
            logger.error(f"❌ Summary generation failed: {summary_result.get('error')}")
            return jsonify({
                'success': False,
                'error': summary_result.get('error', 'Failed to generate summary'),
                'podcast_id': podcast_id
            }), 500
        
        logger.info("✅ Summary generated successfully")
        
        # Send email
        logger.info(f"📤 Sending email to {user_email}...")
        email_result = email_service.send_summary_email(
            to_email=user_email,
            subject=summary_result['subject'],
            html_content=summary_result['email_content'],
            podcast_title=summary_result['podcast_title']
        )
        
        total_time = time.time() - start_time
        
        if email_result['success']:
            logger.info(f"✅ Email sent successfully to {user_email}")
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
            logger.error(f"❌ Email sending failed: {email_result.get('error')}")
            return jsonify({
                'success': False,
                'error': email_result.get('error', 'Failed to send email'),
                'podcast_id': podcast_id,
                'email': user_email
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Email summary error: {e}")
        import traceback
        logger.error(traceback.format_exc())
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
    print("  GET    /api/health             - Health check")
    print("  POST   /api/search             - Search for podcasts")
    print("  POST   /api/chat               - Chat with podcast")
    print("  GET    /api/podcasts           - List all podcasts")
    print("  GET    /api/podcast/<id>       - Get podcast details")
    print("  GET    /api/stats              - System statistics")
    print("  POST   /api/summary/generate   - Generate podcast summary")
    print("  POST   /api/summary/email      - Generate and email summary")
    print(f"\n🌐 Starting server on http://localhost:3000")
    
    app.run(debug=True, host='127.0.0.1', port=3000)