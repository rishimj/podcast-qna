#!/usr/bin/env python3
"""
Benchmark episode search on BEIR retrieval datasets.

Each BEIR document stands in for an episode. For every test query the
production search_two_tier() returns the top 10 documents, scored with
nDCG@10 and Recall@10 against the human relevance labels. The same index is
also queried without the reranker and with the dense or BM25 half alone, so
the table shows what each stage of the pipeline adds.

Usage (from project root, with Ollama running):
    bash eval/benchmarks/download.sh
    python eval/benchmarks/run_beir.py scifact nfcorpus
"""

import csv
import json
import math
import sys
import time
from collections import defaultdict

from pinecone_text.hybrid import hybrid_convex_scale

import harness

# BM25 nDCG@10 from the BEIR paper (Thakur et al., 2021, Table 2)
PUBLISHED_BM25 = {"scifact": 0.665, "nfcorpus": 0.325}


def load_beir(name):
    root = harness.DATA_DIR / name
    corpus = [json.loads(line) for line in open(root / "corpus.jsonl")]
    queries = {q["_id"]: q["text"] for q in map(json.loads, open(root / "queries.jsonl"))}
    qrels = defaultdict(dict)
    with open(root / "qrels" / "test.tsv") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            if int(row["score"]) > 0:
                qrels[row["query-id"]][row["corpus-id"]] = int(row["score"])
    return corpus, {qid: queries[qid] for qid in qrels}, qrels


def ndcg_at_k(ranked, rels, k=10):
    dcg = sum(rels.get(d, 0) / math.log2(i + 2) for i, d in enumerate(ranked[:k]))
    ideal = sorted(rels.values(), reverse=True)[:k]
    idcg = sum(r / math.log2(i + 2) for i, r in enumerate(ideal))
    return dcg / idcg if idcg else 0.0


def recall_at_k(ranked, rels, k=10):
    return len(set(ranked[:k]) & set(rels)) / len(rels)


def first_stage(search, query, alpha, k=10):
    """Hybrid retrieval only (no reranker), aggregated to best chunk per document."""
    dense, sparse = hybrid_convex_scale(
        search.generate_embedding(query), search.bm25.encode_queries(query), alpha=alpha
    )
    matches = search.pinecone_index.query(vector=dense, sparse_vector=sparse, top_k=100).matches
    ranked = []
    for m in matches:
        pid = m.metadata["podcast_id"]
        if pid not in ranked:
            ranked.append(pid)
    return ranked[:k]


def run(name):
    corpus, queries, qrels = load_beir(name)
    docs = [{"title": d.get("title", ""), "content": d["text"]} for d in corpus]
    doc_ids = [d["_id"] for d in corpus]  # podcast_id i -> doc_ids[i - 1]
    search = harness.build_search(docs, f"beir_{name}")

    systems = {
        "BM25 only": lambda q: first_stage(search, q, alpha=0.0),
        "Dense only (nomic-embed-text)": lambda q: first_stage(search, q, alpha=1.0),
        f"Hybrid (alpha={search.alpha})": lambda q: first_stage(search, q, alpha=search.alpha),
        "Full pipeline (hybrid + rerank)": lambda q: [
            r["podcast_id"] for r in search.search_two_tier(q, top_k=10)
        ],
    }

    rerank_failures_before = harness.RERANK["failures"]
    scores = {s: {"ndcg@10": [], "recall@10": []} for s in systems}
    start = time.time()
    for i, (qid, text) in enumerate(queries.items(), 1):
        for system, fn in systems.items():
            ranked = [doc_ids[pid - 1] for pid in fn(text)]
            scores[system]["ndcg@10"].append(ndcg_at_k(ranked, qrels[qid]))
            scores[system]["recall@10"].append(recall_at_k(ranked, qrels[qid]))
        if i % 50 == 0:
            print(f"  {i}/{len(queries)} queries")

    summary = {
        system: {metric: round(sum(v) / len(v), 4) for metric, v in m.items()}
        for system, m in scores.items()
    }
    failures = harness.RERANK["failures"] - rerank_failures_before
    result = {
        "dataset": f"BEIR/{name}",
        "documents": len(docs),
        "queries": len(queries),
        "published_bm25_ndcg@10": PUBLISHED_BM25.get(name),
        "systems": summary,
        "rerank_failures": failures,
        "elapsed_seconds": round(time.time() - start, 1),
    }
    harness.save_results(f"beir_{name}", result)

    print(f"\nBEIR/{name}: {len(docs)} docs, {len(queries)} queries")
    print(f"  {'system':36s} nDCG@10  Recall@10")
    for system, m in summary.items():
        print(f"  {system:36s} {m['ndcg@10']:.3f}    {m['recall@10']:.3f}")
    print(f"  {'Published BM25 (BEIR paper)':36s} {PUBLISHED_BM25.get(name, float('nan')):.3f}")
    if failures:
        print(f"  WARNING: {failures} rerank calls failed and fell back to hybrid scores")
    print()


if __name__ == "__main__":
    for dataset in sys.argv[1:] or ["scifact", "nfcorpus"]:
        run(dataset)
