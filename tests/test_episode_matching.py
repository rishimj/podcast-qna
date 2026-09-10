"""YouTube candidates must be corroborated by runtime and title before we accept them."""
import json

import pytest

import download_youtube_transcripts as d

EPISODE = {
    "name": "NVIDIA's Agentic AI for Container Security with Amanda Saunders and Allan Enemark",
    "show": "Software Engineering Daily",
    "duration_ms": 45 * 60 * 1000,
}


def candidate(title, uploader="Software Engineering Daily", minutes=45, video_id="v"):
    duration = None if minutes is None else minutes * 60
    return {"title": title, "uploader": uploader, "duration": duration, "video_id": video_id}


def test_exact_episode_is_accepted():
    ev = d.evaluate_candidate(EPISODE, candidate(EPISODE["name"]))
    assert ev["accepted"] and ev["duration_verdict"] == "match"


def test_clip_of_the_same_episode_is_rejected_on_runtime():
    ev = d.evaluate_candidate(EPISODE, candidate("NVIDIA's Agentic AI for Container Security - HIGHLIGHT", minutes=5))
    assert not ev["accepted"] and ev["duration_verdict"] == "mismatch"


def test_one_shared_word_is_not_a_match():
    ev = d.evaluate_candidate(EPISODE, candidate("Container gardening for beginners", uploader="Garden Channel"))
    assert not ev["accepted"]


def test_small_runtime_drift_is_tolerated():
    ev = d.evaluate_candidate(EPISODE, candidate("NVIDIA's Agentic AI for Container Security", minutes=44))
    assert ev["accepted"]


def test_missing_runtime_needs_a_strong_title_match():
    strong = candidate("NVIDIA's Agentic AI for Container Security with Amanda Saunders", minutes=None)
    weak = candidate("Agentic AI podcast", minutes=None)
    assert d.evaluate_candidate(EPISODE, strong)["accepted"]
    assert not d.evaluate_candidate(EPISODE, weak)["accepted"]


def test_best_candidate_wins_not_the_first_plausible_one():
    results = [
        candidate("Container Security basics", uploader="Random", video_id="a"),
        candidate(EPISODE["name"], video_id="b"),
    ]
    best, _ = d.pick_best_match(EPISODE, results)
    assert best["video_id"] == "b"


def test_no_verifiable_candidate_returns_none_instead_of_guessing():
    best, ev = d.pick_best_match(EPISODE, [candidate("Cooking pasta", uploader="Food", minutes=5)])
    assert best is None and ev is not None


def test_tombstone_episode_is_skipped_without_crashing(tmp_path, monkeypatch, capsys):
    tombstone = {"name": None, "show": None, "saved_at": "2026-07-04T11:32:53Z",
                 "duration_ms": None, "url": None, "id": None}
    (tmp_path / "saved_podcasts.json").write_text(json.dumps([tombstone]))
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(d, "search_youtube_for_episode",
                        lambda *a, **k: pytest.fail("tombstones must not be searched"))
    d.process_saved_podcasts(auto_confirm=True)
    assert "skipped (no longer available on Spotify)" in capsys.readouterr().out
