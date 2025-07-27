#!/usr/bin/env python3
"""
Two-Tiered Podcast Search System
Enhanced semantic search with weighted title, intro, and content matching
"""

import sqlite3
import os
import json
import numpy as np
from typing import List, Dict, Tuple, Optional
import requests
import re
import glob
import time
from datetime import datetime

class PodcastTwoTierSearch:
    def __init__(self, db_path="../../data/databases/podcast_index_v2.db", embedding_model="nomic-embed-text:latest"):
        self.db_path = db_path
        self.embedding_model = embedding_model
        self.conn = None
        self.base_url = "http://localhost:11434"
        self.embedding_endpoint = f"{self.base_url}/api/embeddings"
        
        # Scoring weights
        self.TITLE_WEIGHT = 0.6
        self.INTRO_WEIGHT = 0.2
        self.CHUNKS_WEIGHT = 0.15
        self.OUTRO_WEIGHT = 0.05
        self.TITLE_FALLBACK_THRESHOLD = 0.3
        
        self.setup_database()
        self._test_ollama_connection()
    
    # ========== DATABASE SETUP ==========
    
    def setup_database(self):
        """Create enhanced database schema with title and section embeddings"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Create enhanced podcasts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS podcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                char_count INTEGER,
                title_embedding TEXT,
                intro_embedding TEXT,
                outro_embedding TEXT,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create chunks table (same as before)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                podcast_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                char_start INTEGER,
                char_end INTEGER,
                embedding TEXT,
                FOREIGN KEY (podcast_id) REFERENCES podcasts (id)
            )
        ''')
        
        # Create indices
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chunks_podcast 
            ON chunks(podcast_id)
        ''')
        
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_podcasts_title_embedding 
            ON podcasts(title_embedding) WHERE title_embedding IS NOT NULL
        ''')
        
        self.conn.commit()
        print(f"✓ Enhanced database initialized at {self.db_path}")
    
    def migrate_from_v1(self, old_db_path="../../data/databases/podcast_index.db"):
        """Migrate data from original database"""
        if not os.path.exists(old_db_path):
            print(f"No existing database found at {old_db_path}")
            return
        
        print(f"🔄 Migrating from {old_db_path}...")
        old_conn = sqlite3.connect(old_db_path)
        old_cursor = old_conn.cursor()
        
        # Copy podcasts
        old_cursor.execute("SELECT * FROM podcasts")
        podcasts = old_cursor.fetchall()
        
        cursor = self.conn.cursor()
        for podcast in podcasts:
            cursor.execute('''
                INSERT OR IGNORE INTO podcasts 
                (id, filename, title, content, char_count, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', podcast[:6])  # First 6 columns
        
        # Copy chunks
        old_cursor.execute("SELECT * FROM chunks")
        chunks = old_cursor.fetchall()
        
        for chunk in chunks:
            cursor.execute('''
                INSERT OR IGNORE INTO chunks 
                (id, podcast_id, chunk_index, content, char_start, char_end, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', chunk)
        
        self.conn.commit()
        old_conn.close()
        print(f"✓ Migrated {len(podcasts)} podcasts and {len(chunks)} chunks")
    
    # ========== EMBEDDING GENERATION ==========
    
    def _test_ollama_connection(self):
        """Test if Ollama is running and model is available"""
        try:
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code != 200:
                raise ConnectionError("Ollama is not running")
            
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]
            
            model_found = self.embedding_model in model_names
            if not model_found and f"{self.embedding_model}:latest" in model_names:
                self.embedding_model = f"{self.embedding_model}:latest"
                model_found = True
            
            if not model_found:
                print(f"⚠️  Model '{self.embedding_model}' not found")
                print(f"Available models: {model_names}")
                raise ValueError(f"Model {self.embedding_model} not available")
            
            print(f"✓ Connected to Ollama with model: {self.embedding_model}")
            
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to Ollama")
            print("Make sure Ollama is running: ollama serve")
            raise
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for text using Ollama"""
        try:
            response = requests.post(
                self.embedding_endpoint,
                json={
                    "model": self.embedding_model,
                    "prompt": text
                }
            )
            
            if response.status_code == 200:
                return response.json()['embedding']
            else:
                print(f"❌ Error generating embedding: {response.status_code}")
                return None
                
        except Exception as e:
            print(f"❌ Embedding error: {e}")
            return None
    
    def cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculate cosine similarity between two vectors"""
        vec1 = np.array(vec1)
        vec2 = np.array(vec2)
        
        dot_product = np.dot(vec1, vec2)
        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
    
    # ========== ENHANCED INDEXING ==========
    
    def extract_title(self, filename):
        """Extract clean title from filename"""
        name = os.path.splitext(filename)[0]
        
        # Remove date patterns
        date_patterns = [
            r'\d{4}[-_]\d{2}[-_]\d{2}',
            r'\d{8}',
            r'\d{2}[-_]\d{2}[-_]\d{4}',
            r'\d{4}[-_]\d{1,2}[-_]\d{1,2}',
        ]
        
        for pattern in date_patterns:
            name = re.sub(pattern, '', name)
        
        name = name.replace('_', ' ').replace('-', ' ')
        name = ' '.join(name.split())
        
        return name.strip()
    
    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[Dict]:
        """Split text into overlapping chunks"""
        words = text.split()
        chunks = []
        
        if len(words) <= chunk_size:
            chunks.append({
                'content': text,
                'char_start': 0,
                'char_end': len(text),
                'chunk_index': 0
            })
            return chunks
        
        step = chunk_size - overlap
        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            if i == 0:
                char_start = 0
            else:
                prefix = ' '.join(words[:i])
                char_start = len(prefix) + 1
            
            char_end = char_start + len(chunk_text)
            
            chunks.append({
                'content': chunk_text,
                'char_start': char_start,
                'char_end': char_end,
                'chunk_index': len(chunks)
            })
            
            if i + chunk_size >= len(words):
                break
        
        return chunks
    
    def index_podcast_enhanced(self, filepath: str) -> bool:
        """Index podcast with title, intro, outro, and chunk embeddings"""
        try:
            filename = os.path.basename(filepath)
            title = self.extract_title(filename)
            
            # Read transcript
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()
            
            if not content:
                print(f"⚠️  Empty transcript: {filename}")
                return False
            
            cursor = self.conn.cursor()
            
            # Check if already indexed
            cursor.execute(
                "SELECT id, title_embedding FROM podcasts WHERE filename = ?", 
                (filename,)
            )
            existing = cursor.fetchone()
            
            if existing and existing[1]:  # Has embeddings already
                print(f"⚠️  Already indexed with embeddings: {filename}")
                return False
            
            print(f"📝 Processing {filename}")
            
            # Generate title embedding
            print(f"  Generating title embedding...")
            title_embedding = self.generate_embedding(title)
            
            # Extract and embed intro (first 1000 chars)
            intro_text = content[:1000]
            print(f"  Generating intro embedding...")
            intro_embedding = self.generate_embedding(intro_text)
            
            # Extract and embed outro (last 1000 chars)
            outro_text = content[-1000:] if len(content) > 1000 else content
            print(f"  Generating outro embedding...")
            outro_embedding = self.generate_embedding(outro_text)
            
            if existing:
                # Update existing podcast with embeddings
                podcast_id = existing[0]
                cursor.execute('''
                    UPDATE podcasts 
                    SET title_embedding = ?, intro_embedding = ?, outro_embedding = ?
                    WHERE id = ?
                ''', (
                    json.dumps(title_embedding) if title_embedding else None,
                    json.dumps(intro_embedding) if intro_embedding else None,
                    json.dumps(outro_embedding) if outro_embedding else None,
                    podcast_id
                ))
            else:
                # Insert new podcast
                cursor.execute('''
                    INSERT INTO podcasts 
                    (filename, title, content, char_count, title_embedding, intro_embedding, outro_embedding)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (
                    filename, 
                    title, 
                    content, 
                    len(content),
                    json.dumps(title_embedding) if title_embedding else None,
                    json.dumps(intro_embedding) if intro_embedding else None,
                    json.dumps(outro_embedding) if outro_embedding else None
                ))
                podcast_id = cursor.lastrowid
                
                # Create and store chunks
                chunks = self.chunk_text(content)
                print(f"  Processing {len(chunks)} chunks...")
                
                for i, chunk in enumerate(chunks):
                    # Insert chunk
                    cursor.execute('''
                        INSERT INTO chunks 
                        (podcast_id, chunk_index, content, char_start, char_end)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (
                        podcast_id,
                        chunk['chunk_index'],
                        chunk['content'],
                        chunk['char_start'],
                        chunk['char_end']
                    ))
                    
                    chunk_id = cursor.lastrowid
                    
                    # Generate embedding
                    embedding = self.generate_embedding(chunk['content'])
                    if embedding:
                        cursor.execute(
                            "UPDATE chunks SET embedding = ? WHERE id = ?",
                            (json.dumps(embedding), chunk_id)
                        )
                    
                    print(f"    Chunk {i+1}/{len(chunks)}", end='\r')
            
            self.conn.commit()
            print(f"\n✓ Indexed: {filename}")
            return True
            
        except Exception as e:
            print(f"❌ Error indexing {filepath}: {e}")
            self.conn.rollback()
            return False
    
    # ========== TWO-TIERED SEARCH ==========
    
    def search_two_tier(self, query: str, top_k: int = 5) -> List[Dict]:
        """Two-tiered search with weighted scoring"""
        # Generate query embedding
        query_embedding = self.generate_embedding(query)
        if not query_embedding:
            print("❌ Failed to generate query embedding")
            return []
        
        cursor = self.conn.cursor()
        
        # Phase 1: Get all podcasts with embeddings
        cursor.execute('''
            SELECT id, filename, title, content, 
                   title_embedding, intro_embedding, outro_embedding
            FROM podcasts
            WHERE title_embedding IS NOT NULL
        ''')
        
        podcast_scores = []
        
        for row in cursor.fetchall():
            podcast_id, filename, title, content, title_emb, intro_emb, outro_emb = row
            
            # Calculate similarities
            title_sim = 0.0
            intro_sim = 0.0
            outro_sim = 0.0
            
            if title_emb:
                title_sim = self.cosine_similarity(query_embedding, json.loads(title_emb))
            if intro_emb:
                intro_sim = self.cosine_similarity(query_embedding, json.loads(intro_emb))
            if outro_emb:
                outro_sim = self.cosine_similarity(query_embedding, json.loads(outro_emb))
            
            # Get top chunks for this podcast
            cursor.execute('''
                SELECT content, embedding
                FROM chunks
                WHERE podcast_id = ? AND embedding IS NOT NULL
                ORDER BY chunk_index
            ''', (podcast_id,))
            
            chunk_sims = []
            for chunk_content, chunk_emb in cursor.fetchall():
                if chunk_emb:
                    sim = self.cosine_similarity(query_embedding, json.loads(chunk_emb))
                    chunk_sims.append(sim)
            
            # Calculate average of top 3 chunks
            chunk_sims.sort(reverse=True)
            top_chunks_avg = np.mean(chunk_sims[:3]) if chunk_sims else 0.0
            
            # Calculate weighted score
            final_score = (
                self.TITLE_WEIGHT * title_sim +
                self.INTRO_WEIGHT * intro_sim +
                self.CHUNKS_WEIGHT * top_chunks_avg +
                self.OUTRO_WEIGHT * outro_sim
            )
            
            podcast_scores.append({
                'podcast_id': podcast_id,
                'filename': filename,
                'title': title,
                'title_similarity': title_sim,
                'intro_similarity': intro_sim,
                'chunks_similarity': top_chunks_avg,
                'outro_similarity': outro_sim,
                'final_score': final_score,
                'content_preview': content[:200] + '...' if len(content) > 200 else content
            })
        
        # Check if we need fallback to pure content search
        best_title_score = max((p['title_similarity'] for p in podcast_scores), default=0)
        
        if best_title_score < self.TITLE_FALLBACK_THRESHOLD:
            print(f"📊 Title scores low (best: {best_title_score:.3f}), using content-focused search")
            # Adjust weights for content-focused search
            for podcast in podcast_scores:
                podcast['final_score'] = (
                    0.1 * podcast['title_similarity'] +
                    0.3 * podcast['intro_similarity'] +
                    0.5 * podcast['chunks_similarity'] +
                    0.1 * podcast['outro_similarity']
                )
        
        # Sort by final score
        podcast_scores.sort(key=lambda x: x['final_score'], reverse=True)
        
        return podcast_scores[:top_k]
    
    def find_best_podcast_two_tier(self, query: str) -> Optional[Dict]:
        """Find single best matching podcast"""
        results = self.search_two_tier(query, top_k=1)
        return results[0] if results else None
    
    # ========== UTILITY FUNCTIONS ==========
    
    def index_all_podcasts_enhanced(self, folder="transcripts"):
        """Index all podcasts with enhanced embeddings"""
        if not os.path.exists(folder):
            print(f"❌ Folder {folder} not found")
            return
        
        files = glob.glob(os.path.join(folder, "*.txt"))
        if not files:
            print(f"❌ No .txt files found in {folder}")
            return
        
        print(f"🎙️  Found {len(files)} transcripts to index\n")
        
        start_time = time.time()
        success_count = 0
        
        for filepath in files:
            if self.index_podcast_enhanced(filepath):
                success_count += 1
        
        elapsed = time.time() - start_time
        print(f"\n✅ Indexed {success_count}/{len(files)} podcasts in {elapsed:.1f} seconds")
        
        stats = self.get_stats()
        print(f"📊 Total: {stats['podcasts']} podcasts, {stats['chunks']} chunks")
        print(f"🎯 Title embeddings: {stats['title_embeddings']}")
    
    def get_stats(self) -> Dict:
        """Get enhanced statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM podcasts")
        podcast_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM podcasts WHERE title_embedding IS NOT NULL")
        title_embeddings = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
        embedded_chunks = cursor.fetchone()[0]
        
        return {
            'podcasts': podcast_count,
            'title_embeddings': title_embeddings,
            'chunks': chunk_count,
            'embedded_chunks': embedded_chunks
        }
    
    def debug_search(self, query: str):
        """Debug search to see scoring breakdown"""
        results = self.search_two_tier(query, top_k=5)
        
        print(f"\n🔍 Debug Search: '{query}'\n")
        
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']} ({result['filename']})")
            print(f"   Title similarity: {result['title_similarity']:.3f} (weight: {self.TITLE_WEIGHT})")
            print(f"   Intro similarity: {result['intro_similarity']:.3f} (weight: {self.INTRO_WEIGHT})")
            print(f"   Chunks similarity: {result['chunks_similarity']:.3f} (weight: {self.CHUNKS_WEIGHT})")
            print(f"   Outro similarity: {result['outro_similarity']:.3f} (weight: {self.OUTRO_WEIGHT})")
            print(f"   → Final score: {result['final_score']:.3f}\n")
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def upgrade_existing_database():
    """Upgrade existing database with enhanced embeddings"""
    print("🚀 Upgrading Podcast Search System\n")
    
    search = PodcastTwoTierSearch()
    
    # Migrate from v1 if exists
    if os.path.exists("../../data/databases/podcast_index.db"):
        search.migrate_from_v1()
    
    # Re-index with enhanced embeddings
    choice = input("Re-index all podcasts with title embeddings? (y/n): ").strip().lower()
    if choice == 'y':
        search.index_all_podcasts_enhanced("transcripts")
    
    # Test the new search
    print("\n🧪 Testing enhanced search:")
    test_query = input("Enter a test search query: ").strip()
    if test_query:
        search.debug_search(test_query)
    
    search.close()


if __name__ == "__main__":
    upgrade_existing_database()