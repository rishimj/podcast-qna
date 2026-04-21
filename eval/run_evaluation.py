#!/usr/bin/env python3
"""
Run retrieval evaluation against the search system.

Loads eval_set.json, runs each query through PodcastTwoTierSearch,
and computes Hit@1, Hit@3, Hit@5, and MRR.

Usage (from project root):
    python eval/run_evaluation.py
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from search.podcast_semantic_search_complete import PodcastTwoTierSearch

EVAL_SET_PATH = Path(__file__).parent / "eval_set.json"
RESULTS_PATH = Path(__file__).parent / "eval_results.json"


def compute_metrics(per_query_results: list) -> dict:
    """Compute aggregate retrieval metrics."""
    total = len(per_query_results)
    if total == 0:
        return {}

    hit_at_1 = sum(1 for r in per_query_results if r["rank"] == 1) / total
    hit_at_3 = sum(1 for r in per_query_results if r["rank"] is not None and r["rank"] <= 3) / total
    hit_at_5 = sum(1 for r in per_query_results if r["rank"] is not None and r["rank"] <= 5) / total
    mrr = sum((1.0 / r["rank"]) for r in per_query_results if r["rank"] is not None) / total

    return {
        "total_queries": total,
        "hit_at_1": round(hit_at_1, 3),
        "hit_at_3": round(hit_at_3, 3),
        "hit_at_5": round(hit_at_5, 3),
        "mrr": round(mrr, 3),
    }


def main():
    if not EVAL_SET_PATH.exists():
        print(f"Eval set not found at {EVAL_SET_PATH}")
        print("Run generate_eval_set.py first.")
        sys.exit(1)

    with open(EVAL_SET_PATH) as f:
        eval_set = json.load(f)

    print(f"Loaded {len(eval_set)} eval queries\n")
    print("Initializing search system...")
    search = PodcastTwoTierSearch()
    print()

    per_query_results = []
    start_time = time.time()

    for i, item in enumerate(eval_set):
        query = item["query"]
        expected_id = item["expected_podcast_id"]

        results = search.search_two_tier(query, top_k=5)

        result_ids = [r["podcast_id"] for r in results]
        rank = None
        if expected_id in result_ids:
            rank = result_ids.index(expected_id) + 1

        score_at_rank = None
        if rank is not None:
            score_at_rank = results[rank - 1]["final_score"]

        per_query_results.append({
            "query": query,
            "query_type": item.get("query_type", "unknown"),
            "expected_podcast_id": expected_id,
            "podcast_title": item.get("podcast_title", ""),
            "rank": rank,
            "score_at_rank": round(score_at_rank, 4) if score_at_rank else None,
            "top_result_id": result_ids[0] if result_ids else None,
            "top_result_score": round(results[0]["final_score"], 4) if results else None,
        })

        status = f"rank={rank}" if rank else "MISS"
        print(f"  [{i+1:3d}/{len(eval_set)}] {status:8s} | {query[:60]}")

    elapsed = time.time() - start_time
    search.close()

    # Aggregate metrics
    overall = compute_metrics(per_query_results)

    # Per-type breakdown
    by_type = defaultdict(list)
    for r in per_query_results:
        by_type[r["query_type"]].append(r)
    type_metrics = {qt: compute_metrics(qs) for qt, qs in by_type.items()}

    # Find failures for inspection
    failures = [r for r in per_query_results if r["rank"] is None or r["rank"] > 1]

    output = {
        "overall": overall,
        "by_query_type": type_metrics,
        "elapsed_seconds": round(elapsed, 1),
        "failures": failures,
        "all_results": per_query_results,
    }

    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump(output, f, indent=2)

    # Print summary
    print("\n" + "=" * 60)
    print("RETRIEVAL EVALUATION RESULTS")
    print("=" * 60)
    print(f"  Queries:  {overall['total_queries']}")
    print(f"  Hit@1:    {overall['hit_at_1']:.1%}")
    print(f"  Hit@3:    {overall['hit_at_3']:.1%}")
    print(f"  Hit@5:    {overall['hit_at_5']:.1%}")
    print(f"  MRR:      {overall['mrr']:.3f}")
    print(f"  Time:     {elapsed:.1f}s ({elapsed/len(eval_set):.1f}s per query)")

    print(f"\nBy query type:")
    for qt, m in sorted(type_metrics.items()):
        print(f"  {qt:10s}  Hit@1={m['hit_at_1']:.1%}  Hit@3={m['hit_at_3']:.1%}  MRR={m['mrr']:.3f}  (n={m['total_queries']})")

    miss_count = sum(1 for r in per_query_results if r["rank"] is None)
    if miss_count:
        print(f"\nMisses (not in top 5): {miss_count}")
        for r in per_query_results:
            if r["rank"] is None:
                print(f"  - \"{r['query']}\" (expected: {r['podcast_title'][:50]})")

    print(f"\nFull results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
