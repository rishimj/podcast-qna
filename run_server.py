#!/usr/bin/env python3
"""
Startup script for the Podcast RAG API server
"""

import os
import sys

# Add backend to Python path
backend_path = os.path.join(os.path.dirname(__file__), 'backend')
sys.path.insert(0, backend_path)

# Change to backend directory for relative paths to work
os.chdir(backend_path)

# Import and run the controller
from api.controller import app

if __name__ == '__main__':
    print("🚀 Starting Podcast RAG API Server from organized structure\n")
    # No reloader: it re-executes sys.argv[0] relative to the cwd, which the
    # chdir above breaks, so the server died on startup. Bound to localhost
    # because debug mode serves Werkzeug's interactive debugger, a remote
    # Python console; set FLASK_DEBUG=1 to enable it.
    app.run(host='127.0.0.1', port=3000,
            debug=os.getenv('FLASK_DEBUG') == '1', use_reloader=False)