#!/usr/bin/env python3
"""
Claude client shared by chat, summaries, the CLI chatbot, and eval scripts.

ClaudeLLM.invoke(prompt) -> str mirrors the OllamaLLM interface it replaced.
Every call's token usage is priced and appended to data/databases/llm_usage.db,
which scripts/daily_cost_report.py reads to email a daily spend report.
"""

import logging
import os
import sqlite3
from datetime import datetime
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "env" / "config.env"
USAGE_DB_PATH = PROJECT_ROOT / "data" / "databases" / "llm_usage.db"

DEFAULT_MODEL = "claude-haiku-4-5"

# Haiku 4.5 predates the effort control and adaptive thinking (it runs without
# thinking unless given a budget), so those params are only sent to newer models.
MODELS_WITHOUT_EFFORT = {"claude-haiku-4-5"}

# USD per million tokens (input, output). Cache writes bill at 1.25x the input
# rate and cache reads at 0.1x.
PRICING = {
    "claude-sonnet-5": (2.00, 10.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-5": (5.00, 25.00),
}


def load_project_env():
    """Load config/env/config.env into os.environ, keeping any vars already set."""
    if not CONFIG_PATH.exists():
        return
    with open(CONFIG_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip())


def estimate_cost(model: str, usage) -> float:
    """Price one response's token usage in USD."""
    input_rate, output_rate = PRICING.get(model, PRICING[DEFAULT_MODEL])
    cache_write = usage.cache_creation_input_tokens or 0
    cache_read = usage.cache_read_input_tokens or 0
    return (
        usage.input_tokens * input_rate
        + cache_write * input_rate * 1.25
        + cache_read * input_rate * 0.10
        + usage.output_tokens * output_rate
    ) / 1_000_000


def connect_usage_db() -> sqlite3.Connection:
    """Open the usage database, creating the table on first use."""
    USAGE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(USAGE_DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,  -- local time; the report groups by local date
            model TEXT NOT NULL,
            purpose TEXT NOT NULL,
            input_tokens INTEGER NOT NULL,
            output_tokens INTEGER NOT NULL,
            cache_write_tokens INTEGER NOT NULL,
            cache_read_tokens INTEGER NOT NULL,
            cost_usd REAL NOT NULL
        )
    """)
    return conn


def record_usage(model: str, purpose: str, usage):
    """Append one call's usage. Bookkeeping failures never break a request."""
    try:
        conn = connect_usage_db()
        try:
            with conn:
                conn.execute(
                    "INSERT INTO llm_usage (created_at, model, purpose, input_tokens, "
                    "output_tokens, cache_write_tokens, cache_read_tokens, cost_usd) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        model,
                        purpose,
                        usage.input_tokens,
                        usage.output_tokens,
                        usage.cache_creation_input_tokens or 0,
                        usage.cache_read_input_tokens or 0,
                        estimate_cost(model, usage),
                    ),
                )
        finally:
            conn.close()
    except Exception as e:
        logger.error("Failed to record LLM usage: %s", e)


class ClaudeLLM:
    """Drop-in replacement for OllamaLLM: invoke(prompt) returns the reply text."""

    def __init__(self, model: str | None = None, purpose: str = "general"):
        load_project_env()
        self.model = model or os.getenv("CLAUDE_MODEL", DEFAULT_MODEL)
        if self.model not in PRICING:
            logger.warning("No pricing for %s; cost report will use %s rates", self.model, DEFAULT_MODEL)
        self.purpose = purpose
        self.client = anthropic.Anthropic()

    def invoke(
        self,
        prompt: str,
        *,
        system=None,
        max_tokens: int = 8000,
        effort: str = "medium",
        thinking: bool = True,
        purpose: str | None = None,
    ) -> str:
        """Send one user turn and return the concatenated text of the reply.

        Use thinking=False with a small max_tokens for short classifier-style
        answers (the RAG graders); leave it on for answers and summaries.
        effort and thinking are ignored on models in MODELS_WITHOUT_EFFORT.
        """
        purpose = purpose or self.purpose
        params = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            params["system"] = system
        if self.model not in MODELS_WITHOUT_EFFORT:
            params["output_config"] = {"effort": effort}
            if not thinking:
                params["thinking"] = {"type": "disabled"}

        response = self.client.messages.create(**params)
        record_usage(self.model, purpose, response.usage)

        if response.stop_reason == "refusal":
            raise RuntimeError("Claude declined to answer this request")
        if response.stop_reason == "max_tokens":
            logger.warning("Claude reply hit max_tokens=%d (%s)", max_tokens, purpose)
        return "".join(block.text for block in response.content if block.type == "text")
