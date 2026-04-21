#!/usr/bin/env python3
"""
Podcast Hybrid Search System

Two-stage retrieval pipeline:
  1. Hybrid search (dense semantic + sparse BM25 keyword) via Pinecone
  2. Cross-encoder reranking via Pinecone's pinecone-rerank-v0
  3. Aggregate to podcast-level results

Dense embeddings from Ollama (nomic-embed-text), sparse vectors from BM25Encoder.
"""

import sqlite3
import os
import json
import numpy as np
from typing import List, Dict, Optional
from pathlib import Path
import requests
import re
import glob
import time
from collections import defaultdict

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder
from pinecone_text.hybrid import hybrid_convex_scale

load_dotenv(Path(__file__).parent.parent.parent / '.env')

PINECONE_INDEX_NAME = "podcast-hybrid"
PINECONE_DIMENSION = 768
PINECONE_CLOUD = "aws"
PINECONE_REGION = "us-east-1"

PROJECT_ROOT = Path(__file__).parent.parent.parent
BM25_PARAMS_PATH = PROJECT_ROOT / "data" / "bm25_params.json"


class PodcastTwoTierSearch:
    def __init__(self, db_path=None, embedding_model="nomic-embed-text:latest"):
        if db_path is None:
            db_path = str(PROJECT_ROOT / "data" / "databases" / "podcast_index_v2.db")
        self.db_path = db_path
        self.embedding_model = embedding_model
        self.conn = None
        self.base_url = "http://localhost:11434"
        self.embedding_endpoint = f"{self.base_url}/api/embeddings"

        self.alpha = 0.7  # dense vs sparse blend (1.0 = pure semantic)
        self.retrieval_top_k = 30  # candidates from hybrid search
        self.rerank_top_n = 10  # results after reranking

        self.setup_database()
        self._test_ollama_connection()
        self._init_pinecone()
        self._load_bm25()

    # ========== PINECONE SETUP ==========

    def _init_pinecone(self):
        """Initialize Pinecone client and ensure the hybrid index exists."""
        api_key = os.getenv("PINECONE_API_KEY")
        if not api_key:
            raise ValueError(
                "PINECONE_API_KEY not set. Add it to .env at the project root."
            )

        self.pc = Pinecone(api_key=api_key)

        existing_indexes = [idx.name for idx in self.pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing_indexes:
            print(f"Creating Pinecone hybrid index '{PINECONE_INDEX_NAME}' ...")
            self.pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=PINECONE_DIMENSION,
                metric="dotproduct",
                spec=ServerlessSpec(cloud=PINECONE_CLOUD, region=PINECONE_REGION),
            )
            print(f"✓ Pinecone hybrid index created")

        self.pinecone_index = self.pc.Index(PINECONE_INDEX_NAME)
        stats = self.pinecone_index.describe_index_stats()
        print(f"✓ Connected to Pinecone index '{PINECONE_INDEX_NAME}' "
              f"({stats.total_vector_count} vectors)")

    # ========== BM25 SETUP ==========

    def _load_bm25(self):
        """Load fitted BM25 encoder from disk, or use default."""
        if BM25_PARAMS_PATH.exists():
            self.bm25 = BM25Encoder()
            self.bm25.load(str(BM25_PARAMS_PATH))
            print(f"✓ BM25 encoder loaded from {BM25_PARAMS_PATH}")
        else:
            self.bm25 = BM25Encoder.default()
            print("⚠️  Using default BM25 encoder (not fitted on corpus)")

    def fit_bm25(self):
        """Fit BM25 encoder on all chunk texts and save params."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT p.title, c.content FROM chunks c JOIN podcasts p ON p.id = c.podcast_id")
        rows = cursor.fetchall()

        corpus = [f"{title} | {content}" for title, content in rows]
        print(f"Fitting BM25 on {len(corpus)} chunks...")

        self.bm25 = BM25Encoder()
        self.bm25.fit(corpus)

        BM25_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
        self.bm25.dump(str(BM25_PARAMS_PATH))
        print(f"✓ BM25 encoder fitted and saved to {BM25_PARAMS_PATH}")

    # ========== DATABASE SETUP ==========

    def setup_database(self):
        """Create database schema for text content and metadata."""
        self.conn = sqlite3.connect(self.db_path)
        cursor = self.conn.cursor()

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

        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_chunks_podcast
            ON chunks(podcast_id)
        ''')

        self.conn.commit()
        print(f"✓ Database initialized at {self.db_path}")

    # ========== EMBEDDING GENERATION ==========

    def _test_ollama_connection(self):
        """Test if Ollama is running and model is available."""
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
        """Generate dense embedding for text using Ollama."""
        try:
            response = requests.post(
                self.embedding_endpoint,
                json={"model": self.embedding_model, "prompt": text}
            )
            if response.status_code == 200:
                embedding = response.json()['embedding']
                # L2-normalize for dotproduct metric
                vec = np.array(embedding)
                norm = np.linalg.norm(vec)
                if norm > 0:
                    vec = vec / norm
                return vec.tolist()
            else:
                print(f"❌ Error generating embedding: {response.status_code}")
                return None
        except Exception as e:
            print(f"❌ Embedding error: {e}")
            return None

    # ========== INDEXING ==========

    def extract_title(self, filename):
        """Extract clean title from filename."""
        name = os.path.splitext(filename)[0]
        for pattern in [r'\d{4}[-_]\d{2}[-_]\d{2}', r'\d{8}',
                        r'\d{2}[-_]\d{2}[-_]\d{4}', r'\d{4}[-_]\d{1,2}[-_]\d{1,2}']:
            name = re.sub(pattern, '', name)
        name = name.replace('_', ' ').replace('-', ' ')
        return ' '.join(name.split()).strip()

    def chunk_text(self, text: str, chunk_size: int = 500, overlap: int = 100) -> List[Dict]:
        """Split text into overlapping chunks."""
        words = text.split()
        chunks = []

        if len(words) <= chunk_size:
            chunks.append({
                'content': text, 'char_start': 0,
                'char_end': len(text), 'chunk_index': 0
            })
            return chunks

        step = chunk_size - overlap
        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size]
            chunk_text = ' '.join(chunk_words)
            char_start = 0 if i == 0 else len(' '.join(words[:i])) + 1
            char_end = char_start + len(chunk_text)

            chunks.append({
                'content': chunk_text, 'char_start': char_start,
                'char_end': char_end, 'chunk_index': len(chunks)
            })

            if i + chunk_size >= len(words):
                break

        return chunks

    def index_podcast_enhanced(self, filepath: str) -> bool:
        """Index podcast: text to SQLite, hybrid vectors to Pinecone."""
        try:
            filename = os.path.basename(filepath)
            title = self.extract_title(filename)

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            if not content:
                print(f"⚠️  Empty transcript: {filename}")
                return False

            cursor = self.conn.cursor()
            cursor.execute("SELECT id FROM podcasts WHERE filename = ?", (filename,))
            existing = cursor.fetchone()

            if existing:
                podcast_id = existing[0]
                try:
                    fetch_result = self.pinecone_index.fetch(ids=[f"{podcast_id}_chunk_0"])
                    if fetch_result.vectors:
                        print(f"⚠️  Already indexed: {filename}")
                        return False
                except Exception:
                    pass
            else:
                cursor.execute('''
                    INSERT INTO podcasts (filename, title, content, char_count)
                    VALUES (?, ?, ?, ?)
                ''', (filename, title, content, len(content)))
                podcast_id = cursor.lastrowid

            print(f"📝 Processing {filename}")

            if not existing:
                chunks = self.chunk_text(content)
            else:
                cursor.execute(
                    "SELECT chunk_index, content FROM chunks WHERE podcast_id = ? ORDER BY chunk_index",
                    (podcast_id,)
                )
                chunks = [{'chunk_index': r[0], 'content': r[1]} for r in cursor.fetchall()]

            print(f"  Processing {len(chunks)} chunks...")
            pinecone_vectors = []

            for i, chunk in enumerate(chunks):
                chunk_text_for_embed = f"{title} | {chunk['content']}"

                dense_vec = self.generate_embedding(chunk_text_for_embed)
                sparse_vec = self.bm25.encode_documents(chunk_text_for_embed)

                if dense_vec:
                    pinecone_vectors.append({
                        "id": f"{podcast_id}_chunk_{chunk['chunk_index']}",
                        "values": dense_vec,
                        "sparse_values": sparse_vec,
                        "metadata": {
                            "podcast_id": podcast_id,
                            "title": title,
                            "filename": filename,
                            "chunk_index": chunk['chunk_index'],
                        },
                    })

                if not existing and 'char_start' in chunk:
                    cursor.execute('''
                        INSERT INTO chunks
                        (podcast_id, chunk_index, content, char_start, char_end)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (podcast_id, chunk['chunk_index'], chunk['content'],
                          chunk.get('char_start', 0), chunk.get('char_end', 0)))

                print(f"    Chunk {i+1}/{len(chunks)}", end='\r')

            for batch_start in range(0, len(pinecone_vectors), 100):
                batch = pinecone_vectors[batch_start:batch_start + 100]
                self.pinecone_index.upsert(vectors=batch)

            self.conn.commit()
            print(f"\n✓ Indexed: {filename} ({len(pinecone_vectors)} hybrid vectors)")
            return True

        except Exception as e:
            print(f"❌ Error indexing {filepath}: {e}")
            import traceback
            traceback.print_exc()
            self.conn.rollback()
            return False

    # ========== HYBRID SEARCH ==========

    def search_two_tier(self, query: str, top_k: int = 5) -> List[Dict]:
        """Two-stage hybrid search: retrieve with dense+sparse, rerank, aggregate."""
        # Stage 0: Generate query vectors
        dense_vec = self.generate_embedding(query)
        if not dense_vec:
            print("❌ Failed to generate query embedding")
            return []

        sparse_vec = self.bm25.encode_queries(query)

        # Apply alpha weighting
        scaled_dense, scaled_sparse = hybrid_convex_scale(
            dense_vec, sparse_vec, alpha=self.alpha
        )

        # Stage 1: Hybrid retrieval
        results = self.pinecone_index.query(
            vector=scaled_dense,
            sparse_vector=scaled_sparse,
            top_k=self.retrieval_top_k,
            include_metadata=True,
        )

        if not results.matches:
            return []

        # Collect chunk texts for reranking
        chunk_texts = []
        chunk_meta = []
        for match in results.matches:
            pid = int(match.metadata["podcast_id"])
            chunk_idx = int(match.metadata.get("chunk_index", 0))

            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT content FROM chunks WHERE podcast_id = ? AND chunk_index = ?",
                (pid, chunk_idx)
            )
            row = cursor.fetchone()
            text = row[0] if row else ""

            title = match.metadata.get("title", "")
            chunk_texts.append(f"{title} | {text}")
            chunk_meta.append({
                "podcast_id": pid,
                "title": title,
                "filename": match.metadata.get("filename", ""),
                "hybrid_score": match.score,
            })

        # Stage 2: Rerank
        try:
            rerank_result = self.pc.inference.rerank(
                model="pinecone-rerank-v0",
                query=query,
                documents=chunk_texts,
                top_n=self.rerank_top_n,
                return_documents=False,
                parameters={"truncate": "END"},
            )

            reranked = []
            for item in rerank_result.data:
                meta = chunk_meta[item.index]
                reranked.append({**meta, "rerank_score": item.score})
        except Exception as e:
            print(f"⚠️  Reranker failed ({e}), falling back to hybrid scores")
            reranked = [{**m, "rerank_score": m["hybrid_score"]}
                        for m in chunk_meta[:self.rerank_top_n]]

        # Stage 3: Aggregate to podcast level (best score per podcast)
        best_per_podcast: Dict[int, Dict] = {}
        for item in reranked:
            pid = item["podcast_id"]
            if pid not in best_per_podcast or item["rerank_score"] > best_per_podcast[pid]["rerank_score"]:
                best_per_podcast[pid] = item

        # Build final results
        podcast_results = []
        for pid, item in best_per_podcast.items():
            cursor = self.conn.cursor()
            cursor.execute("SELECT content FROM podcasts WHERE id = ?", (pid,))
            row = cursor.fetchone()
            content_preview = ""
            if row:
                content_preview = row[0][:200] + '...' if len(row[0]) > 200 else row[0]

            podcast_results.append({
                'podcast_id': pid,
                'filename': item['filename'],
                'title': item['title'],
                'title_similarity': item.get('hybrid_score', 0.0),
                'intro_similarity': 0.0,
                'chunks_similarity': item.get('hybrid_score', 0.0),
                'outro_similarity': 0.0,
                'final_score': item['rerank_score'],
                'content_preview': content_preview,
            })

        podcast_results.sort(key=lambda x: x['final_score'], reverse=True)
        return podcast_results[:top_k]

    def find_best_podcast_two_tier(self, query: str) -> Optional[Dict]:
        """Find single best matching podcast."""
        results = self.search_two_tier(query, top_k=1)
        return results[0] if results else None

    def search_chunks_for_podcast(self, query: str, podcast_id: int, top_k: int = 5) -> List[Dict]:
        """Retrieve the most relevant chunks from a specific podcast.

        Uses the same hybrid dense+sparse search as search_two_tier but filters
        results to a single podcast via Pinecone metadata filter. Returns
        chunk-level results (not aggregated to podcast level).
        """
        dense_vec = self.generate_embedding(query)
        if not dense_vec:
            return []

        sparse_vec = self.bm25.encode_queries(query)
        scaled_dense, scaled_sparse = hybrid_convex_scale(
            dense_vec, sparse_vec, alpha=self.alpha
        )

        results = self.pinecone_index.query(
            vector=scaled_dense,
            sparse_vector=scaled_sparse,
            top_k=top_k,
            include_metadata=True,
            filter={"podcast_id": {"$eq": podcast_id}},
        )

        if not results.matches:
            return []

        chunks = []
        cursor = self.conn.cursor()
        for match in results.matches:
            chunk_idx = int(match.metadata.get("chunk_index", 0))
            cursor.execute(
                "SELECT content FROM chunks WHERE podcast_id = ? AND chunk_index = ?",
                (podcast_id, chunk_idx),
            )
            row = cursor.fetchone()
            chunks.append({
                "chunk_index": chunk_idx,
                "text": row[0] if row else "",
                "score": match.score,
                "title": match.metadata.get("title", ""),
            })

        return chunks

    def get_full_transcript(self, podcast_id: int) -> tuple[str, str]:
        """Return (title, full_content) for a podcast."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT title, content FROM podcasts WHERE id = ?", (podcast_id,))
        row = cursor.fetchone()
        if row:
            return row[0], row[1]
        return "", ""

    # ========== UTILITY FUNCTIONS ==========

    def index_all_podcasts_enhanced(self, folder="transcripts"):
        """Index all podcasts with hybrid vectors."""
        if not os.path.exists(folder):
            print(f"❌ Folder {folder} not found")
            return

        files = glob.glob(os.path.join(folder, "*.txt"))
        if not files:
            print(f"❌ No .txt files found in {folder}")
            return

        print(f"Found {len(files)} transcripts to index\n")

        start_time = time.time()
        success_count = 0
        for filepath in files:
            if self.index_podcast_enhanced(filepath):
                success_count += 1

        elapsed = time.time() - start_time
        print(f"\n✅ Indexed {success_count}/{len(files)} podcasts in {elapsed:.1f} seconds")

        stats = self.get_stats()
        print(f"📊 Total: {stats['podcasts']} podcasts, {stats['chunks']} chunks")
        print(f"🎯 Pinecone vectors: {stats['pinecone_vectors']}")

    def get_stats(self) -> Dict:
        """Get statistics from SQLite and Pinecone."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM podcasts")
        podcast_count = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM chunks")
        chunk_count = cursor.fetchone()[0]

        pinecone_vectors = 0
        try:
            pinecone_stats = self.pinecone_index.describe_index_stats()
            pinecone_vectors = pinecone_stats.total_vector_count
        except Exception:
            pass

        return {
            'podcasts': podcast_count,
            'title_embeddings': pinecone_vectors,
            'chunks': chunk_count,
            'embedded_chunks': pinecone_vectors,
            'pinecone_vectors': pinecone_vectors,
        }

    def debug_search(self, query: str):
        """Debug search to see scoring breakdown."""
        results = self.search_two_tier(query, top_k=5)
        print(f"\n🔍 Debug Search: '{query}'\n")
        for i, result in enumerate(results, 1):
            print(f"{i}. {result['title']} ({result['filename']})")
            print(f"   Hybrid score: {result['chunks_similarity']:.4f}")
            print(f"   Rerank score: {result['final_score']:.4f}\n")

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()


def upgrade_existing_database():
    """Upgrade existing database with enhanced embeddings."""
    print("🚀 Upgrading Podcast Search System\n")
    search = PodcastTwoTierSearch()

    choice = input("Re-index all podcasts? (y/n): ").strip().lower()
    if choice == 'y':
        search.fit_bm25()
        search.index_all_podcasts_enhanced("transcripts")

    print("\n🧪 Testing search:")
    test_query = input("Enter a test search query: ").strip()
    if test_query:
        search.debug_search(test_query)

    search.close()


if __name__ == "__main__":
    upgrade_existing_database()
