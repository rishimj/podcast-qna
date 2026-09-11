#!/usr/bin/env python3
"""
Startup script for the Podcast RAG API server
"""

import os
import sys

import uvicorn

# Add backend to Python path
backend_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'backend')
sys.path.insert(0, backend_path)

# Change to backend directory for relative paths to work
os.chdir(backend_path)

# Import and run the controller
from api.controller import app

if __name__ == '__main__':
    print("🚀 Starting Podcast RAG API Server (FastAPI)\n")
    # Localhost only: the API has no auth and can send email and spend Claude
    # credits. Interactive API docs are served at http://127.0.0.1:3000/docs.
    uvicorn.run(app, host='127.0.0.1', port=3000)
