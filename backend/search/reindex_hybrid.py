#!/usr/bin/env python3
"""
Re-index all podcast chunks into the new Pinecone hybrid index.

Reads chunk texts from SQLite, fits BM25 on the corpus, generates
dense (Ollama) + sparse (BM25) vectors for each chunk, and upserts
to the 'podcast-hybrid' Pinecone index.

Usage (from project root):
    python backend/search/reindex_hybrid.py
"""

import json
import os
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np
import requests
from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec
from pinecone_text.sparse import BM25Encoder

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

DB_PATH = PROJECT_ROOT / "data" / "databases" / "podcast_index_v2.db"
BM25_PARAMS_PATH = PROJECT_ROOT / "data" / "bm25_params.json"

INDEX_NAME = "podcast-hybrid"
DIMENSION = 768
CLOUD = "aws"
REGION = "us-east-1"

OLLAMA_URL = "http://localhost:11434/api/embeddings"
EMBEDDING_MODEL = "nomic-embed-text:latest"


def generate_embedding(text: str) -> list[float] | None:
    try:
        resp = requests.post(OLLAMA_URL, json={"model": EMBEDDING_MODEL, "prompt": text})
        if resp.status_code == 200:
            vec = np.array(resp.json()["embedding"])
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec.tolist()
    except Exception as e:
        print(f"  Embedding error: {e}")
    return None


def main():
    if not DB_PATH.exists():
        print(f"❌ Database not found at {DB_PATH}")
        sys.exit(1)

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        print("❌ PINECONE_API_KEY not set in .env")
        sys.exit(1)

    # Connect to SQLite
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()

    # Load all podcasts and chunks
    cursor.execute("SELECT id, title, filename FROM podcasts ORDER BY id")
    podcasts = {row[0]: {"title": row[1], "filename": row[2]} for row in cursor.fetchall()}

    cursor.execute("""
        SELECT c.podcast_id, c.chunk_index, c.content, p.title, p.filename
        FROM chunks c JOIN podcasts p ON p.id = c.podcast_id
        ORDER BY c.podcast_id, c.chunk_index
    """)
    all_chunks = cursor.fetchall()
    conn.close()

    print(f"Found {len(podcasts)} podcasts, {len(all_chunks)} chunks\n")

    # Step 1: Fit BM25 on all title-prepended chunk texts
    print("Step 1: Fitting BM25 encoder on corpus...")
    corpus = [f"{row[3]} | {row[2]}" for row in all_chunks]

    bm25 = BM25Encoder()
    bm25.fit(corpus)

    BM25_PARAMS_PATH.parent.mkdir(parents=True, exist_ok=True)
    bm25.dump(str(BM25_PARAMS_PATH))
    print(f"  ✓ BM25 fitted on {len(corpus)} documents, saved to {BM25_PARAMS_PATH}\n")

    # Step 2: Create/connect to Pinecone hybrid index
    print("Step 2: Setting up Pinecone hybrid index...")
    pc = Pinecone(api_key=api_key)

    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"  Creating index '{INDEX_NAME}' (dotproduct, {DIMENSION}d)...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="dotproduct",
            spec=ServerlessSpec(cloud=CLOUD, region=REGION),
        )
        print(f"  ✓ Index created")
    else:
        print(f"  ✓ Index '{INDEX_NAME}' already exists")

    index = pc.Index(INDEX_NAME)
    pre_stats = index.describe_index_stats()
    print(f"  Current vectors: {pre_stats.total_vector_count}\n")

    # Step 3: Generate and upsert hybrid vectors
    print("Step 3: Generating and upserting hybrid vectors...")
    start_time = time.time()

    vectors_to_upsert = []
    total = len(all_chunks)

    for i, (pid, chunk_idx, content, title, filename) in enumerate(all_chunks):
        chunk_text = f"{title} | {content}"

        dense_vec = generate_embedding(chunk_text)
        if not dense_vec:
            print(f"  ⚠️  Skipping chunk {pid}_{chunk_idx}: embedding failed")
            continue

        sparse_vec = bm25.encode_documents(chunk_text)

        vectors_to_upsert.append({
            "id": f"{pid}_chunk_{chunk_idx}",
            "values": dense_vec,
            "sparse_values": sparse_vec,
            "metadata": {
                "podcast_id": pid,
                "title": title,
                "filename": filename,
                "chunk_index": chunk_idx,
            },
        })

        # Batch upsert every 100 vectors
        if len(vectors_to_upsert) >= 100:
            index.upsert(vectors=vectors_to_upsert)
            vectors_to_upsert = []

        print(f"  [{i+1:4d}/{total}] podcast {pid} chunk {chunk_idx}", end="\r")

    # Upsert remaining
    if vectors_to_upsert:
        index.upsert(vectors=vectors_to_upsert)

    elapsed = time.time() - start_time
    print(f"\n\n✅ Re-indexing complete in {elapsed:.1f}s")

    post_stats = index.describe_index_stats()
    print(f"   Pinecone now has {post_stats.total_vector_count} hybrid vectors")


if __name__ == "__main__":
    main()
