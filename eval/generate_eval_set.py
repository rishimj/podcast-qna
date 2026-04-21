#!/usr/bin/env python3
"""
Generate an evaluation dataset for retrieval testing.

For each podcast in the database, uses llama3 via Ollama to generate
3-5 realistic search queries a user might type to find that episode.
Writes the result to eval_set.json.

Usage (from project root):
    python eval/generate_eval_set.py
"""

import json
import re
import sqlite3
import sys
from pathlib import Path

from langchain_ollama import OllamaLLM

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "databases" / "podcast_index_v2.db"
OUTPUT_PATH = Path(__file__).parent / "eval_set.json"

PROMPT_TEMPLATE = """You are helping build a test dataset for a podcast search engine.

Given the podcast title and a snippet of its transcript, generate exactly 5 search queries that a real user might type to find this specific episode. The queries should be short (3-10 words) and diverse:

1. A TOPIC query about the main subject matter
2. A PERSON query mentioning a guest, host, or person discussed
3. A CONCEPT query about a specific idea, technology, or argument from the episode
4. A CASUAL query — how a non-expert might search for this
5. A VAGUE query — a broader or more ambiguous phrasing that should still match this episode

PODCAST TITLE: {title}

TRANSCRIPT SNIPPET:
{snippet}

Respond with ONLY a JSON array of objects, no other text. Each object must have "query" and "query_type" fields. Example:
[
  {{"query": "container security with AI", "query_type": "topic"}},
  {{"query": "Amanda Saunders NVIDIA", "query_type": "person"}},
  {{"query": "agentic vulnerability scanning", "query_type": "concept"}},
  {{"query": "how to secure docker containers", "query_type": "casual"}},
  {{"query": "AI for devops security", "query_type": "vague"}}
]"""


def extract_json_array(text: str) -> list:
    """Extract a JSON array from LLM output, handling markdown fences."""
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        bracket_match = re.search(r"\[.*\]", text, re.DOTALL)
        if bracket_match:
            text = bracket_match.group(0)
    return json.loads(text)


def main():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}")
        sys.exit(1)

    llm = OllamaLLM(
        model="llama3",
        temperature=0.8,
        base_url="http://localhost:11434",
    )

    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, content FROM podcasts ORDER BY id")
    podcasts = cursor.fetchall()
    conn.close()

    print(f"Generating eval queries for {len(podcasts)} podcasts...\n")

    eval_set = []
    failures = 0

    for pid, title, content in podcasts:
        snippet = content[:2000]
        prompt = PROMPT_TEMPLATE.format(title=title, snippet=snippet)

        print(f"  [{pid:2d}/{len(podcasts)}] {title[:70]}...", end=" ", flush=True)

        try:
            response = llm.invoke(prompt)
            queries = extract_json_array(response)

            for q in queries:
                eval_set.append({
                    "query": q["query"],
                    "expected_podcast_id": pid,
                    "podcast_title": title,
                    "query_type": q.get("query_type", "unknown"),
                })

            print(f"-> {len(queries)} queries")

        except Exception as e:
            print(f"FAILED: {e}")
            failures += 1

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(eval_set, f, indent=2)

    print(f"\nDone! Generated {len(eval_set)} queries across {len(podcasts)} podcasts.")
    if failures:
        print(f"  ({failures} podcasts failed to generate queries)")
    print(f"Saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
