"""The safeguards that make it safe to publish the site: every path that spends
money or sends mail is capped per IP, site-wide, and by recorded spend."""
from datetime import datetime, timedelta

import pytest

import search.claude_llm as claude_llm
from api.safeguards import Guard, Settings, remember_session


@pytest.fixture(autouse=True)
def usage_db(monkeypatch, tmp_path):
    """Point the usage/request-log database at a fresh temp file."""
    monkeypatch.setattr(claude_llm, "USAGE_DB_PATH", tmp_path / "llm_usage.db")


class Clock:
    def __init__(self, at=datetime(2026, 9, 10, 12, 0, 0)):
        self.at = at

    def __call__(self):
        return self.at

    def advance(self, **kwargs):
        self.at += timedelta(**kwargs)


def make_guard(**overrides):
    settings = Settings(
        daily_model_requests=5, ip_daily_model_requests=3, ip_burst_per_minute=100,
        daily_emails=2, ip_daily_emails=1, daily_budget_usd=1.0,
        weekly_budget_usd=0, monthly_budget_usd=0,
    )
    for name, value in overrides.items():
        setattr(settings, name, value)
    clock = Clock()
    return Guard(settings, now=clock), clock


def chat(guard, ip="1.1.1.1", path="/api/chat", **kwargs):
    return guard.check(ip=ip, method="POST", path=path, **kwargs)


def record_spend(cost_usd, when=datetime(2026, 9, 10, 11, 0, 0)):
    conn = claude_llm.connect_usage_db()
    with conn:
        conn.execute(
            "INSERT INTO llm_usage (created_at, model, purpose, input_tokens, output_tokens, "
            "cache_write_tokens, cache_read_tokens, cost_usd) VALUES (?, 'm', 'chat', 0, 0, 0, 0, ?)",
            (when.isoformat(timespec="seconds"), cost_usd),
        )
    conn.close()


def test_per_ip_daily_limit_then_others_still_allowed():
    guard, _ = make_guard()
    for _ in range(3):
        assert chat(guard) is None
    rejection = chat(guard)
    assert rejection.status == 429
    assert rejection.code == "ip_daily_limit"
    assert rejection.retry_after > 0
    assert chat(guard, ip="2.2.2.2") is None


def test_site_wide_daily_limit_blocks_every_ip():
    guard, _ = make_guard(ip_daily_model_requests=0)
    for i in range(5):
        assert chat(guard, ip=f"10.0.0.{i}") is None
    rejection = chat(guard, ip="10.0.0.99")
    assert rejection.status == 429
    assert rejection.code == "daily_limit"


def test_limits_reset_the_next_day():
    guard, clock = make_guard()
    for _ in range(3):
        chat(guard)
    assert chat(guard).code == "ip_daily_limit"
    clock.advance(days=1)
    assert chat(guard) is None


def test_counts_survive_a_restart():
    guard, clock = make_guard()
    for _ in range(3):
        chat(guard)
    fresh = Guard(guard.settings, now=clock)
    assert chat(fresh).code == "ip_daily_limit"


def test_rejected_requests_do_not_consume_quota_but_admitted_ones_do():
    guard, _ = make_guard(ip_daily_model_requests=1)
    assert chat(guard) is None
    for _ in range(3):
        assert chat(guard).code == "ip_daily_limit"
    # The site-wide budget of 5 was only charged once.
    for i in range(4):
        assert chat(guard, ip=f"3.3.3.{i}") is None
    assert chat(guard, ip="3.3.3.9").code == "daily_limit"


def test_email_has_its_own_tighter_caps():
    guard, _ = make_guard()
    email = "/api/summary/email"
    assert chat(guard, path=email) is None
    assert chat(guard, path=email).code == "ip_email_limit"
    assert chat(guard, ip="5.5.5.5", path=email) is None
    assert chat(guard, ip="6.6.6.6", path=email).code == "email_limit"
    # Plain chat is unaffected by the email caps.
    assert chat(guard) is None


def test_spend_cap_refuses_model_requests_once_reached():
    guard, _ = make_guard()
    record_spend(0.5)
    assert chat(guard) is None
    record_spend(0.5)
    rejection = chat(guard)
    assert rejection.status == 429
    assert rejection.code == "budget"


def test_yesterdays_spend_does_not_count_against_today():
    guard, _ = make_guard()
    record_spend(5.0, when=datetime(2026, 9, 9, 23, 0, 0))
    assert chat(guard) is None


def test_weekly_and_monthly_budgets():
    guard, _ = make_guard(daily_budget_usd=0, weekly_budget_usd=2.0)
    record_spend(1.5, when=datetime(2026, 9, 5, 9, 0, 0))
    record_spend(0.6, when=datetime(2026, 9, 8, 9, 0, 0))
    assert chat(guard).code == "budget"
    guard.settings.weekly_budget_usd = 0
    guard.settings.monthly_budget_usd = 2.0
    assert chat(guard).code == "budget"
    guard.settings.monthly_budget_usd = 3.0
    assert chat(guard) is None


def test_burst_limit_applies_to_every_endpoint(monkeypatch):
    guard, _ = make_guard(ip_burst_per_minute=2)
    assert guard.check(ip="7.7.7.7", method="GET", path="/api/stats") is None
    assert guard.check(ip="7.7.7.7", method="GET", path="/api/health") is None
    rejection = guard.check(ip="7.7.7.7", method="POST", path="/api/search")
    assert rejection.status == 429
    assert rejection.code == "burst"
    assert rejection.retry_after == 60
    # Another client is unaffected.
    assert guard.check(ip="8.8.8.8", method="GET", path="/api/stats") is None


def test_burst_window_slides(monkeypatch):
    import api.safeguards as safeguards
    ticks = [0.0]
    monkeypatch.setattr(safeguards.time, "monotonic", lambda: ticks[0])
    guard, _ = make_guard(ip_burst_per_minute=1)
    assert guard.check(ip="9.9.9.9", method="GET", path="/api/stats") is None
    assert guard.check(ip="9.9.9.9", method="GET", path="/api/stats").code == "burst"
    ticks[0] = 61.0
    assert guard.check(ip="9.9.9.9", method="GET", path="/api/stats") is None


def test_free_endpoints_never_count_against_model_caps():
    guard, _ = make_guard(ip_daily_model_requests=1)
    for _ in range(5):
        assert guard.check(ip="1.1.1.1", method="POST", path="/api/search") is None
        assert guard.check(ip="1.1.1.1", method="GET", path="/api/podcasts") is None
    assert chat(guard) is None


def test_oversized_body_is_a_413():
    guard, _ = make_guard(max_body_bytes=100)
    assert chat(guard, content_length="99") is None
    assert chat(guard, content_length="101").status == 413
    assert chat(guard, content_length="not-a-number").status == 413


def test_access_code_gates_posts_but_not_reads():
    guard, _ = make_guard(access_code="secret")
    assert chat(guard).status == 401
    assert chat(guard).code == "access_code_required"
    assert chat(guard, access_code="wrong").status == 401
    assert chat(guard, access_code="secret") is None
    assert guard.check(ip="1.1.1.1", method="GET", path="/api/stats") is None
    assert guard.check(ip="1.1.1.1", method="OPTIONS", path="/api/chat") is None


def test_zero_disables_a_limit():
    guard, _ = make_guard(daily_model_requests=0, ip_daily_model_requests=0,
                          daily_budget_usd=0, ip_burst_per_minute=0)
    record_spend(1000)
    for _ in range(50):
        assert chat(guard) is None


def test_forwarded_headers_only_trusted_behind_a_proxy():
    untrusting, _ = make_guard()
    headers = {"x-forwarded-for": "203.0.113.5, 10.0.0.1", "cf-connecting-ip": "203.0.113.9"}
    assert untrusting.client_ip(headers, "10.0.0.1") == "10.0.0.1"
    trusting, _ = make_guard(trust_proxy=True)
    assert trusting.client_ip(headers, "10.0.0.1") == "203.0.113.9"
    assert trusting.client_ip({"x-forwarded-for": "203.0.113.5, 10.0.0.1"}, "10.0.0.1") == "203.0.113.5"
    assert trusting.client_ip({}, None) == "unknown"


def test_settings_read_the_environment(monkeypatch):
    monkeypatch.setenv("DAILY_REQUEST_LIMIT", "12")
    monkeypatch.setenv("DAILY_BUDGET_LIMIT", "2.5")
    monkeypatch.setenv("ACCESS_CODE", " friends ")
    monkeypatch.setenv("TRUST_PROXY", "true")
    monkeypatch.setenv("IP_BURST_LIMIT", "garbage")
    settings = Settings.from_env()
    assert settings.daily_model_requests == 12
    assert settings.daily_budget_usd == 2.5
    assert settings.access_code == "friends"
    assert settings.trust_proxy is True
    assert settings.ip_burst_per_minute == Settings.ip_burst_per_minute


def test_sessions_are_capped_by_evicting_the_oldest():
    sessions = {}
    for i in range(5):
        remember_session(sessions, f"s{i}", {"podcast_id": i, "history": []}, max_sessions=3)
    assert list(sessions) == ["s2", "s3", "s4"]
    remember_session(sessions, "s2", sessions["s2"], max_sessions=3)
    assert len(sessions) == 3


# ── Through the API ────────────────────────────────────────────────────

@pytest.fixture
def client(monkeypatch, tmp_path):
    import sqlite3
    import api.controller as controller
    from test_api_errors import ASGIClient  # works with any Starlette/httpx pairing

    db = tmp_path / "podcasts.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE podcasts (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO podcasts VALUES (1, 'Known episode')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(controller, "DB_PATH", db)
    for name in ("llm", "summarization_service", "email_service"):
        monkeypatch.setattr(controller, name, object())
    monkeypatch.setattr(controller, "run_corrective_rag",
                        lambda **kwargs: {"generation": "an answer"})
    # Fresh, small limits for every test regardless of config.env.
    monkeypatch.setattr(controller.guard, "settings", Settings(
        daily_model_requests=0, ip_daily_model_requests=2, ip_burst_per_minute=0,
        daily_emails=0, ip_daily_emails=0, daily_budget_usd=0,
    ))
    monkeypatch.setattr(controller.guard, "_burst", {})
    return ASGIClient(controller.app)


CHAT = {"podcast_id": 1, "message": "hi"}


def test_api_returns_429_with_retry_after_and_cors_headers(client):
    headers = {"Origin": "http://localhost:8080"}
    assert client.post("/api/chat", json=CHAT, headers=headers).status_code == 200
    assert client.post("/api/chat", json=CHAT, headers=headers).status_code == 200
    response = client.post("/api/chat", json=CHAT, headers=headers)
    assert response.status_code == 429
    assert response.json()["code"] == "ip_daily_limit"
    assert "come back tomorrow" in response.json()["error"]
    assert int(response.headers["retry-after"]) > 0
    # The browser must be allowed to read the rejection, not see a CORS failure.
    assert response.headers["access-control-allow-origin"] in ("*", "http://localhost:8080")


def test_rejected_requests_never_reach_the_model(client, monkeypatch):
    import api.controller as controller
    client.post("/api/chat", json=CHAT)
    client.post("/api/chat", json=CHAT)
    monkeypatch.setattr(controller, "run_corrective_rag",
                        lambda **kwargs: pytest.fail("RAG graph must not run"))
    assert client.post("/api/chat", json=CHAT).status_code == 429


def test_access_code_via_api(client):
    import api.controller as controller
    controller.guard.settings.access_code = "friends"
    response = client.post("/api/chat", json=CHAT)
    assert response.status_code == 401
    assert response.json()["code"] == "access_code_required"
    assert client.post("/api/chat", json=CHAT, headers={"X-Access-Code": "friends"}).status_code == 200
    assert client.get("/api/chat/session/nope").status_code == 404  # reads stay open


def test_oversized_inputs_are_400s_without_a_model_call(client, monkeypatch):
    import api.controller as controller
    monkeypatch.setattr(controller, "run_corrective_rag",
                        lambda **kwargs: pytest.fail("RAG graph must not run"))
    response = client.post("/api/chat", json={"podcast_id": 1, "message": "x" * 2001})
    assert response.status_code == 400
    assert "message" in response.json()["error"]
    response = client.post("/api/search", json={"query": "x" * 501})
    assert response.status_code == 400
    assert client.post("/api/search", json={"query": "ok", "top_k": 1000}).status_code == 400
    assert client.post("/api/chat", json={**CHAT, "session_id": "s" * 65}).status_code == 400


def test_oversized_body_is_a_413(client):
    response = client.post("/api/chat", json={"podcast_id": 1, "message": "x" * 20000})
    assert response.status_code == 413


def test_chat_sessions_are_capped(client, monkeypatch):
    import api.controller as controller
    controller.guard.settings.ip_daily_model_requests = 0
    controller.guard.settings.max_sessions = 2
    monkeypatch.setattr(controller, "current_sessions", {})
    for i in range(4):
        client.post("/api/chat", json={**CHAT, "session_id": f"s{i}"})
    assert list(controller.current_sessions) == ["s2", "s3"]
