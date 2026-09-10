#!/usr/bin/env python3
"""
Email a daily report of the Claude API spend recorded by backend/search/claude_llm.py.

Covers one day (yesterday by default) plus the trailing 7 days and month to
date, and flags the subject line when DAILY_BUDGET_LIMIT or WEEKLY_BUDGET_LIMIT
from config/env/config.env is exceeded. Sent to COST_ALERT_EMAIL; run daily
at 17:00 by launchd (~/Library/LaunchAgents/com.podcast-qa.daily-cost-report.plist).

Usage (from project root):
    python scripts/daily_cost_report.py                    # email yesterday's report
    python scripts/daily_cost_report.py --dry-run          # print instead of sending
    python scripts/daily_cost_report.py --date 2026-09-09
"""

import argparse
import html
import os
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from search.claude_llm import connect_usage_db, load_project_env  # noqa: E402
from search.email_service import EmailService  # noqa: E402


def spend_between(conn, start: date, end: date) -> tuple[float, int]:
    """Total cost and call count for local dates in [start, end]."""
    return conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM llm_usage "
        "WHERE date(created_at) BETWEEN ? AND ?",
        (start.isoformat(), end.isoformat()),
    ).fetchone()


def breakdown_by_purpose(conn, day: date) -> list[tuple]:
    return conn.execute(
        "SELECT purpose, COUNT(*), "
        "SUM(input_tokens + cache_write_tokens + cache_read_tokens), "
        "SUM(output_tokens), SUM(cost_usd) "
        "FROM llm_usage WHERE date(created_at) = ? "
        "GROUP BY purpose ORDER BY SUM(cost_usd) DESC",
        (day.isoformat(),),
    ).fetchall()


def build_report(day: date, daily_limit: float, weekly_limit: float) -> tuple[str, str]:
    """Return (subject, plain-text body)."""
    conn = connect_usage_db()
    try:
        day_cost, day_calls = spend_between(conn, day, day)
        week_cost, _ = spend_between(conn, day - timedelta(days=6), day)
        month_cost, _ = spend_between(conn, day.replace(day=1), day)
        purposes = breakdown_by_purpose(conn, day)
        last_7 = [day - timedelta(days=i) for i in range(6, -1, -1)]
        daily = [(d, spend_between(conn, d, d)[0]) for d in last_7]
    finally:
        conn.close()

    alerts = []
    if day_cost > daily_limit:
        alerts.append(f"Daily spend ${day_cost:.2f} is over the ${daily_limit:.2f} limit")
    if week_cost > weekly_limit:
        alerts.append(f"7-day spend ${week_cost:.2f} is over the ${weekly_limit:.2f} limit")

    subject = f"Claude API spend for {day:%b %d}: ${day_cost:.2f}"
    if alerts:
        subject = "⚠️ Over budget: " + subject

    lines = [f"Claude API spend for {day:%a %b %d, %Y}", ""]
    lines += [f"⚠️  {a}" for a in alerts]
    if alerts:
        lines.append("")
    lines += [
        f"This day:       ${day_cost:7.2f}   ({day_calls} calls, limit ${daily_limit:.2f})",
        f"Last 7 days:    ${week_cost:7.2f}   (limit ${weekly_limit:.2f})",
        f"Month to date:  ${month_cost:7.2f}",
        "",
    ]
    if purposes:
        lines.append(f"{'By purpose':<16}{'calls':>7}{'in tok':>11}{'out tok':>10}{'cost':>10}")
        for purpose, calls, tok_in, tok_out, cost in purposes:
            lines.append(f"  {purpose:<14}{calls:>7}{tok_in:>11,}{tok_out:>10,}{'$' + format(cost, '.3f'):>10}")
        lines.append("")
    lines.append("Daily totals")
    lines += [f"  {d:%a %b %d}   ${cost:.2f}" for d, cost in daily]
    lines += [
        "",
        "Costs are estimated by the app from each response's token usage.",
        "The Anthropic Console (Usage / Cost pages) is the billing source of truth.",
    ]
    return subject, "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Email a daily Claude API spend report.")
    parser.add_argument("--date", type=date.fromisoformat,
                        default=date.today() - timedelta(days=1),
                        help="day to report, YYYY-MM-DD (default: yesterday)")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the report instead of emailing it")
    args = parser.parse_args()

    load_project_env()
    subject, body = build_report(
        args.date,
        daily_limit=float(os.getenv("DAILY_BUDGET_LIMIT", "5")),
        weekly_limit=float(os.getenv("WEEKLY_BUDGET_LIMIT", "10")),
    )

    if args.dry_run:
        print(f"Subject: {subject}\n\n{body}")
        return 0

    to_email = os.getenv("COST_ALERT_EMAIL", "")
    if not to_email or to_email.endswith("@example.com"):
        print("COST_ALERT_EMAIL is not set in config/env/config.env")
        return 1

    html_body = f'<pre style="font: 13px Menlo, Consolas, monospace">{html.escape(body)}</pre>'
    result = EmailService().send_summary_email(to_email, subject, html_body)
    print(result.get("message") or result.get("error"))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
