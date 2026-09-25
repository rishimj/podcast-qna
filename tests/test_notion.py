"""Notion export: Markdown becomes Notion blocks within Notion's size limits,
and the endpoints refuse cleanly when Notion isn't set up or has nothing to save."""
import pytest

import api.controller as controller
from search.notion_service import (MAX_TEXT_CHARS, NotionError, NotionService,
                                   conversation_blocks, markdown_to_blocks, parse_page_id)
from test_api_errors import client  # noqa: F401  (fixture)

PAGE_ID = "0123456789abcdef0123456789abcdef"


def test_page_id_from_raw_id_dashed_id_or_url():
    assert parse_page_id(PAGE_ID) == PAGE_ID
    assert parse_page_id("01234567-89ab-cdef-0123-456789abcdef") == PAGE_ID
    assert parse_page_id(f"https://www.notion.so/team/Podcast-notes-{PAGE_ID}?pvs=4") == PAGE_ID
    assert parse_page_id("not a page") == ""


def test_markdown_becomes_headings_lists_and_bold():
    blocks = markdown_to_blocks("# Title\n\n## Key ideas\n- **Agents** matter\n2. Second\n> quoted\n---\nPlain text")
    assert [b["type"] for b in blocks] == [
        "heading_1", "heading_2", "bulleted_list_item", "numbered_list_item", "quote", "divider", "paragraph"]
    bullet = blocks[2]["bulleted_list_item"]["rich_text"]
    assert bullet[0]["text"]["content"] == "Agents" and bullet[0]["annotations"]["bold"]
    assert bullet[1]["text"]["content"] == " matter" and not bullet[1]["annotations"]["bold"]


def test_long_text_is_split_under_notions_limit():
    rich_text = markdown_to_blocks("x" * 4500)[0]["paragraph"]["rich_text"]
    assert [len(part["text"]["content"]) for part in rich_text] == [MAX_TEXT_CHARS, MAX_TEXT_CHARS, 500]


def test_conversation_is_question_heading_then_answer():
    blocks = conversation_blocks([{"human": "Who?", "assistant": "Them."},
                                  {"human": "Why?", "assistant": "- Because"}])
    assert [b["type"] for b in blocks] == ["heading_3", "paragraph", "divider", "heading_3", "bulleted_list_item"]


class FakeResponse:
    def __init__(self, status_code, body):
        self.status_code, self._body, self.text = status_code, body, str(body)

    def json(self):
        return self._body


class FakeHTTP:
    def __init__(self, status_code=200):
        self.status_code = status_code
        self.calls = []

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs["json"]))
        return FakeResponse(self.status_code, {"id": "new-page", "url": "https://notion.so/new-page",
                                               "message": "nope"})


def test_large_pages_are_created_then_appended_in_batches_of_100():
    http = FakeHTTP()
    service = NotionService(token="secret", parent_page_id=PAGE_ID, http=http)
    page = service.export_summary("Episode", "\n".join(f"- point {i}" for i in range(250)))
    assert page == {"id": "new-page", "url": "https://notion.so/new-page"}
    methods = [(m, url.rsplit("/v1", 1)[1], len(body["children"])) for m, url, body in http.calls]
    # 251 blocks: the export note plus 250 bullets.
    assert methods == [("POST", "/pages", 100), ("PATCH", "/blocks/new-page/children", 100),
                       ("PATCH", "/blocks/new-page/children", 51)]
    assert http.calls[0][2]["parent"] == {"page_id": PAGE_ID}


def test_unshared_parent_page_gives_an_actionable_error():
    service = NotionService(token="secret", parent_page_id=PAGE_ID, http=FakeHTTP(404))
    with pytest.raises(NotionError, match="share it with the integration"):
        service.export_summary("Episode", "text")


def test_unconfigured_notion_is_a_503(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(controller, "notion_service", NotionService(token="", parent_page_id=""))
    response = client.post("/api/notion/conversation", json={"session_id": "s1"})
    assert response.status_code == 503


def test_exporting_an_unknown_conversation_is_a_404(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(controller, "notion_service",
                        NotionService(token="secret", parent_page_id=PAGE_ID, http=FakeHTTP()))
    response = client.post("/api/notion/conversation", json={"session_id": "missing"})
    assert response.status_code == 404


def test_exporting_a_conversation_returns_the_page_link(client, monkeypatch):  # noqa: F811
    http = FakeHTTP()
    monkeypatch.setattr(controller, "notion_service",
                        NotionService(token="secret", parent_page_id=PAGE_ID, http=http))
    monkeypatch.setitem(controller.current_sessions, "s1",
                        {"podcast_id": 1, "history": [{"human": "Q?", "assistant": "A."}]})
    response = client.post("/api/notion/conversation", json={"session_id": "s1"})
    assert response.status_code == 200
    assert response.json()["notion_url"] == "https://notion.so/new-page"
    title = http.calls[0][2]["properties"]["title"]["title"][0]["text"]["content"]
    assert title == "Q&A: Known episode"


def test_summary_of_unknown_podcast_is_a_404(client, monkeypatch):  # noqa: F811
    monkeypatch.setattr(controller, "notion_service",
                        NotionService(token="secret", parent_page_id=PAGE_ID, http=FakeHTTP()))
    response = client.post("/api/notion/summary", json={"podcast_id": 999})
    assert response.status_code == 404
