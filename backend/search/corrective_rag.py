#!/usr/bin/env python3
"""
Corrective RAG pipeline using LangGraph.

Flow:
  1. Retrieve top chunks from the selected podcast via hybrid search
  2. Grade each chunk for relevance (LLM judge)
  3. If no relevant chunks found, rewrite the query and retry (max 1 rewrite)
  4. If still no relevant chunks, fall back to full transcript
  5. Generate answer from relevant context
  6. Check answer is grounded in the context (hallucination guard)
"""

import logging
from typing import TypedDict

from langchain_ollama import OllamaLLM
from langgraph.graph import StateGraph, START, END

from search.podcast_semantic_search_complete import PodcastTwoTierSearch

logger = logging.getLogger(__name__)

MAX_RETRIES = 1
CHUNKS_TO_RETRIEVE = 5


class RAGState(TypedDict):
    query: str
    original_query: str
    podcast_id: int
    podcast_title: str
    documents: list[dict]
    relevant_docs: list[dict]
    generation: str
    retries: int
    history: list[dict]
    generation_attempts: int
    used_fallback: bool
    nodes_visited: list[str]


# ---------------------------------------------------------------------------
# Shared resources — initialised once per process via init_rag_resources()
# ---------------------------------------------------------------------------

_search: PodcastTwoTierSearch | None = None
_llm: OllamaLLM | None = None


def init_rag_resources(search: PodcastTwoTierSearch, llm: OllamaLLM):
    global _search, _llm
    _search = search
    _llm = llm


def _get_search() -> PodcastTwoTierSearch:
    if _search is None:
        raise RuntimeError("Call init_rag_resources() before running the graph")
    return _search


def _get_llm() -> OllamaLLM:
    if _llm is None:
        raise RuntimeError("Call init_rag_resources() before running the graph")
    return _llm


# ---------------------------------------------------------------------------
# Graph nodes
# ---------------------------------------------------------------------------

def retrieve(state: RAGState) -> dict:
    """Retrieve top chunks from the selected podcast."""
    search = _get_search()
    docs = search.search_chunks_for_podcast(
        query=state["query"],
        podcast_id=state["podcast_id"],
        top_k=CHUNKS_TO_RETRIEVE,
    )
    return {
        "documents": docs,
        "nodes_visited": state.get("nodes_visited", []) + ["retrieve"],
    }


def grade_documents(state: RAGState) -> dict:
    """Grade all chunks for relevance in a single LLM call."""
    llm = _get_llm()
    query = state["original_query"]
    docs = state["documents"]

    if not docs:
        return {
            "relevant_docs": [],
            "nodes_visited": state.get("nodes_visited", []) + ["grade"],
        }

    numbered = "\n\n".join(
        f"[{i+1}] {doc['text'][:400]}" for i, doc in enumerate(docs)
    )
    prompt = (
        f"You are a relevance grader. For each numbered document below, decide "
        f"if it helps answer the question. Reply with ONLY a comma-separated "
        f"list of the relevant document numbers (e.g. \"1,3,5\"). "
        f"If none are relevant, reply \"none\".\n\n"
        f"Question: {query}\n\n"
        f"Documents:\n{numbered}"
    )
    verdict = llm.invoke(prompt).strip().lower()

    relevant = []
    if verdict != "none":
        for token in verdict.replace(" ", "").split(","):
            try:
                idx = int(token) - 1
                if 0 <= idx < len(docs):
                    relevant.append(docs[idx])
            except ValueError:
                continue

    return {
        "relevant_docs": relevant,
        "nodes_visited": state.get("nodes_visited", []) + ["grade"],
    }


def decide_next(state: RAGState) -> str:
    """Route: generate if we have relevant docs, else rewrite or fallback."""
    if state["relevant_docs"]:
        return "generate"
    if state["retries"] < MAX_RETRIES:
        return "rewrite"
    return "fallback"


def rewrite_query(state: RAGState) -> dict:
    """LLM rewrites the query to improve retrieval."""
    llm = _get_llm()
    prompt = (
        f"The following search query did not retrieve useful results from a "
        f"podcast transcript. Rewrite it to be more specific and likely to "
        f"match relevant passages. Return ONLY the rewritten query, nothing else.\n\n"
        f"Original query: {state['original_query']}"
    )
    new_query = llm.invoke(prompt).strip().strip('"')
    return {
        "query": new_query,
        "retries": state["retries"] + 1,
        "nodes_visited": state.get("nodes_visited", []) + ["rewrite"],
    }


def generate(state: RAGState) -> dict:
    """Generate an answer grounded in the relevant chunks."""
    llm = _get_llm()

    context_parts = []
    for i, doc in enumerate(state["relevant_docs"], 1):
        context_parts.append(f"[Chunk {i}]\n{doc['text']}")
    context = "\n\n".join(context_parts)

    history_str = ""
    for h in (state.get("history") or [])[-5:]:
        history_str += f"Human: {h['human']}\nAssistant: {h['assistant']}\n\n"

    prompt = (
        f"You are a helpful assistant answering questions about the podcast "
        f"\"{state['podcast_title']}\".\n\n"
        f"INSTRUCTIONS:\n"
        f"- Answer based ONLY on the transcript excerpts below.\n"
        f"- If the excerpts do not contain enough information, say so.\n"
        f"- Quote relevant parts when possible.\n\n"
        f"TRANSCRIPT EXCERPTS:\n{context}\n\n"
        f"CONVERSATION HISTORY:\n{history_str}\n"
        f"QUESTION: {state['original_query']}\n\n"
        f"Answer:"
    )
    answer = llm.invoke(prompt)

    return {
        "generation": answer,
        "generation_attempts": state.get("generation_attempts", 0) + 1,
        "nodes_visited": state.get("nodes_visited", []) + ["generate"],
    }


def check_hallucination(state: RAGState) -> str:
    """Verify the answer is grounded in the provided chunks."""
    if state.get("generation_attempts", 0) >= 2:
        return "accept"

    llm = _get_llm()
    excerpts = "\n".join(doc["text"][:400] for doc in state["relevant_docs"])

    prompt = (
        f"You are a hallucination grader. Is the following answer fully "
        f"supported by the provided transcript excerpts? Answer ONLY 'yes' or 'no'.\n\n"
        f"Transcript excerpts:\n{excerpts}\n\n"
        f"Answer:\n{state['generation']}\n\n"
        f"Supported?"
    )
    verdict = llm.invoke(prompt).strip().lower()
    if verdict.startswith("yes"):
        return "accept"
    return "regenerate"


def fallback(state: RAGState) -> dict:
    """Fall back to full-transcript generation when chunk retrieval fails."""
    llm = _get_llm()
    search = _get_search()
    title, content = search.get_full_transcript(state["podcast_id"])

    history_str = ""
    for h in (state.get("history") or [])[-5:]:
        history_str += f"Human: {h['human']}\nAssistant: {h['assistant']}\n\n"

    prompt = (
        f"You are a helpful assistant for answering questions about podcasts "
        f"based on their transcripts.\n\n"
        f"IMPORTANT INSTRUCTIONS:\n"
        f"- Answer questions based ONLY on the podcast transcript provided below\n"
        f"- If information is not in the transcript, say "
        f"\"I don't find that information in the transcript\"\n"
        f"- Quote relevant parts from the transcript when answering\n"
        f"- The podcast is titled: {title}\n\n"
        f"PODCAST TRANSCRIPT:\n{content}\n\n"
        f"CONVERSATION HISTORY:\n{history_str}\n"
        f"CURRENT QUESTION: {state['original_query']}\n\n"
        f"Please answer the question based on the podcast transcript above."
    )
    answer = llm.invoke(prompt)

    return {
        "generation": answer,
        "used_fallback": True,
        "nodes_visited": state.get("nodes_visited", []) + ["fallback"],
    }


# ---------------------------------------------------------------------------
# Build the graph
# ---------------------------------------------------------------------------

def _build_graph() -> StateGraph:
    g = StateGraph(RAGState)

    g.add_node("retrieve", retrieve)
    g.add_node("grade", grade_documents)
    g.add_node("rewrite", rewrite_query)
    g.add_node("generate", generate)
    g.add_node("fallback", fallback)

    g.add_edge(START, "retrieve")
    g.add_edge("retrieve", "grade")
    g.add_conditional_edges("grade", decide_next, {
        "generate": "generate",
        "rewrite": "rewrite",
        "fallback": "fallback",
    })
    g.add_edge("rewrite", "retrieve")
    g.add_conditional_edges("generate", check_hallucination, {
        "accept": END,
        "regenerate": "generate",
    })
    g.add_edge("fallback", END)

    return g


_compiled_graph = None


def _get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = _build_graph().compile()
    return _compiled_graph


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_corrective_rag(
    query: str,
    podcast_id: int,
    podcast_title: str = "",
    history: list[dict] | None = None,
) -> dict:
    """Run the corrective RAG graph and return the final state.

    Returns a dict with at least:
      - generation: the answer string
      - used_fallback: bool
      - nodes_visited: list of node names visited
    """
    if not podcast_title:
        search = _get_search()
        title, _ = search.get_full_transcript(podcast_id)
        podcast_title = title

    initial_state: RAGState = {
        "query": query,
        "original_query": query,
        "podcast_id": podcast_id,
        "podcast_title": podcast_title,
        "documents": [],
        "relevant_docs": [],
        "generation": "",
        "retries": 0,
        "history": history or [],
        "generation_attempts": 0,
        "used_fallback": False,
        "nodes_visited": [],
    }

    graph = _get_graph()
    final_state = graph.invoke(initial_state)
    return final_state
