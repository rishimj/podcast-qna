"""
Run the production search and RAG code against a public benchmark corpus.

build_search() returns a real PodcastTwoTierSearch whose Pinecone index is
swapped for LocalHybridIndex, an exact in-memory dot-product index with the
same query() interface. Everything else is the production code path:
chunk_text, the Ollama embeddings, the BM25 encoder (fitted on the benchmark
corpus, as fit_bm25 does for the podcast library), hybrid_convex_scale with the
production alpha, pinecone-rerank-v0, and the per-episode aggregation in
search_two_tier. Nothing is written to the production Pinecone index or SQLite
database, and Claude calls made here are not counted toward the live site's
daily spend cap.
"""

import hashlib
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402
from pinecone import Pinecone  # noqa: E402
from pinecone_text.sparse import BM25Encoder  # noqa: E402

import search.claude_llm as claude_llm  # noqa: E402
from search.podcast_semantic_search_complete import PodcastTwoTierSearch  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

DATA_DIR = PROJECT_ROOT / "data" / "benchmarks"
CACHE_DIR = DATA_DIR / "cache"
RESULTS_DIR = Path(__file__).parent / "results"


# ---------------------------------------------------------------------------
# Claude spend: tally locally instead of writing to llm_usage.db
# ---------------------------------------------------------------------------

SPEND = {"usd": 0.0, "calls": 0}


def _record_usage_locally(model, purpose, usage):
    SPEND["usd"] += claude_llm.estimate_cost(model, usage)
    SPEND["calls"] += 1


claude_llm.record_usage = _record_usage_locally


# ---------------------------------------------------------------------------
# Local stand-in for the Pinecone hybrid index
# ---------------------------------------------------------------------------

class LocalHybridIndex:
    """Exact dotproduct over dense + sparse vectors, like a Pinecone hybrid index."""

    def __init__(self, ids, metadata, dense, sparse):
        self.ids = ids
        self.metadata = metadata
        self.dense = np.asarray(dense, dtype=np.float32)
        self.podcast_ids = np.array([m["podcast_id"] for m in metadata])
        # Inverted index for the sparse half: term -> (rows, weights)
        postings = {}
        for row, vec in enumerate(sparse):
            for term, weight in zip(vec["indices"], vec["values"]):
                postings.setdefault(term, ([], []))
                postings[term][0].append(row)
                postings[term][1].append(weight)
        self.postings = {t: (np.array(r), np.array(w, dtype=np.float32)) for t, (r, w) in postings.items()}

    def scores(self, vector, sparse_vector):
        s = self.dense @ np.asarray(vector, dtype=np.float32)
        if sparse_vector:
            for term, weight in zip(sparse_vector["indices"], sparse_vector["values"]):
                if term in self.postings:
                    rows, weights = self.postings[term]
                    s[rows] += weights * weight
        return s

    def query(self, vector, sparse_vector=None, top_k=10, include_metadata=True, filter=None):
        s = self.scores(vector, sparse_vector)
        if filter:
            pid = filter["podcast_id"]["$eq"]
            s = np.where(self.podcast_ids == pid, s, -np.inf)
        top = np.argsort(-s)[:top_k]
        matches = [
            SimpleNamespace(id=self.ids[i], score=float(s[i]), metadata=self.metadata[i])
            for i in top if np.isfinite(s[i])
        ]
        return SimpleNamespace(matches=matches)


# ---------------------------------------------------------------------------
# Reranker accounting: retry rate limits, and count real failures, because
# search_two_tier silently falls back to hybrid scores when rerank raises.
# ---------------------------------------------------------------------------

RERANK = {"calls": 0, "failures": 0}


def _wrap_rerank(pc):
    original = pc.inference.rerank

    def rerank(*args, **kwargs):
        RERANK["calls"] += 1
        for attempt in range(8):
            try:
                return original(*args, **kwargs)
            except Exception as e:
                if "429" in str(e) and attempt < 7:
                    time.sleep(min(2 ** attempt, 60))
                    continue
                RERANK["failures"] += 1
                raise

    pc.inference.rerank = rerank


# ---------------------------------------------------------------------------
# Building a search system over a benchmark corpus
# ---------------------------------------------------------------------------

def _embed_all(search, texts, cache_name):
    """Embed texts with the production generate_embedding, cached on disk."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1("\x00".join(texts).encode()).hexdigest()[:12]
    path = CACHE_DIR / f"{cache_name}_{digest}.npy"
    if path.exists():
        return np.load(path)

    print(f"Embedding {len(texts)} chunks with {search.embedding_model} ...")
    done = [0]

    def embed(text):
        vec = search.generate_embedding(text)
        done[0] += 1
        if done[0] % 500 == 0:
            print(f"  {done[0]}/{len(texts)}")
        if vec is None:
            raise RuntimeError("Embedding failed; is Ollama running?")
        return vec

    with ThreadPoolExecutor(max_workers=8) as pool:
        vectors = np.array(list(pool.map(embed, texts)), dtype=np.float32)
    np.save(path, vectors)
    return vectors


def build_search(docs, cache_name):
    """Index docs ({"title", "content"} dicts; ids are 1-based list positions)."""
    with patch.object(PodcastTwoTierSearch, "_init_pinecone", lambda self: None), \
         patch.object(PodcastTwoTierSearch, "_load_bm25", lambda self: None):
        search = PodcastTwoTierSearch(db_path=":memory:")

    search.pc = Pinecone(api_key=os.environ["PINECONE_API_KEY"])
    _wrap_rerank(search.pc)

    cursor = search.conn.cursor()
    ids, metadata, texts = [], [], []
    for podcast_id, doc in enumerate(docs, start=1):
        filename = f"{cache_name}_{podcast_id}.txt"
        cursor.execute(
            "INSERT INTO podcasts (id, filename, title, content, char_count) VALUES (?, ?, ?, ?, ?)",
            (podcast_id, filename, doc["title"], doc["content"], len(doc["content"])),
        )
        # Same chunking and "title | chunk" text as index_podcast_enhanced
        for chunk in search.chunk_text(doc["content"]):
            cursor.execute(
                "INSERT INTO chunks (podcast_id, chunk_index, content, char_start, char_end) "
                "VALUES (?, ?, ?, ?, ?)",
                (podcast_id, chunk["chunk_index"], chunk["content"], chunk["char_start"], chunk["char_end"]),
            )
            ids.append(f"{podcast_id}_chunk_{chunk['chunk_index']}")
            metadata.append({
                "podcast_id": podcast_id,
                "title": doc["title"],
                "filename": filename,
                "chunk_index": chunk["chunk_index"],
            })
            texts.append(f"{doc['title']} | {chunk['content']}")
    search.conn.commit()

    # Same corpus fit_bm25 uses: every chunk as "title | content"
    search.bm25 = BM25Encoder()
    search.bm25.fit(texts)
    sparse = [search.bm25.encode_documents(t) for t in texts]
    dense = _embed_all(search, texts, cache_name)

    search.pinecone_index = LocalHybridIndex(ids, metadata, dense, sparse)
    print(f"Indexed {len(docs)} documents as {len(texts)} chunks\n")
    return search


def save_results(name, payload):
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    path = RESULTS_DIR / f"{name}.json"
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"Saved {path.relative_to(PROJECT_ROOT)}")
