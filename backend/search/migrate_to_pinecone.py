#!/usr/bin/env python3
"""
One-time migration: push existing embeddings from SQLite into Pinecone.

Run from the project root:
    python backend/search/migrate_to_pinecone.py

This reads the JSON-serialized embeddings already stored in the SQLite
database (title_embedding, intro_embedding, outro_embedding on podcasts;
embedding on chunks) and upserts them into Pinecone so you don't need
to re-generate them with Ollama.
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv
from pinecone import Pinecone, ServerlessSpec

PROJECT_ROOT = Path(__file__).parent.parent.parent
load_dotenv(PROJECT_ROOT / ".env")

INDEX_NAME = "podcast-embeddings"
DIMENSION = 768
CLOUD = "aws"
REGION = "us-east-1"


def main():
    db_path = PROJECT_ROOT / "data" / "databases" / "podcast_index_v2.db"
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        sys.exit(1)

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        print("❌ PINECONE_API_KEY not set in .env")
        sys.exit(1)

    pc = Pinecone(api_key=api_key)

    existing = [idx.name for idx in pc.list_indexes()]
    if INDEX_NAME not in existing:
        print(f"Creating Pinecone index '{INDEX_NAME}' ...")
        pc.create_index(
            name=INDEX_NAME,
            dimension=DIMENSION,
            metric="cosine",
            spec=ServerlessSpec(cloud=CLOUD, region=REGION),
        )

    index = pc.Index(INDEX_NAME)
    pre_stats = index.describe_index_stats()
    print(f"Pinecone index '{INDEX_NAME}': {pre_stats.total_vector_count} vectors before migration\n")

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    # Migrate podcast-level embeddings (title, intro, outro)
    cursor.execute("""
        SELECT id, filename, title, title_embedding, intro_embedding, outro_embedding
        FROM podcasts
        WHERE title_embedding IS NOT NULL
           OR intro_embedding IS NOT NULL
           OR outro_embedding IS NOT NULL
    """)

    vectors_to_upsert = []
    podcast_count = 0

    for row in cursor.fetchall():
        pid, filename, title, title_emb_json, intro_emb_json, outro_emb_json = row
        meta_base = {"podcast_id": pid, "title": title, "filename": filename}
        podcast_count += 1

        if title_emb_json:
            vectors_to_upsert.append({
                "id": f"{pid}_title",
                "values": json.loads(title_emb_json),
                "metadata": {**meta_base, "type": "title"},
            })
        if intro_emb_json:
            vectors_to_upsert.append({
                "id": f"{pid}_intro",
                "values": json.loads(intro_emb_json),
                "metadata": {**meta_base, "type": "intro"},
            })
        if outro_emb_json:
            vectors_to_upsert.append({
                "id": f"{pid}_outro",
                "values": json.loads(outro_emb_json),
                "metadata": {**meta_base, "type": "outro"},
            })

    print(f"Found {podcast_count} podcasts with embeddings in SQLite")

    # Migrate chunk embeddings
    cursor.execute("""
        SELECT c.podcast_id, c.chunk_index, c.embedding, p.title, p.filename
        FROM chunks c
        JOIN podcasts p ON p.id = c.podcast_id
        WHERE c.embedding IS NOT NULL
    """)

    chunk_count = 0
    for row in cursor.fetchall():
        pid, chunk_idx, emb_json, title, filename = row
        chunk_count += 1
        vectors_to_upsert.append({
            "id": f"{pid}_chunk_{chunk_idx}",
            "values": json.loads(emb_json),
            "metadata": {
                "podcast_id": pid,
                "title": title,
                "filename": filename,
                "type": "chunk",
                "chunk_index": chunk_idx,
            },
        })

    conn.close()
    print(f"Found {chunk_count} chunks with embeddings in SQLite")
    print(f"Total vectors to upsert: {len(vectors_to_upsert)}\n")

    if not vectors_to_upsert:
        print("Nothing to migrate.")
        return

    # Batch upsert (Pinecone max 100 per call)
    total = len(vectors_to_upsert)
    for i in range(0, total, 100):
        batch = vectors_to_upsert[i : i + 100]
        index.upsert(vectors=batch)
        print(f"  Upserted {min(i + 100, total)}/{total} vectors", end="\r")

    print()

    post_stats = index.describe_index_stats()
    print(f"\n✅ Migration complete!")
    print(f"   Pinecone now has {post_stats.total_vector_count} vectors")


if __name__ == "__main__":
    main()
