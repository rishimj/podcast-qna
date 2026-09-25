#!/usr/bin/env python3
"""
Notion export: writes episode summaries and chat conversations as Notion pages.

Uses a Notion internal integration (https://www.notion.so/my-integrations).
Pages are created under one parent page that has been shared with that
integration ("..." menu on the page -> Connections -> add the integration).

Configuration (config/env/config.env):
  NOTION_TOKEN            the integration's secret (starts with "ntn_" or "secret_")
  NOTION_PARENT_PAGE_ID   the parent page's id, or just paste its URL
"""

import logging
import os
import re
from datetime import datetime

import requests

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
# Notion's per-request limits: 2000 characters per rich-text object and
# 100 child blocks per create/append call.
MAX_TEXT_CHARS = 2000
MAX_BLOCKS_PER_REQUEST = 100


class NotionError(Exception):
    """Notion refused the request or could not be reached."""


def parse_page_id(value: str) -> str:
    """A page id from a raw id or a Notion page URL; '' if none is found."""
    compact = (value or "").strip().split("?")[0].replace("-", "")
    match = re.search(r"[0-9a-fA-F]{32}$", compact)
    return match.group(0).lower() if match else ""


# ──────────────────────────── Markdown -> blocks ────────────────

def rich_text(text: str) -> list:
    """Notion rich text for a line of Markdown; **bold** spans become bold."""
    parts = []
    for segment in re.split(r"(\*\*[^*\n]+\*\*)", text):
        bold = len(segment) > 4 and segment.startswith("**") and segment.endswith("**")
        content = segment[2:-2] if bold else segment
        for start in range(0, len(content), MAX_TEXT_CHARS):
            parts.append({
                "type": "text",
                "text": {"content": content[start:start + MAX_TEXT_CHARS]},
                "annotations": {"bold": bold},
            })
    return parts


def block(kind: str, text: str) -> dict:
    return {"object": "block", "type": kind, kind: {"rich_text": rich_text(text)}}


def markdown_to_blocks(markdown: str) -> list:
    """Convert the Markdown Claude writes (headings, lists, bold) to Notion blocks."""
    blocks = []
    for raw in (markdown or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", line):
            blocks.append({"object": "block", "type": "divider", "divider": {}})
        elif m := re.match(r"^(#{1,6})\s+(.*)$", line):
            level = min(len(m.group(1)), 3)
            blocks.append(block(f"heading_{level}", m.group(2).strip("# ")))
        elif m := re.match(r"^[-*•]\s+(.*)$", line):
            blocks.append(block("bulleted_list_item", m.group(1)))
        elif m := re.match(r"^\d+[.)]\s+(.*)$", line):
            blocks.append(block("numbered_list_item", m.group(1)))
        elif m := re.match(r"^>\s?(.*)$", line):
            blocks.append(block("quote", m.group(1)))
        else:
            blocks.append(block("paragraph", line))
    return blocks


def export_note(source: str) -> dict:
    """Italic grey first line saying where and when the page came from."""
    stamp = datetime.now().strftime("%B %d, %Y at %I:%M %p")
    return {
        "object": "block", "type": "paragraph",
        "paragraph": {"rich_text": [{
            "type": "text",
            "text": {"content": f"{source} · exported from Podcast Q&A on {stamp}"},
            "annotations": {"italic": True, "color": "gray"},
        }]},
    }


def conversation_blocks(history: list) -> list:
    """Each question as a heading, followed by the answer's Markdown."""
    blocks = []
    for turn in history:
        blocks.append(block("heading_3", turn.get("human", "")))
        blocks.extend(markdown_to_blocks(turn.get("assistant", "")))
        blocks.append({"object": "block", "type": "divider", "divider": {}})
    return blocks[:-1]  # no divider after the last answer


# ──────────────────────────── API client ────────────────────────

class NotionService:
    def __init__(self, token: str | None = None, parent_page_id: str | None = None,
                 http=None, timeout: float = 30):
        self.token = (token if token is not None else os.getenv("NOTION_TOKEN", "")).strip()
        self.parent_page_id = parse_page_id(
            parent_page_id if parent_page_id is not None else os.getenv("NOTION_PARENT_PAGE_ID", ""))
        self.http = http or requests
        self.timeout = timeout

    @property
    def configured(self) -> bool:
        return bool(self.token and self.parent_page_id)

    def _call(self, method: str, path: str, payload: dict) -> dict:
        try:
            response = self.http.request(
                method, f"{NOTION_API}{path}", json=payload, timeout=self.timeout,
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Notion-Version": NOTION_VERSION,
                    "Content-Type": "application/json",
                },
            )
        except requests.RequestException as e:
            raise NotionError(f"Could not reach Notion: {e}") from e

        if response.status_code < 400:
            return response.json()

        try:
            detail = response.json().get("message", "")
        except ValueError:
            detail = response.text[:200]
        logger.error("Notion %s %s failed (%s): %s", method, path, response.status_code, detail)
        if response.status_code == 401:
            raise NotionError("Notion rejected the integration token (check NOTION_TOKEN)")
        if response.status_code == 404:
            raise NotionError("Notion can't see the parent page; share it with the integration "
                              "(page menu -> Connections)")
        if response.status_code == 429:
            raise NotionError("Notion is rate limiting requests; try again in a moment")
        raise NotionError(f"Notion error: {detail or response.status_code}")

    def create_page(self, title: str, blocks: list) -> dict:
        """Create a page under the parent page. Returns {'id', 'url'}."""
        if not self.configured:
            raise NotionError("Notion export is not configured")

        first, rest = blocks[:MAX_BLOCKS_PER_REQUEST], blocks[MAX_BLOCKS_PER_REQUEST:]
        page = self._call("POST", "/pages", {
            "parent": {"page_id": self.parent_page_id},
            "icon": {"type": "emoji", "emoji": "🎧"},
            "properties": {"title": {"title": [{"text": {"content": title[:MAX_TEXT_CHARS]}}]}},
            "children": first,
        })
        # Long summaries/conversations go in follow-up appends of 100 blocks each.
        for start in range(0, len(rest), MAX_BLOCKS_PER_REQUEST):
            self._call("PATCH", f"/blocks/{page['id']}/children",
                       {"children": rest[start:start + MAX_BLOCKS_PER_REQUEST]})

        logger.info("Created Notion page %s (%d blocks)", page["id"], len(blocks))
        return {"id": page["id"], "url": page.get("url")}

    def export_summary(self, podcast_title: str, summary: str) -> dict:
        return self.create_page(f"Summary: {podcast_title}",
                                [export_note("Episode summary")] + markdown_to_blocks(summary))

    def export_conversation(self, podcast_title: str, history: list) -> dict:
        return self.create_page(f"Q&A: {podcast_title}",
                                [export_note("Conversation")] + conversation_blocks(history))
