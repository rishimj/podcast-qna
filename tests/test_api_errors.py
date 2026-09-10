"""Client errors must be 4xx, and must be rejected before any model call is made."""
import sqlite3

import pytest

import api.controller as controller


@pytest.fixture
def client(monkeypatch, tmp_path):
    db = tmp_path / "podcasts.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE podcasts (id INTEGER PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO podcasts VALUES (1, 'Known episode')")
    conn.commit()
    conn.close()
    monkeypatch.setattr(controller, "DB_PATH", db)
    # Mark services as initialized so @require_services doesn't try to build
    # real clients; none of these requests should ever reach them.
    for name in ("llm", "summarization_service", "email_service"):
        monkeypatch.setattr(controller, name, object())
    monkeypatch.setattr(controller, "run_corrective_rag",
                        lambda **kwargs: pytest.fail("RAG graph must not run"))
    return controller.app.test_client()


@pytest.mark.parametrize("path", ["/api/search", "/api/chat", "/api/summary/generate", "/api/summary/email"])
def test_malformed_json_is_a_400(client, path):
    response = client.post(path, data="{not json", content_type="application/json")
    assert response.status_code == 400


def test_non_object_json_is_a_400(client):
    assert client.post("/api/chat", json=[1, 2]).status_code == 400


def test_chat_about_unknown_podcast_is_a_404_without_a_model_call(client):
    response = client.post("/api/chat", json={"podcast_id": 999, "message": "hi"})
    assert response.status_code == 404


def test_summary_of_unknown_podcast_is_a_404(client):
    assert client.post("/api/summary/generate", json={"podcast_id": 999}).status_code == 404
