#!/bin/bash
# Daily podcast refresh: Spotify saved episodes -> YouTube transcripts -> index.
#
# Runs unattended under launchd (com.podcast-qna.daily-refresh) and must never
# prompt: there is nobody at the keyboard. Every step degrades rather than
# hangs, and any failure raises a macOS notification instead of failing silently.
set -u

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="/Users/rishimanimaran/miniforge3/bin/python3"
OLLAMA="/opt/homebrew/bin/ollama"
LOG_DIR="$PROJECT_ROOT/logs"
LOG="$LOG_DIR/daily_refresh.log"
LOCK="$LOG_DIR/.daily_refresh.lock"
SPOTIFY_CACHE="backend/data_collection/.spotifycache"  # orchestrator chdirs here
MAX_RUNTIME=7200  # seconds; a hung step must never wedge future runs

export PYTHONUNBUFFERED=1
mkdir -p "$LOG_DIR"
exec >>"$LOG" 2>&1

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
notify() {
    /usr/bin/osascript -e "display notification \"$1\" with title \"Podcast refresh\"" >/dev/null 2>&1 || true
}
# Cap a command's runtime; perl is always present on macOS, `timeout` is not.
run_capped() { /usr/bin/perl -e 'alarm shift; exec @ARGV' "$MAX_RUNTIME" "$@"; }

# --- single-run lock (reclaimed if the holder died) -------------------------
if ! mkdir "$LOCK" 2>/dev/null; then
    holder=$(cat "$LOCK/pid" 2>/dev/null || true)
    if [ -n "$holder" ] && kill -0 "$holder" 2>/dev/null; then
        log "run already in progress (pid $holder); exiting"
        exit 0
    fi
    log "reclaiming stale lock from pid ${holder:-unknown}"
    rm -rf "$LOCK" && mkdir "$LOCK"
fi
echo $$ > "$LOCK/pid"

STARTED_OLLAMA=""
cleanup() {
    if [ -n "$STARTED_OLLAMA" ]; then kill "$STARTED_OLLAMA" 2>/dev/null; fi
    rm -rf "$LOCK"
}
trap cleanup EXIT

cd "$PROJECT_ROOT" || { log "cannot enter $PROJECT_ROOT"; notify "Cannot access project folder"; exit 1; }
log "=============== run start ==============="
FAILED=""

# --- Ollama: needed for embeddings; not a managed service on this machine --
if ! /usr/bin/curl -s -m 3 http://localhost:11434/api/tags >/dev/null; then
    log "ollama not running; starting it for this run"
    "$OLLAMA" serve >>"$LOG_DIR/ollama.log" 2>&1 &
    STARTED_OLLAMA=$!
    for _ in $(seq 1 30); do
        /usr/bin/curl -s -m 2 http://localhost:11434/api/tags >/dev/null && break
        sleep 1
    done
fi

# --- Step 1: Spotify token preflight ----------------------------------------
# spotify_fetcher uses open_browser=True, which blocks forever on a login page
# when the token is invalid. Refresh headlessly first; if that fails, skip the
# Spotify step and keep going with the episodes we already have.
if "$PYTHON" - "$SPOTIFY_CACHE" <<'PY'
import json, os, sys
cache = sys.argv[1]
for line in open("config/env/config.env"):
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, v = line.split("=", 1)
        os.environ[k.strip()] = v.strip()
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
if not os.path.exists(cache):
    print(f"no Spotify token cache at {cache}")
    sys.exit(1)
auth = SpotifyOAuth(
    client_id=os.environ["SPOTIFY_CLIENT_ID"],
    client_secret=os.environ["SPOTIFY_CLIENT_SECRET"],
    redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
    scope="user-library-read",
    open_browser=False,
    cache_handler=CacheFileHandler(cache_path=cache),
    requests_timeout=20,
)
try:
    token = auth.validate_token(auth.cache_handler.get_cached_token())  # refreshes + saves
except Exception as e:
    print(f"Spotify token refresh failed: {e}")
    sys.exit(1)
sys.exit(0 if token else 1)
PY
then
    log "spotify token valid"
    COLLECT_ARGS=""
else
    log "SPOTIFY RE-AUTH NEEDED: skipping Spotify fetch, using existing episode export"
    COLLECT_ARGS="--transcripts-only"
    FAILED="$FAILED spotify-auth"
fi

# --- Step 2: fetch episodes + transcripts -----------------------------------
log "collecting (args: ${COLLECT_ARGS:-full})"
if ! run_capped "$PYTHON" collect_podcasts.py $COLLECT_ARGS; then
    log "collection step failed"
    FAILED="$FAILED collect"
fi

# --- Step 3: index, then verify nothing on disk is left unsearchable --------
# Retried once, but only on a crash (exit 1). Exit 2 means verify found files
# it genuinely cannot index; retrying would just repeat that.
index_and_verify() {
    run_capped "$PYTHON" - <<'PY'
import os, sqlite3, sys
root = os.getcwd()
sys.path.insert(0, os.path.join(root, "backend"))
from search.podcast_semantic_search_complete import PodcastTwoTierSearch

transcripts = os.path.join(root, "data", "transcripts")  # absolute: never cwd-relative
PodcastTwoTierSearch().index_all_podcasts_enhanced(transcripts)

db = os.path.join(root, "data", "databases", "podcast_index_v2.db")
indexed = {r[0] for r in sqlite3.connect(db).execute("SELECT filename FROM podcasts")}
on_disk = {f for f in os.listdir(transcripts) if f.endswith(".txt")}
missing = sorted(on_disk - indexed)
print(f"\nverify: {len(on_disk)} transcripts on disk, {len(indexed)} indexed, {len(missing)} unindexed")
for m in missing:
    print(f"  UNINDEXED: {m}")
sys.exit(2 if missing else 0)
PY
}
log "indexing new transcripts"
index_and_verify
rc=$?
if [ "$rc" -eq 1 ]; then
    log "index step crashed (exit 1); retrying once in 30s"
    sleep 30
    index_and_verify
    rc=$?
fi
if [ "$rc" -ne 0 ]; then
    log "index or verify step failed (exit $rc)"
    FAILED="$FAILED index"
fi

# --- Outcome ------------------------------------------------------------------
if [ -n "$FAILED" ]; then
    log "run finished WITH FAILURES:$FAILED"
    case "$FAILED" in
        *spotify-auth*) notify "Spotify login expired - run the one-time auth (see logs/daily_refresh.log)" ;;
        *) notify "Refresh failed:$FAILED - see logs/daily_refresh.log" ;;
    esac
    exit 1
fi
log "run finished OK"
