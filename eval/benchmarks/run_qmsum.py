#!/usr/bin/env python3
"""
Benchmark episode Q&A (and episode search) on QMSum.

QMSum (Zhong et al., NAACL 2021) pairs 35 test meeting transcripts (product
design, academic, and parliamentary meetings) with 244 human-written specific
questions. Each question has a reference answer and the transcript turns an
annotator marked as relevant. Each meeting stands in for an episode.

For every question this measures:
  - Episode search: rank of the right meeting in search_two_tier() (Hit@1/5, MRR)
  - Passage retrieval: share of the annotated span covered by the 5 chunks
    that search_chunks_for_podcast() hands the RAG graph
  - Answer quality of run_corrective_rag(), and of the full-transcript
    fallback node as a no-retrieval baseline: ROUGE-1/2/L against the reference
    (QMSum's official metric) and a 1-5 correctness grade from a stronger
    Claude model that sees the reference answer

Usage (from project root, with Ollama running):
    bash eval/benchmarks/download.sh
    python eval/benchmarks/run_qmsum.py [--limit N] [--workers 6]
"""

import argparse
import json
import re
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from rouge_score import rouge_scorer

import harness
from search import corrective_rag
from search.claude_llm import ClaudeLLM

JUDGE_MODEL = "claude-sonnet-5"

JUDGE_PROMPT = """You are grading an answer to a question about a meeting. A human annotator wrote the reference answer after reading the full transcript.

Grade how well the candidate answer conveys the reference answer's key content:
5 = covers all key points, nothing contradicts the reference
4 = covers most key points, nothing important is wrong
3 = covers some key points, or mixes correct and incorrect content
2 = mostly misses the key points or is too vague to be useful
1 = wrong, contradicts the reference, or says the information is not available

Ignore length, style, and quoting. Extra correct detail is fine.

QUESTION: {question}

REFERENCE ANSWER: {reference}

CANDIDATE ANSWER: {candidate}

Reply with ONLY JSON: {{"score": <1-5>, "reason": "<one sentence>"}}"""


def domain_of(meeting):
    speakers = {t["speaker"] for t in meeting["meeting_transcripts"]}
    if any("Project Manager" in s or "Marketing" in s for s in speakers):
        return "product design (AMI)"
    if any(s.startswith(("Grad", "Professor", "PhD", "Postdoc")) for s in speakers):
        return "academic (ICSI)"
    return "parliament"


def load_meetings():
    meetings = [json.loads(line) for line in open(harness.DATA_DIR / "qmsum_test.jsonl")]
    docs, turn_word_ranges = [], []
    for i, m in enumerate(meetings, 1):
        lines, ranges, pos = [], [], 0
        for turn in m["meeting_transcripts"]:
            line = f"{turn['speaker']}: {turn['content']}"
            n = len(line.split())
            lines.append(line)
            ranges.append((pos, pos + n))
            pos += n
        docs.append({"title": f"QMSum meeting {i}", "content": "\n".join(lines)})
        turn_word_ranges.append(ranges)
    return meetings, docs, turn_word_ranges


def span_coverage(chunk_indices, gold_spans, turn_ranges, n_words, size=500, overlap=100):
    """Share of the annotated span's words that fall inside the retrieved chunks."""
    step = size - overlap  # chunk_text: chunk c covers words [c*step, c*step + size)
    gold = set()
    for start, end in gold_spans:
        s, e = int(start), min(int(end), len(turn_ranges) - 1)
        gold.update(range(turn_ranges[s][0], turn_ranges[e][1]))
    if not gold:
        return None
    got = set()
    for c in chunk_indices:
        got.update(range(c * step, min(c * step + size, n_words)))
    return len(gold & got) / len(gold)


def summarize(rows):
    n = len(rows)
    ranks = [r["search_rank"] for r in rows]
    cov = [r["span_coverage"] for r in rows if r["span_coverage"] is not None]
    summary = {
        "questions": n,
        "episode_search": {
            "hit@1": round(sum(r == 1 for r in ranks) / n, 3),
            "hit@5": round(sum(r is not None for r in ranks) / n, 3),
            "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
        },
        "passage_retrieval": {
            "mean_span_coverage": round(sum(cov) / len(cov), 3),
            "any_overlap": round(sum(c > 0 for c in cov) / len(cov), 3),
        },
        "rag_fallback_rate": round(sum(r["rag_used_fallback"] for r in rows) / n, 3),
    }
    for name in ("rag", "full_transcript"):
        grades = [r[f"{name}_judge"]["score"] for r in rows if r[f"{name}_judge"].get("score")]
        summary[name] = {
            **{k: round(100 * sum(r[f"{name}_rouge"][k] for r in rows) / n, 2)
               for k in ("rouge1", "rouge2", "rougeL")},
            "judge_mean_1to5": round(sum(grades) / len(grades), 2),
            "judge_4_or_5": round(sum(g >= 4 for g in grades) / len(grades), 3),
        }
    return summary


def judge(llm, question, reference, candidate):
    reply = llm.invoke(
        JUDGE_PROMPT.format(question=question, reference=reference, candidate=candidate),
        max_tokens=300, effort="low", thinking=False, purpose="benchmark_judge",
    )
    match = re.search(r"\{.*\}", reply, re.DOTALL)
    return json.loads(match.group(0)) if match else {"score": None, "reason": reply}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only the first N questions")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--search-only", action="store_true",
                        help="redo only the episode-search ranks in results/qmsum.json (no Claude calls)")
    args = parser.parse_args()
    if args.search_only:
        return rerun_search_only()

    meetings, docs, turn_ranges = load_meetings()
    search = harness.build_search(docs, "qmsum_test")
    answer_llm = ClaudeLLM(purpose="benchmark")
    judge_llm = ClaudeLLM(model=JUDGE_MODEL, purpose="benchmark_judge")
    corrective_rag.init_rag_resources(search, answer_llm)
    scorer = rouge_scorer.RougeScorer(["rouge1", "rouge2", "rougeL"], use_stemmer=True)

    items = [
        {"podcast_id": i, "domain": domain_of(m), **q}
        for i, m in enumerate(meetings, 1)
        for q in m["specific_query_list"]
    ][: args.limit]
    print(f"{len(items)} questions over {len(meetings)} meetings; answers by {answer_llm.model}, "
          f"graded by {JUDGE_MODEL}\n")

    def evaluate(item):
        pid, question, reference = item["podcast_id"], item["query"], item["answer"]
        title, content = search.get_full_transcript(pid)
        out = {k: item[k] for k in ("podcast_id", "domain", "query", "answer")}

        # Episode search across all 35 meetings
        ranked = [r["podcast_id"] for r in search.search_two_tier(question, top_k=5)]
        out["search_rank"] = ranked.index(pid) + 1 if pid in ranked else None

        # Passage retrieval inside the right meeting (what the RAG graph retrieves first)
        chunks = search.search_chunks_for_podcast(question, pid, top_k=corrective_rag.CHUNKS_TO_RETRIEVE)
        out["span_coverage"] = span_coverage(
            [c["chunk_index"] for c in chunks], item["relevant_text_span"],
            turn_ranges[pid - 1], len(content.split()),
        )

        # System answer: the production corrective RAG graph
        state = corrective_rag.run_corrective_rag(question, pid, title)
        out["rag_answer"] = state["generation"]
        out["rag_path"] = state["nodes_visited"]
        out["rag_used_fallback"] = state["used_fallback"]

        # Baseline: the graph's own full-transcript node, skipping retrieval
        baseline = corrective_rag.fallback({
            "podcast_id": pid, "original_query": question, "history": [], "nodes_visited": [],
        })
        out["full_transcript_answer"] = baseline["generation"]

        for name in ("rag", "full_transcript"):
            answer = out[f"{name}_answer"]
            rouge = scorer.score(reference, answer)
            out[f"{name}_rouge"] = {k: round(v.fmeasure, 4) for k, v in rouge.items()}
            out[f"{name}_judge"] = judge(judge_llm, question, reference, answer)
        return out

    results, errors = [], []
    start = time.time()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(evaluate, item) for item in items]
        for i, (item, future) in enumerate(zip(items, futures), 1):
            try:
                results.append(future.result())
            except Exception as e:  # keep going; report at the end
                errors.append({"query": item["query"], "error": repr(e)})
            if i % 20 == 0:
                print(f"  {i}/{len(items)} questions  (Claude spend so far ${harness.SPEND['usd']:.2f})")

    by_domain = defaultdict(list)
    for r in results:
        by_domain[r["domain"]].append(r)
    output = {
        "dataset": "QMSum test (specific queries)",
        "answer_model": answer_llm.model,
        "judge_model": JUDGE_MODEL,
        "overall": summarize(results),
        "by_domain": {d: summarize(rows) for d, rows in sorted(by_domain.items())},
        "rerank_calls": harness.RERANK["calls"],
        "rerank_failures": harness.RERANK["failures"],
        "claude_spend_usd": round(harness.SPEND["usd"], 2),
        "claude_calls": harness.SPEND["calls"],
        "elapsed_seconds": round(time.time() - start, 1),
        "errors": errors,
        "results": results,
    }
    harness.save_results("qmsum" if args.limit is None else f"qmsum_limit{args.limit}", output)

    o = output["overall"]
    print(f"\nQMSum test, {o['questions']} questions ({len(errors)} errors)")
    print(f"  Episode search   Hit@1 {o['episode_search']['hit@1']:.1%}  Hit@5 {o['episode_search']['hit@5']:.1%}  "
          f"MRR {o['episode_search']['mrr']:.3f}")
    print(f"  Passage recall   {o['passage_retrieval']['mean_span_coverage']:.1%} of annotated span covered; "
          f"{o['passage_retrieval']['any_overlap']:.1%} of questions retrieve some of it")
    for name, label in (("rag", "Corrective RAG"), ("full_transcript", "Full transcript")):
        m = o[name]
        print(f"  {label:16s} R-1 {m['rouge1']:.2f}  R-2 {m['rouge2']:.2f}  R-L {m['rougeL']:.2f}  "
              f"judge {m['judge_mean_1to5']:.2f}/5  ({m['judge_4_or_5']:.1%} graded 4-5)")
    print(f"  Claude spend ${output['claude_spend_usd']:.2f} over {output['claude_calls']} calls; "
          f"rerank failures {output['rerank_failures']}")


def rerun_search_only():
    """Recompute episode-search ranks one query at a time and update qmsum.json."""
    path = harness.RESULTS_DIR / "qmsum.json"
    output = json.load(open(path))
    _, docs, _ = load_meetings()
    search = harness.build_search(docs, "qmsum_test")
    for i, r in enumerate(output["results"], 1):
        ranked = [x["podcast_id"] for x in search.search_two_tier(r["query"], top_k=5)]
        r["search_rank"] = ranked.index(r["podcast_id"]) + 1 if r["podcast_id"] in ranked else None
        if i % 50 == 0:
            print(f"  {i}/{len(output['results'])}")
    by_domain = defaultdict(list)
    for r in output["results"]:
        by_domain[r["domain"]].append(r)
    output["overall"] = summarize(output["results"])
    output["by_domain"] = {d: summarize(rows) for d, rows in sorted(by_domain.items())}
    output["rerank_calls"] = harness.RERANK["calls"]
    output["rerank_failures"] = harness.RERANK["failures"]
    output["search_rerun"] = "episode search recomputed sequentially after rate-limited rerank calls"
    json.dump(output, open(path, "w"), indent=2)
    e = output["overall"]["episode_search"]
    print(f"Episode search  Hit@1 {e['hit@1']:.1%}  Hit@5 {e['hit@5']:.1%}  MRR {e['mrr']:.3f}  "
          f"(rerank failures {harness.RERANK['failures']})")


if __name__ == "__main__":
    main()
