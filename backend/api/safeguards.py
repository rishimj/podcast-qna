#!/usr/bin/env python3
"""
Abuse and cost safeguards for the public API.

The API has no accounts, and every chat or summary request spends Claude
credits (and the email endpoint sends mail to any address). Before a request
reaches a handler, Guard.check() applies, in order:

  1. Body size cap            -> 413
  2. Optional access code     -> 401 (ACCESS_CODE; off by default)
  3. Per-IP burst limit       -> 429 (any endpoint)
  4. Daily caps on model calls, per IP and site-wide            -> 429
  5. Daily caps on summary emails, per IP and site-wide         -> 429
  6. Spend caps from the recorded Claude usage (day/week/month) -> 429

Model requests are logged to the `api_requests` table in llm_usage.db at
admission, so daily counts survive server restarts and a bot can't reset its
quota by crashing the server. Spend is read from the `llm_usage` table that
search/claude_llm.py fills in after every model call.

All limits come from environment variables (config/env/config.env), see
Settings. Every limit can be raised or set to 0 to disable it.
"""

import logging
import os
import sqlite3
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from search.claude_llm import connect_usage_db, load_project_env

logger = logging.getLogger(__name__)

# Endpoints that call Claude. The email endpoint also sends mail, so it has
# its own, tighter caps on top of the model caps.
MODEL_PATHS = frozenset({"/api/chat", "/api/summary/generate", "/api/summary/email"})
EMAIL_PATHS = frozenset({"/api/summary/email"})
# Only these paths cost anything; GET endpoints and health only get the burst limit.
PROTECTED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Input caps enforced by the request models in the controller. Long inputs
# cost tokens on every model call in the RAG graph.
MAX_QUERY_CHARS = 500
MAX_MESSAGE_CHARS = 2000
MAX_TOP_K = 20
MAX_SESSION_ID_CHARS = 64


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        logger.warning("%s is not an integer; using %s", name, default)
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        logger.warning("%s is not a number; using %s", name, default)
        return default


@dataclass
class Settings:
    """Limits, read from the environment. 0 disables a limit."""

    daily_model_requests: int = 300       # site-wide chat + summary requests per day
    ip_daily_model_requests: int = 40     # ... per client IP
    ip_burst_per_minute: int = 30         # any request, per client IP
    daily_emails: int = 20                # summary emails per day, site-wide
    ip_daily_emails: int = 3              # ... per client IP
    daily_budget_usd: float = 5.0         # recorded Claude spend, local calendar day
    weekly_budget_usd: float = 0.0        # trailing 7 days
    monthly_budget_usd: float = 0.0       # month to date
    max_body_bytes: int = 16 * 1024
    max_sessions: int = 500               # chat sessions kept in memory
    access_code: str = ""                 # required X-Access-Code header when set
    trust_proxy: bool = False             # take client IP from X-Forwarded-For

    @classmethod
    def from_env(cls) -> "Settings":
        load_project_env()
        return cls(
            daily_model_requests=_env_int("DAILY_REQUEST_LIMIT", cls.daily_model_requests),
            ip_daily_model_requests=_env_int("IP_DAILY_REQUEST_LIMIT", cls.ip_daily_model_requests),
            ip_burst_per_minute=_env_int("IP_BURST_LIMIT", cls.ip_burst_per_minute),
            daily_emails=_env_int("DAILY_EMAIL_LIMIT", cls.daily_emails),
            ip_daily_emails=_env_int("IP_DAILY_EMAIL_LIMIT", cls.ip_daily_emails),
            daily_budget_usd=_env_float("DAILY_BUDGET_LIMIT", cls.daily_budget_usd),
            weekly_budget_usd=_env_float("WEEKLY_BUDGET_LIMIT", cls.weekly_budget_usd),
            monthly_budget_usd=_env_float("MONTHLY_BUDGET_LIMIT", cls.monthly_budget_usd),
            max_body_bytes=_env_int("MAX_BODY_BYTES", cls.max_body_bytes),
            max_sessions=_env_int("MAX_SESSIONS", cls.max_sessions),
            access_code=os.getenv("ACCESS_CODE", "").strip(),
            trust_proxy=os.getenv("TRUST_PROXY", "0").strip().lower() in ("1", "true", "yes"),
        )


@dataclass
class Rejection:
    status: int
    message: str
    retry_after: int | None = None  # seconds; becomes the Retry-After header
    code: str = ""                  # machine-readable reason for the frontend

    def body(self) -> dict:
        body = {"error": self.message}
        if self.code:
            body["code"] = self.code
        if self.retry_after is not None:
            body["retry_after"] = self.retry_after
        return body

    def headers(self) -> dict:
        return {"Retry-After": str(self.retry_after)} if self.retry_after is not None else {}


def connect_request_log() -> sqlite3.Connection:
    """The usage database, with the api_requests table created on first use."""
    conn = connect_usage_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,  -- local time, like llm_usage
            ip TEXT NOT NULL,
            path TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS api_requests_day_ip ON api_requests (created_at, ip)")
    return conn


def seconds_until_midnight(now: datetime) -> int:
    tomorrow = datetime.combine(now.date() + timedelta(days=1), datetime.min.time())
    return max(1, int((tomorrow - now).total_seconds()) + 1)


class Guard:
    """Decides whether a request may proceed. Thread-safe; one instance per app."""

    def __init__(self, settings: Settings | None = None, now=datetime.now):
        self.settings = settings or Settings.from_env()
        self._now = now
        self._lock = threading.Lock()
        self._burst: dict[str, deque] = {}
        self._pruned = False  # old request rows are pruned on the first model request
        s = self.settings
        logger.info(
            "Safeguards: %d model requests/day (%d per IP), %d requests/min per IP, "
            "%d emails/day (%d per IP), budget $%.2f/day, access code %s, trust proxy %s",
            s.daily_model_requests, s.ip_daily_model_requests, s.ip_burst_per_minute,
            s.daily_emails, s.ip_daily_emails, s.daily_budget_usd,
            "on" if s.access_code else "off", "on" if s.trust_proxy else "off",
        )

    # ── client identity ──────────────────────────────────────────────

    def client_ip(self, headers, remote_addr: str | None) -> str:
        """The address to rate-limit on.

        X-Forwarded-For is only honoured with TRUST_PROXY=1: without a proxy
        in front, any client could set it and pick its own quota bucket.
        """
        if self.settings.trust_proxy:
            for header in ("cf-connecting-ip", "x-real-ip"):
                value = headers.get(header)
                if value:
                    return value.strip()
            forwarded = headers.get("x-forwarded-for")
            if forwarded:
                return forwarded.split(",")[0].strip()
        return remote_addr or "unknown"

    # ── the decision ─────────────────────────────────────────────────

    def check(self, *, ip: str, method: str, path: str,
              content_length: int | str | None = None,
              access_code: str | None = None) -> Rejection | None:
        """None if the request may proceed, otherwise the Rejection to send."""
        method = method.upper()
        if method == "OPTIONS":  # CORS preflight never costs anything
            return None
        s = self.settings

        if s.max_body_bytes and content_length:
            try:
                too_big = int(content_length) > s.max_body_bytes
            except (TypeError, ValueError):
                too_big = True
            if too_big:
                return Rejection(413, f"Request body must be under {s.max_body_bytes} bytes",
                                 code="body_too_large")

        protected = method in PROTECTED_METHODS and path.startswith("/api/")
        if protected and s.access_code and (access_code or "").strip() != s.access_code:
            return Rejection(401, "An access code is required to use this site",
                             code="access_code_required")

        if s.ip_burst_per_minute and self._burst_exceeded(ip):
            logger.warning("Burst limit hit by %s on %s", ip, path)
            return Rejection(429, "Too many requests, slow down and try again in a minute",
                             retry_after=60, code="burst")

        if path not in MODEL_PATHS or method not in PROTECTED_METHODS:
            return None

        now = self._now()
        today = now.date()
        until_tomorrow = seconds_until_midnight(now)
        if not self._pruned:
            self._prune_old_rows()
        conn = connect_request_log()
        try:
            if s.ip_daily_model_requests and \
                    self._count(conn, today, MODEL_PATHS, ip) >= s.ip_daily_model_requests:
                logger.warning("Per-IP daily request limit hit by %s", ip)
                return Rejection(429, "You've reached today's request limit; please come back tomorrow",
                                 retry_after=until_tomorrow, code="ip_daily_limit")
            if s.daily_model_requests and \
                    self._count(conn, today, MODEL_PATHS) >= s.daily_model_requests:
                logger.warning("Site-wide daily request limit hit (%s)", ip)
                return Rejection(429, "This site has reached its daily request limit; please come back tomorrow",
                                 retry_after=until_tomorrow, code="daily_limit")
            if path in EMAIL_PATHS:
                if s.ip_daily_emails and \
                        self._count(conn, today, EMAIL_PATHS, ip) >= s.ip_daily_emails:
                    logger.warning("Per-IP daily email limit hit by %s", ip)
                    return Rejection(429, "You've reached today's email limit",
                                     retry_after=until_tomorrow, code="ip_email_limit")
                if s.daily_emails and self._count(conn, today, EMAIL_PATHS) >= s.daily_emails:
                    logger.warning("Site-wide daily email limit hit (%s)", ip)
                    return Rejection(429, "This site has reached its daily email limit",
                                     retry_after=until_tomorrow, code="email_limit")

            over_budget = self._over_budget(conn, today)
            if over_budget:
                logger.warning("Spend cap reached (%s); refusing model request from %s", over_budget, ip)
                return Rejection(429, "This site has reached its usage budget for now; please come back later",
                                 retry_after=until_tomorrow, code="budget")

            # Admit and count it now, so concurrent requests can't all squeeze
            # under the cap, and so failed attempts still burn the bot's quota.
            with conn:
                conn.execute("INSERT INTO api_requests (created_at, ip, path) VALUES (?, ?, ?)",
                             (now.isoformat(timespec="seconds"), ip, path))
        finally:
            conn.close()
        return None

    # ── helpers ──────────────────────────────────────────────────────

    def _burst_exceeded(self, ip: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._burst.setdefault(ip, deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.settings.ip_burst_per_minute:
                return True
            hits.append(now)
            # Forget idle clients so the table can't grow without bound.
            if len(self._burst) > 10_000:
                for key in [k for k, v in self._burst.items() if not v or now - v[-1] > 60]:
                    del self._burst[key]
            return False

    @staticmethod
    def _count(conn, day: date, paths, ip: str | None = None) -> int:
        placeholders = ",".join("?" for _ in paths)
        sql = f"SELECT COUNT(*) FROM api_requests WHERE date(created_at) = ? AND path IN ({placeholders})"
        params: list = [day.isoformat(), *sorted(paths)]
        if ip is not None:
            sql += " AND ip = ?"
            params.append(ip)
        return conn.execute(sql, params).fetchone()[0]

    @staticmethod
    def _spend(conn, start: date, end: date) -> float:
        return conn.execute(
            "SELECT COALESCE(SUM(cost_usd), 0) FROM llm_usage WHERE date(created_at) BETWEEN ? AND ?",
            (start.isoformat(), end.isoformat()),
        ).fetchone()[0]

    def _over_budget(self, conn, today: date) -> str | None:
        """Name of the first exceeded budget, or None."""
        s = self.settings
        if s.daily_budget_usd and self._spend(conn, today, today) >= s.daily_budget_usd:
            return "daily"
        if s.weekly_budget_usd and \
                self._spend(conn, today - timedelta(days=6), today) >= s.weekly_budget_usd:
            return "weekly"
        if s.monthly_budget_usd and \
                self._spend(conn, today.replace(day=1), today) >= s.monthly_budget_usd:
            return "monthly"
        return None

    def _prune_old_rows(self):
        """Request rows only matter for today's counts; keep a month for auditing."""
        self._pruned = True
        try:
            conn = connect_request_log()
            try:
                cutoff = (self._now() - timedelta(days=35)).isoformat(timespec="seconds")
                with conn:
                    conn.execute("DELETE FROM api_requests WHERE created_at < ?", (cutoff,))
            finally:
                conn.close()
        except Exception as e:  # never block startup on bookkeeping
            logger.error("Could not prune api_requests: %s", e)


def remember_session(sessions: dict, session_id: str, value: dict, max_sessions: int) -> dict:
    """Store a chat session, evicting the oldest once max_sessions is exceeded.

    Sessions live in a plain dict; without a cap, a bot could create one per
    request until the process runs out of memory.
    """
    sessions[session_id] = value
    if max_sessions:
        while len(sessions) > max_sessions:
            oldest = next(iter(sessions))
            if oldest == session_id:
                break
            del sessions[oldest]
    return value


def install_fastapi(app, guard: Guard | None = None) -> Guard:
    """Attach the guard to a FastAPI app as HTTP middleware. Returns the guard."""
    from fastapi.responses import JSONResponse

    guard = guard or Guard()

    @app.middleware("http")
    async def safeguards(request, call_next):
        ip = guard.client_ip(request.headers, request.client.host if request.client else None)
        rejection = guard.check(
            ip=ip,
            method=request.method,
            path=request.url.path,
            content_length=request.headers.get("content-length"),
            access_code=request.headers.get("x-access-code"),
        )
        if rejection is not None:
            return JSONResponse(rejection.body(), status_code=rejection.status,
                                headers=rejection.headers())
        return await call_next(request)

    return guard
