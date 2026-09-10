"""ClaudeLLM request shaping and cost accounting, with the API client faked out."""
import types

import pytest

import search.claude_llm as cl


def usage(inp=0, out=0, cache_write=0, cache_read=0):
    return types.SimpleNamespace(input_tokens=inp, output_tokens=out,
                                 cache_creation_input_tokens=cache_write,
                                 cache_read_input_tokens=cache_read)


def test_haiku_cost_per_million_tokens():
    assert cl.estimate_cost("claude-haiku-4-5", usage(1_000_000, 1_000_000)) == pytest.approx(6.0)


def test_cache_write_and_read_multipliers():
    # $1/M input on Haiku: writes bill at 1.25x, reads at 0.1x
    cost = cl.estimate_cost("claude-haiku-4-5", usage(cache_write=1_000_000, cache_read=1_000_000))
    assert cost == pytest.approx(1.35)


def test_unpriced_model_falls_back_to_default_rates():
    assert cl.estimate_cost("claude-future-model", usage(1_000_000)) == pytest.approx(1.0)


class FakeMessages:
    def __init__(self, stop_reason="end_turn"):
        self.calls = []
        self.stop_reason = stop_reason

    def create(self, **params):
        self.calls.append(params)
        return types.SimpleNamespace(stop_reason=self.stop_reason, usage=usage(10, 5),
                                     content=[types.SimpleNamespace(type="text", text="ok")])


@pytest.fixture
def make_llm(monkeypatch, tmp_path):
    monkeypatch.setattr(cl, "USAGE_DB_PATH", tmp_path / "llm_usage.db")
    monkeypatch.setattr(cl, "load_project_env", lambda: None)

    def make(model, stop_reason="end_turn"):
        fake = FakeMessages(stop_reason)
        monkeypatch.setattr(cl.anthropic, "Anthropic", lambda: types.SimpleNamespace(messages=fake))
        return cl.ClaudeLLM(model=model), fake
    return make


def test_haiku_is_not_sent_effort_or_thinking(make_llm):
    # effort errors on Haiku 4.5, so these must be dropped even when requested
    llm, fake = make_llm("claude-haiku-4-5")
    assert llm.invoke("q", effort="low", thinking=False) == "ok"
    assert "output_config" not in fake.calls[0] and "thinking" not in fake.calls[0]


def test_newer_models_get_effort_and_can_disable_thinking(make_llm):
    llm, fake = make_llm("claude-sonnet-5")
    llm.invoke("q", effort="low", thinking=False)
    assert fake.calls[0]["output_config"] == {"effort": "low"}
    assert fake.calls[0]["thinking"] == {"type": "disabled"}


def test_thinking_is_left_to_the_model_default_when_enabled(make_llm):
    llm, fake = make_llm("claude-sonnet-5")
    llm.invoke("q")
    assert "thinking" not in fake.calls[0]


def test_every_call_is_recorded_for_the_cost_report(make_llm):
    llm, _ = make_llm("claude-haiku-4-5")
    llm.invoke("q", purpose="unit")
    rows = cl.connect_usage_db().execute(
        "SELECT model, purpose, input_tokens, output_tokens FROM llm_usage").fetchall()
    assert rows == [("claude-haiku-4-5", "unit", 10, 5)]


def test_refusal_raises_instead_of_returning_empty_text(make_llm):
    llm, _ = make_llm("claude-haiku-4-5", stop_reason="refusal")
    with pytest.raises(RuntimeError):
        llm.invoke("q")
