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
    app.run(debug=True, host='0.0.0.0', port=3000)