# Public benchmark results

Run 2026-09-23 with the production search and RAG code (`harness.py` swaps only the
Pinecone vector index for an exact in-memory one; embeddings, BM25, alpha, reranker,
episode aggregation and the corrective RAG graph are unchanged). Answers by
claude-haiku-4-5, graded by claude-sonnet-5. Raw per-query output is in `results/`.

## Episode search: BEIR SciFact (5,183 docs, 300 human-labelled queries)

| System | nDCG@10 | Recall@10 |
| --- | --- | --- |
| Published BM25 (BEIR paper, Thakur et al. 2021) | 0.665 | – |
| BM25 only (our encoder) | 0.674 | 0.807 |
| Dense only (nomic-embed-text) | 0.669 | 0.808 |
| Hybrid, alpha 0.7 | 0.717 | 0.850 |
| **Full pipeline (hybrid + pinecone-rerank-v0)** | **0.774** | **0.883** |

Our BM25-only row reproduces the published baseline (0.674 vs 0.665), which checks the
harness. Every stage adds accuracy; the full pipeline is +16% nDCG@10 over published BM25.
All 300 rerank calls succeeded.

NFCorpus was not completed: the Pinecone org hit its 500 rerank requests/month limit.

## Meeting transcripts: QMSum test (35 meetings, 244 human-written questions)

Each meeting stands in for an episode (transcripts average 9,500 words).

**Episode search** (find the right meeting among 35)

| Domain | Questions | Hit@1 | Hit@5 | MRR |
| --- | --- | --- | --- | --- |
| Parliament committees | 66 | 90.9% | 98.5% | 0.947 |
| Academic (ICSI) | 49 | 77.6% | 91.8% | 0.838 |
| Product design (AMI) | 129 | 34.9% | 71.3% | 0.481 |
| All | 244 | 58.6% | 82.8% | 0.679 |

AMI's 20 meetings are all the same team designing the same remote control, so questions
like "what did the group discuss about the buttons?" are genuinely ambiguous across them.
23 of 244 rerank calls hit the monthly limit and used hybrid scores instead.

**Passage retrieval inside the episode:** the 5 chunks the RAG graph retrieves cover
64% of the annotator-marked relevant passage on average, and touch it for 88.5% of questions.

**Answer quality**

| | ROUGE-1 | ROUGE-2 | ROUGE-L | Judge (1-5) | Graded 4-5 |
| --- | --- | --- | --- | --- | --- |
| Corrective RAG (production chat path) | 26.70 | 8.16 | 16.56 | 2.91 | 39.3% |
| Whole transcript to the same model (no retrieval) | 27.52 | 9.52 | 17.11 | 3.56 | 56.1% |

The retrieval path currently answers worse than sending the whole transcript.

## Problems the benchmark surfaced in `backend/search/corrective_rag.py`

1. **The hallucination check almost never passes a first answer.** Of the 177 answers generated
   from chunks, 174 went `generate → generate`; the second is accepted only because of the 2-attempt cap.
   The checker sees `doc["text"][:400]`, the first ~70 words of each 500-word chunk, so
   it cannot find the support. Every answer is generated twice and the check filters nothing.
2. **The relevance grader also sees only the first 400 characters** of each chunk. It
   marked all 5 chunks irrelevant for 83 questions (34%), even though retrieval touched
   the annotated passage 88.5% of the time. Those questions went through a rewrite, and 67
   ended in the full-transcript fallback. 36 grader replies also hit `max_tokens=50`.

Claude spend for the QMSum run: $7.56 over 1,737 calls (not counted in `llm_usage.db`).

## Reproduce

```bash
bash eval/benchmarks/download.sh
python eval/benchmarks/run_beir.py scifact nfcorpus   # ~300 rerank calls per dataset
python eval/benchmarks/run_qmsum.py                   # 244 rerank calls, ~$8 of Claude
```

Each run spends Pinecone rerank requests from the same monthly quota as the live site.
