#!/usr/bin/env python3
"""
Stage 1: Semantic Search for Podcast Transcripts
Database setup and text chunking
"""

import sqlite3
import os
import json
from typing import List, Dict, Tuple
import re
from datetime import datetime

class PodcastIndexer:
    def __init__(self, db_path="podcast_index.db"):
        self.db_path = db_path
        self.conn = None
        self.setup_database()
    
    def setup_database(self):
        """Create database tables if they don't exist"""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()
        
        # Create podcasts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS podcasts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE NOT NULL,
                title TEXT NOT NULL,
                content TEXT NOT NULL,
                char_count INTEGER,
                indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create chunks table (will store embeddings later)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                podcast_id INTEGER NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                char_start INTEGER,
                char_end INTEGER,
                embedding TEXT,  -- Will store JSON array later
                FOREIGN KEY (podcast_id) REFERENCES podcasts (id)
            )
        ''')
        
        # Create index for faster searches
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chunks_podcast 
            ON chunks(podcast_id)
        ''')
        
        self.conn.commit()
        print(f"✓ Database initialized at {self.db_path}")
    
    def extract_title(self, filename):
        """Extract podcast title from filename"""
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
        """
        Split text into overlapping chunks
        
        Args:
            text: Full transcript text
            chunk_size: Target words per chunk
            overlap: Number of words to overlap between chunks
        
        Returns:
            List of chunk dictionaries with content and position info
        """
        words = text.split()
        chunks = []
        
        if len(words) <= chunk_size:
            # If text is short, return as single chunk
            chunks.append({
                'content': text,
                'char_start': 0,
                'char_end': len(text),
                'chunk_index': 0
            })
            return chunks
        
        # Create overlapping chunks
        step = chunk_size - overlap
        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            
            # Calculate character positions
            if i == 0:
                char_start = 0
            else:
                # Find where this chunk starts in original text
                prefix = ' '.join(words[:i])
                char_start = len(prefix) + 1  # +1 for space
            
            char_end = char_start + len(chunk_text)
            
            chunks.append({
                'content': chunk_text,
                'char_start': char_start,
                'char_end': char_end,
                'chunk_index': len(chunks)
            })
            
            # Stop if we've processed all words
            if i + chunk_size >= len(words):
                break
        
        return chunks
    
    def index_podcast(self, filepath: str) -> bool:
        """
        Index a single podcast transcript
        
        Args:
            filepath: Path to transcript .txt file
            
        Returns:
            Success boolean
        """
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
                "SELECT id FROM podcasts WHERE filename = ?", 
                (filename,)
            )
            existing = cursor.fetchone()
            
            if existing:
                print(f"⚠️  Already indexed: {filename}")
                return False
            
            # Insert podcast
            cursor.execute('''
                INSERT INTO podcasts (filename, title, content, char_count)
                VALUES (?, ?, ?, ?)
            ''', (filename, title, content, len(content)))
            
            podcast_id = cursor.lastrowid
            
            # Create and store chunks
            chunks = self.chunk_text(content)
            
            for chunk in chunks:
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
            
            self.conn.commit()
            print(f"✓ Indexed: {filename} ({len(chunks)} chunks)")
            return True
            
        except Exception as e:
            print(f"❌ Error indexing {filepath}: {e}")
            self.conn.rollback()
            return False
    
    def get_stats(self) -> Dict:
        """Get indexing statistics"""
        cursor = self.conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM podcasts")
        podcast_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT AVG(char_count) FROM podcasts")
        avg_length = cursor.fetchone()[0] or 0
        
        return {
            'podcasts': podcast_count,
            'chunks': chunk_count,
            'avg_length': int(avg_length)
        }
    
    def list_indexed_podcasts(self) -> List[Tuple]:
        """List all indexed podcasts"""
        cursor = self.conn.cursor()
        cursor.execute('''
            SELECT filename, title, char_count, indexed_at 
            FROM podcasts 
            ORDER BY indexed_at DESC
        ''')
        return cursor.fetchall()
    
    def close(self):
        """Close database connection"""
        if self.conn:
            self.conn.close()


def test_stage1():
    """Test Stage 1 functionality"""
    print("🧪 Testing Stage 1: Database Setup & Chunking\n")
    
    # Initialize indexer
    indexer = PodcastIndexer("test_podcast_index.db")
    
    # Test 1: Text chunking
    print("Test 1: Text Chunking")
    sample_text = " ".join([f"Word{i}" for i in range(1000)])  # 1000 words
    chunks = indexer.chunk_text(sample_text, chunk_size=100, overlap=20)
    print(f"✓ Created {len(chunks)} chunks from 1000 words")
    print(f"  First chunk: {chunks[0]['content'][:50]}...")
    print(f"  Chunk overlap verified: {chunks[0]['content'].split()[-20:] == chunks[1]['content'].split()[:20]}")
    
    # Test 2: Title extraction
    print("\nTest 2: Title Extraction")
    test_names = [
        ("2024-01-15_JoeRogan.txt", "JoeRogan"),
        ("PodcastName_2024_01_15.txt", "PodcastName"),
        ("InterestingTalk-20240115.txt", "InterestingTalk"),
        ("MyPodcast.txt", "MyPodcast")
    ]
    
    for filename, expected in test_names:
        result = indexer.extract_title(filename)
        print(f"  {filename} → {result} {'✓' if result == expected else '✗'}")
    
    # Clean up test database
    indexer.close()
    if os.path.exists("test_podcast_index.db"):
        os.remove("test_podcast_index.db")
    
    print("\n✅ Stage 1 tests completed!")
    print("\nNext: Create a sample transcript file and test indexing:")
    print("  1. Create 'transcripts/test_podcast.txt' with some content")
    print("  2. Run: indexer.index_podcast('transcripts/test_podcast.txt')")
    print("  3. Check: indexer.get_stats()")


if __name__ == "__main__":
    test_stage1()