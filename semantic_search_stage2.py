#!/usr/bin/env python3
"""
Stage 2: Semantic Search for Podcast Transcripts
Embedding generation using Ollama
"""

import sqlite3
import os
import json
import numpy as np
from typing import List, Dict, Tuple, Optional
import requests
from semantic_search_stage1 import PodcastIndexer

class EmbeddingGenerator:
    def __init__(self, model_name="nomic-embed-text:latest", base_url="http://localhost:11434"):
        """
        Initialize embedding generator with Ollama
        
        Args:
            model_name: Ollama embedding model to use
            base_url: Ollama API endpoint
        """
        self.model_name = model_name
        self.base_url = base_url
        self.embedding_endpoint = f"{base_url}/api/embeddings"
        
        # Test connection
        self._test_connection()
    
    def _test_connection(self):
        """Test if Ollama is running and model is available"""
        try:
            # Test if Ollama is running
            response = requests.get(f"{self.base_url}/api/tags")
            if response.status_code != 200:
                raise ConnectionError("Ollama is not running")
            
            # Check if embedding model is available
            models = response.json().get('models', [])
            model_names = [m['name'] for m in models]
            
            # Check both with and without :latest tag
            model_found = False
            if self.model_name in model_names:
                model_found = True
            elif self.model_name.replace(':latest', '') in model_names:
                model_found = True
            elif f"{self.model_name}:latest" in model_names:
                self.model_name = f"{self.model_name}:latest"
                model_found = True
            
            if not model_found:
                print(f"⚠️  Model '{self.model_name}' not found")
                print(f"Available models: {model_names}")
                print(f"\nTo install: ollama pull {self.model_name}")
                raise ValueError(f"Model {self.model_name} not available")
            
            print(f"✓ Connected to Ollama with model: {self.model_name}")
            
        except requests.exceptions.ConnectionError:
            print("❌ Cannot connect to Ollama")
            print("Make sure Ollama is running: ollama serve")
            raise
    
    def generate_embedding(self, text: str) -> Optional[List[float]]:
        """
        Generate embedding for a text using Ollama
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector as list of floats
        """
        try:
            response = requests.post(
                self.embedding_endpoint,
                json={
                    "model": self.model_name,
                    "prompt": text
                }
            )
            
            if response.status_code == 200:
                embedding = response.json()['embedding']
                return embedding
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


class PodcastIndexerWithEmbeddings(PodcastIndexer):
    """Extended indexer with embedding support"""
    
    def __init__(self, db_path="podcast_index.db", embedding_model="nomic-embed-text:latest"):
        super().__init__(db_path)
        self.embedder = EmbeddingGenerator(embedding_model)
    
    def generate_chunk_embedding(self, chunk_id: int, content: str) -> bool:
        """
        Generate and store embedding for a chunk
        
        Args:
            chunk_id: Database ID of chunk
            content: Chunk text content
            
        Returns:
            Success boolean
        """
        embedding = self.embedder.generate_embedding(content)
        
        if embedding:
            cursor = self.conn.cursor()
            # Store as JSON array
            cursor.execute(
                "UPDATE chunks SET embedding = ? WHERE id = ?",
                (json.dumps(embedding), chunk_id)
            )
            self.conn.commit()
            return True
        return False
    
    def embed_podcast_chunks(self, podcast_id: int) -> int:
        """
        Generate embeddings for all chunks of a podcast
        
        Args:
            podcast_id: Database ID of podcast
            
        Returns:
            Number of chunks embedded
        """
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT id, content FROM chunks WHERE podcast_id = ? AND embedding IS NULL",
            (podcast_id,)
        )
        chunks = cursor.fetchall()
        
        embedded_count = 0
        for chunk_id, content in chunks:
            if self.generate_chunk_embedding(chunk_id, content):
                embedded_count += 1
                print(f"  Embedded chunk {embedded_count}/{len(chunks)}", end='\r')
        
        print(f"\n✓ Embedded {embedded_count} chunks")
        return embedded_count
    
    def test_embeddings(self):
        """Test embedding generation and similarity"""
        print("\n🧪 Testing Embedding Generation\n")
        
        # Test 1: Generate embeddings
        test_texts = [
            "Artificial intelligence and machine learning are transforming technology",
            "AI and ML are revolutionizing tech",
            "I love cooking pasta with tomatoes",
            "Consciousness is the hard problem of philosophy"
        ]
        
        embeddings = []
        for text in test_texts:
            emb = self.embedder.generate_embedding(text)
            if emb:
                embeddings.append(emb)
                print(f"✓ Generated embedding: {len(emb)} dimensions")
            else:
                print(f"❌ Failed to embed: {text}")
        
        # Test 2: Calculate similarities
        if len(embeddings) >= 4:
            print("\n📊 Similarity Scores:")
            print("(Higher = more similar, range: -1 to 1)")
            print(f"\nAI vs ML text: {self.embedder.cosine_similarity(embeddings[0], embeddings[1]):.3f}")
            print(f"AI vs Cooking: {self.embedder.cosine_similarity(embeddings[0], embeddings[2]):.3f}")
            print(f"AI vs Philosophy: {self.embedder.cosine_similarity(embeddings[0], embeddings[3]):.3f}")
        
        # Test 3: Check database storage
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
        embedded_chunks = cursor.fetchone()[0]
        print(f"\n📦 Database: {embedded_chunks} chunks have embeddings")
    
    def get_embedding_stats(self) -> Dict:
        """Get statistics about embeddings"""
        cursor = self.conn.cursor()
        
        # Count embedded chunks
        cursor.execute("SELECT COUNT(*) FROM chunks WHERE embedding IS NOT NULL")
        embedded = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM chunks")
        total = cursor.fetchone()[0]
        
        # Get embedding dimension
        cursor.execute("SELECT embedding FROM chunks WHERE embedding IS NOT NULL LIMIT 1")
        sample = cursor.fetchone()
        dim = len(json.loads(sample[0])) if sample else 0
        
        return {
            'total_chunks': total,
            'embedded_chunks': embedded,
            'embedding_dimension': dim,
            'percentage': (embedded / total * 100) if total > 0 else 0
        }


def test_stage2():
    """Test Stage 2 functionality"""
    print("🚀 Stage 2: Testing Embedding Generation\n")
    
    # Initialize
    indexer = PodcastIndexerWithEmbeddings("test_embeddings.db")
    
    # Run embedding tests
    indexer.test_embeddings()
    
    # Clean up
    indexer.close()
    if os.path.exists("test_embeddings.db"):
        os.remove("test_embeddings.db")
    
    print("\n✅ Stage 2 tests completed!")
    print("\nNext steps:")
    print("1. Make sure ollama is running: ollama serve")
    print("2. Pull embedding model: ollama pull nomic-embed-text")
    print("3. Run on your indexed podcasts to generate embeddings")
    print("\nNote: If you get model not found errors, try using 'nomic-embed-text:latest'")


def embed_all_podcasts():
    """Helper function to embed all indexed podcasts"""
    indexer = PodcastIndexerWithEmbeddings()
    
    cursor = indexer.conn.cursor()
    cursor.execute("SELECT id, filename FROM podcasts")
    podcasts = cursor.fetchall()
    
    print(f"Found {len(podcasts)} podcasts to embed\n")
    
    for podcast_id, filename in podcasts:
        print(f"Embedding: {filename}")
        indexer.embed_podcast_chunks(podcast_id)
    
    stats = indexer.get_embedding_stats()
    print(f"\n📊 Final Stats:")
    print(f"  Total chunks: {stats['total_chunks']}")
    print(f"  Embedded: {stats['embedded_chunks']} ({stats['percentage']:.1f}%)")
    print(f"  Dimensions: {stats['embedding_dimension']}")
    
    indexer.close()


if __name__ == "__main__":
    # Run tests
    test_stage2()
    
    # Uncomment to embed all your podcasts:
    # embed_all_podcasts()