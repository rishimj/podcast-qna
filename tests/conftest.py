import sys

import pytest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for path in (ROOT / "backend", ROOT / "backend" / "data_collection"):
    sys.path.insert(0, str(path))


@pytest.fixture(autouse=True)
def isolated_usage_db(monkeypatch, tmp_path):
    """Keep spend records and rate-limit counts out of the real llm_usage.db."""
    import search.claude_llm as claude_llm
    monkeypatch.setattr(claude_llm, "USAGE_DB_PATH", tmp_path / "llm_usage.db")
