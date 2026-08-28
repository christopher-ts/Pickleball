"""Scrapes Santa Monica Rec's ActiveCommunities site for open-play pickleball
sessions and writes data/sessions.json.

Because the search page is a client-rendered Angular app, we drive a real
headless browser (Playwright) rather than issuing plain HTTP requests. While
the page loads we also record every XHR/fetch response so the underlying
JSON API (if any) can be discovered and reused directly in later revisions
of this script -- see data/debug_capture.json.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

SEARCH_URL = (
    "https://anc.apm.activecommunities.com/santamonicarecreation/activity/search"
    "?onlineSiteId=0&activity_select_param=2&viewMode=list&activity_keyword=pickleball"
)

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SESSIONS_PATH = DATA_DIR / "sessions.json"
DEBUG_PATH = DATA_DIR / "debug_capture.json"

# Only sessions whose name/description looks like open play / drop-in are kept.
OPEN_PLAY_PATTERN = re.compile(r"open\s*play|drop[\s-]?in", re.IGNORECASE)

MAX_CAPTURED_RESPONSES = 40
MAX_BODY_CHARS = 50_000


def capture_network(page, captured: list[dict]) -> None:
    def on_response(response):
        if len(captured) >= MAX_CAPTURED_RESPONSES:
            return
        url = response.url
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type and "/rest/" not in url:
            return
        entry = {
            "url": url,
            "method": response.request.method,
            "status": response.status,
            "request_post_data": response.request.post_data,
        }
        try:
            body = response.text()
            if len(body) > MAX_BODY_CHARS:
                body = body[:MAX_BODY_CHARS] + "...<truncated>"
            entry["body"] = body
        except Exception as exc:  # noqa: BLE001 - best effort diagnostics
            entry["body_error"] = str(exc)
        captured.append(entry)

    page.on("response", on_response)


def find_activity_records(node, found: list[dict], seen_ids: set) -> None:
    """Recursively search parsed JSON for dict records that look like
    activity/session entries (have some kind of name field mentioning
    pickleball)."""
    if isinstance(node, dict):
        name_val = None
        for key, val in node.items():
            if isinstance(val, str) and "name" in key.lower() and "pickleball" in val.lower():
                name_val = val
                break
        if name_val:
            record_id = json.dumps(node, sort_keys=True, default=str)[:200]
            if record_id not in seen_ids:
                seen_ids.add(record_id)
                found.append(node)
        for val in node.values():
            find_activity_records(val, found, seen_ids)
    elif isinstance(node, list):
        for item in node:
            find_activity_records(item, found, seen_ids)


def build_session_entry(raw: dict) -> dict:
    """Best-effort normalization of a raw record into our session schema.
    Field names are guesses to be refined once we see real API output."""

    def first_str(*keys):
        for k in keys:
            v = raw.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    return {
        "id": first_str("id", "activity_id", "activityId") or None,
        "name": first_str("name", "activity_name", "activityName"),
        "day": first_str("day", "days", "day_of_week"),
        "time": first_str("time", "activity_time", "time_range"),
        "date_range": first_str("date_range", "dates"),
        "location": first_str("location", "center", "facility", "center_name"),
        "status": first_str("status", "activity_status", "availability"),
        "spots_left": raw.get("spots_left") or raw.get("openings"),
        "price": first_str("price", "fee"),
        "register_url": first_str("register_url", "url", "activity_url"),
        "raw": raw,
    }


def scrape() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    captured: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        capture_network(page, captured)

        page.goto(SEARCH_URL, wait_until="networkidle", timeout=45_000)
        try:
            page.wait_for_timeout(3_000)
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:  # noqa: BLE001 - best effort, keep going regardless
            pass

        rendered_text = page.inner_text("body")
        rendered_html_len = len(page.content())

        browser.close()

    DEBUG_PATH.write_text(
        json.dumps(
            {
                "search_url": SEARCH_URL,
                "captured_responses": captured,
                "rendered_text_sample": rendered_text[:5_000],
                "rendered_html_length": rendered_html_len,
            },
            indent=2,
            default=str,
        )
    )

    found_records: list[dict] = []
    seen_ids: set = set()
    for entry in captured:
        body = entry.get("body")
        if not body:
            continue
        try:
            parsed = json.loads(body)
        except (json.JSONDecodeError, TypeError):
            continue
        find_activity_records(parsed, found_records, seen_ids)

    sessions = [build_session_entry(r) for r in found_records]
    sessions = [
        s
        for s in sessions
        if s["name"] and (OPEN_PLAY_PATTERN.search(s["name"]) or not sessions)
    ]

    output = {
        "scraped_at": datetime.now(timezone.utc).isoformat(),
        "source_url": SEARCH_URL,
        "session_count": len(sessions),
        "sessions": sessions,
    }
    SESSIONS_PATH.write_text(json.dumps(output, indent=2, default=str))
    return output


if __name__ == "__main__":
    result = scrape()
    print(f"Wrote {result['session_count']} session(s) to {SESSIONS_PATH}")
    print(f"Debug capture written to {DEBUG_PATH}")
