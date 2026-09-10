"""Episodes removed from Spotify come back as null tombstones and must be dropped."""
import spotify_fetcher


class FakeSpotify:
    def __init__(self, items):
        self.items = items

    def current_user_saved_episodes(self, limit=50):
        return {"items": self.items}


def saved(name, episode_id):
    return {
        "added_at": "2026-07-04T11:32:53Z",
        "episode": {"id": episode_id, "name": name, "show": {"name": "Some Show"},
                    "duration_ms": 1000, "external_urls": {"spotify": f"https://open.spotify.com/episode/{episode_id}"}},
    }


TOMBSTONE = {
    "added_at": "2026-07-04T11:32:53Z",
    "episode": {"id": None, "name": None, "show": {"name": None}, "duration_ms": None,
                "external_urls": {}, "href": "https://api.spotify.com/v1/episodes/null"},
}


def test_tombstones_are_dropped_and_reported(capsys):
    episodes = spotify_fetcher.get_saved_episodes(
        FakeSpotify([saved("A", "1"), TOMBSTONE, {"added_at": "x", "episode": None}, saved("B", "2")]))
    assert [e["name"] for e in episodes] == ["A", "B"]
    assert all(value is not None for e in episodes for value in e.values())
    assert "skipped 2 no longer available on Spotify" in capsys.readouterr().out
