"""The HTTP contract the frontend relies on: errors are {"error": ...} with the
right 4xx status, and bad requests are rejected before any model call."""
import asyncio
import sqlite3

import httpx
import pytest

import api.controller as controller


class ASGIClient:
    """Minimal synchronous client over httpx's ASGI transport.

    Stands in for fastapi.testclient.TestClient, which on Starlette releases
    bundled with older FastAPI (e.g. 0.27) passes an app= argument that
    httpx 0.28 removed. This works with any Starlette/httpx combination.
    """

    def __init__(self, app):
        self.app = app

    def request(self, method, url, **kwargs):
        async def send():
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)
        return asyncio.run(send())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def options(self, url, **kwargs):
        return self.request("OPTIONS", url, **kwargs)


@pytest.fixture
def client(monkeypatch, tmp_path):
    db = tmp_path / "podcasts.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE podcasts (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO podcasts VALUES (1, 'Known episode')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(controller, "DB_PATH", db)
    # Mark services as initialized so require_services doesn't build real
    # clients; none of these requests should ever reach them.
    for name in ("llm", "summarization_service", "email_service"):
        monkeypatch.setattr(controller, name, object())
    monkeypatch.setattr(controller, "run_corrective_rag",
                        lambda **kwargs: pytest.fail("RAG graph must not run"))
    # Default limits regardless of the local config.env (which may turn email off).
    from api.safeguards import Settings
    monkeypatch.setattr(controller.guard, "settings", Settings())
    monkeypatch.setattr(controller.guard, "_burst", {})
    return ASGIClient(controller.app)


@pytest.mark.parametrize("path", ["/api/search", "/api/chat", "/api/summary/generate", "/api/summary/email"])
def test_malformed_json_is_a_400(client, path):
    response = client.post(path, content="{not json", headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert response.json() == {"error": "Request body must be a JSON object"}


def test_non_object_json_is_a_400(client):
    response = client.post("/api/chat", json=[1, 2])
    assert response.status_code == 400
    assert response.json() == {"error": "Request body must be a JSON object"}


def test_missing_body_is_a_400(client):
    assert client.post("/api/chat").status_code == 400


def test_missing_fields_keep_their_specific_message(client):
    response = client.post("/api/chat", json={"podcast_id": 1})
    assert response.status_code == 400
    assert response.json() == {"error": "podcast_id and message are required"}


def test_wrong_field_type_is_a_400_naming_the_field(client):
    response = client.post("/api/chat", json={"podcast_id": "abc", "message": "hi"})
    assert response.status_code == 400
    assert "podcast_id" in response.json()["error"]


def test_chat_about_unknown_podcast_is_a_404_without_a_model_call(client):
    response = client.post("/api/chat", json={"podcast_id": 999, "message": "hi"})
    assert response.status_code == 404
    assert response.json()["error"] == "Podcast not found"


def test_summary_of_unknown_podcast_is_a_404(client):
    response = client.post("/api/summary/generate", json={"podcast_id": 999})
    assert response.status_code == 404
    assert response.json()["error"] == "Podcast not found"


def test_unknown_endpoint_is_a_json_404(client):
    response = client.get("/api/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {"error": "Endpoint not found"}


def test_non_integer_podcast_id_in_path_is_a_404(client):
    assert client.get("/api/podcast/abc").status_code == 404


def test_unknown_session_is_a_404(client):
    response = client.get("/api/chat/session/nope")
    assert response.status_code == 404
    assert response.json() == {"error": "Session not found"}


def test_services_that_cannot_start_return_503(client, monkeypatch):
    monkeypatch.setattr(controller, "llm", None)
    monkeypatch.setattr(controller, "init_services", lambda: False)
    response = client.post("/api/chat", json={"podcast_id": 1, "message": "hi"})
    assert response.status_code == 503
    assert response.json()["error"] == "Services not initialized"


def test_cors_preflight_allows_the_frontend(client):
    response = client.options("/api/chat", headers={
        "Origin": "http://localhost:8080",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    })
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] in ("*", "http://localhost:8080")
