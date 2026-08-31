"""Scrapes Santa Monica Rec's ActiveCommunities site for open-play pickleball
sessions and writes data/sessions.json.

The search page is a client-rendered Angular app backed by a JSON API at
POST /rest/activities/list. We drive a real headless browser (Playwright) to
load the search page -- which establishes whatever session/cookies the API
needs and fires that request itself -- and capture the response directly
rather than trying to replay the request by hand. Confirmed against a real
run on 2026-08-29; see data/debug_capture.json for the raw shape.
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

ACTIVITY_LIST_URL_FRAGMENT = "/rest/activities/list"

# Drop-in sessions carry no structured date from the API -- date_range_start/
# end are only populated for recurring classes/leagues, always empty for
# open-play items -- so the only date signal is embedded in the free-text
# name (e.g. "Pickleball Drop-In, Tues., Sept. 1"). Parsed out here so
# sessions can be sorted chronologically instead of just by weekday name.
MONTH_ABBR = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
DATE_IN_NAME_PATTERN = re.compile(
    r"\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?\s+(\d{1,2})\b",
    re.IGNORECASE,
)
START_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})\s*(AM|PM)", re.IGNORECASE)
SESSION_NUMBER_PATTERN = re.compile(r"Session\s+(\d+)", re.IGNORECASE)


def parse_date_from_name(name: str | None, today: datetime) -> str | None:
    """Best-effort "Month Day" extraction from a session name. Assumes the
    current year, rolling to next year if that would place the date more
    than ~60 days in the past (handles scraping in Nov/Dec for Jan dates)."""
    if not name:
        return None
    match = DATE_IN_NAME_PATTERN.search(name)
    if not match:
        return None
    month = MONTH_ABBR.get(match.group(1).lower())
    day = int(match.group(2))
    for year in (today.year, today.year + 1):
        try:
            candidate = datetime(year, month, day, tzinfo=timezone.utc)
        except ValueError:
            continue
        if (today - candidate).days <= 60:
            return candidate.date().isoformat()
    return None


def start_time_minutes(time_range: str | None) -> int:
    """Minutes since midnight for a time range's start (e.g. "8:00 AM -
    11:00 AM" -> 480). Sorting the raw string instead ("11:00 AM" <
    "8:00 AM" lexicographically) put later same-day sessions first, so this
    exists to sort numerically. Unparseable/missing times sort last."""
    if not time_range:
        return 24 * 60
    match = START_TIME_PATTERN.search(time_range)
    if not match:
        return 24 * 60
    hour = int(match.group(1)) % 12
    minute = int(match.group(2))
    if match.group(3).upper() == "PM":
        hour += 12
    return hour * 60 + minute


def session_number(name: str | None) -> int:
    """The N in "...Session N" (e.g. multiple slots on the same day), or 0
    for names with no such suffix -- there's only one session on those
    days, so it never competes with a real session number."""
    if not name:
        return 0
    match = SESSION_NUMBER_PATTERN.search(name)
    return int(match.group(1)) if match else 0

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SESSIONS_PATH = DATA_DIR / "sessions.json"
DEBUG_PATH = DATA_DIR / "debug_capture.json"

# Only sessions whose name looks like open play / drop-in are kept.
OPEN_PLAY_PATTERN = re.compile(r"open\s*play|drop[\s-]?in", re.IGNORECASE)

# The API returns full street addresses (e.g. "1401 Olympic Blvd. Memorial
# Park Tennis/Pickleball Courts"). Shorten to just the facility name for
# display; add entries here as new facilities show up.
LOCATION_SHORT_NAMES = {
    "1401 Olympic Blvd. Memorial Park Tennis/Pickleball Courts": "Memorial Park",
}
ADDRESS_PREFIX_PATTERN = re.compile(r"^\d+[^,]*?(?:Blvd\.|St\.|Ave\.|Avenue|Street|Dr\.|Drive)\s*")
PARK_NAME_PATTERN = re.compile(r"^(.*?\bPark\b)")


def short_location(label: str | None) -> str | None:
    if not label:
        return label
    if label in LOCATION_SHORT_NAMES:
        return LOCATION_SHORT_NAMES[label]
    stripped = ADDRESS_PREFIX_PATTERN.sub("", label).strip()
    match = PARK_NAME_PATTERN.search(stripped)
    return match.group(1) if match else (stripped or label)

MAX_MISC_CAPTURED_RESPONSES = 10
MAX_MISC_BODY_CHARS = 5_000


def capture_network(page, activity_list_bodies: list[dict], misc_captured: list[dict]) -> None:
    def on_response(response):
        url = response.url
        if ACTIVITY_LIST_URL_FRAGMENT in url and response.request.method == "POST":
            try:
                activity_list_bodies.append(response.json())
            except Exception as exc:  # noqa: BLE001 - best effort diagnostics
                misc_captured.append({"url": url, "parse_error": str(exc)})
            return

        if len(misc_captured) >= MAX_MISC_CAPTURED_RESPONSES:
            return
        content_type = response.headers.get("content-type", "")
        if "json" not in content_type and "/rest/" not in url:
            return
        entry = {"url": url, "method": response.request.method, "status": response.status}
        try:
            body = response.text()
            if len(body) > MAX_MISC_BODY_CHARS:
                body = body[:MAX_MISC_BODY_CHARS] + "...<truncated>"
            entry["body"] = body
        except Exception as exc:  # noqa: BLE001 - best effort diagnostics
            entry["body_error"] = str(exc)
        misc_captured.append(entry)

    page.on("response", on_response)


def build_session_entry(item: dict, today: datetime) -> dict:
    urgent = item.get("urgent_message") or {}
    status_desc = (urgent.get("status_description") or "").strip()
    action = item.get("action_link") or {}
    enroll = item.get("enroll_now") or {}
    register_url = action.get("href") or enroll.get("href") or item.get("detail_url")

    openings = item.get("openings")
    try:
        openings_int = int(openings) if openings not in (None, "") else None
    except (TypeError, ValueError):
        openings_int = None

    has_register_link = bool(action.get("href") or enroll.get("href"))

    if status_desc.lower() == "full" or openings_int == 0:
        status = "Full"
    elif "wait" in status_desc.lower():
        status = "Waitlist"
    elif has_register_link or (openings_int is not None and openings_int > 0):
        status = "Open"
    else:
        status = status_desc or "Unknown"

    location_full = (item.get("location") or {}).get("label")
    spots_total = item.get("total_open")
    spots_taken = item.get("already_enrolled")

    return {
        "id": str(item.get("id")),
        "name": item.get("name"),
        "day": item.get("days_of_week"),
        "date": parse_date_from_name(item.get("name"), today),
        "time": item.get("time_range"),
        "date_range": item.get("date_range"),
        "location": short_location(location_full),
        "location_full": location_full,
        "status": status,
        "spots_left": openings_int,
        "spots_taken": spots_taken,
        "spots_total": spots_total,
        "activity_number": item.get("number"),
        "register_url": register_url,
        "detail_url": item.get("detail_url"),
    }


def scrape() -> dict:
    DATA_DIR.mkdir(exist_ok=True)
    activity_list_bodies: list[dict] = []
    misc_captured: list[dict] = []

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        capture_network(page, activity_list_bodies, misc_captured)

        page.goto(SEARCH_URL, wait_until="networkidle", timeout=45_000)
        try:
            page.wait_for_timeout(3_000)
            page.wait_for_load_state("networkidle", timeout=15_000)
        except Exception:  # noqa: BLE001 - best effort, keep going regardless
            pass

        browser.close()

    DEBUG_PATH.write_text(
        json.dumps(
            {
                "search_url": SEARCH_URL,
                "activity_list_responses": activity_list_bodies,
                "misc_captured_responses": misc_captured,
            },
            indent=2,
            default=str,
        )
    )

    now = datetime.now(timezone.utc)

    items_by_id: dict[str, dict] = {}
    for resp in activity_list_bodies:
        for item in (resp.get("body") or {}).get("activity_items", []):
            item_id = item.get("id")
            if item_id is not None:
                items_by_id[item_id] = item

    sessions = [
        build_session_entry(item, now)
        for item in items_by_id.values()
        if item.get("name") and OPEN_PLAY_PATTERN.search(item["name"])
    ]
    weekday_order = {day: i for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])}
    # Weekday first (matches how the site groups sessions), then the actual
    # calendar date, then session number ("...Session 1"/"Session 2" on a
    # day with multiple slots) -- without the date, sessions on different
    # weeks that share a weekday (e.g. two different Tuesdays) only
    # tied-break on time and stayed in scrape order, not date order.
    # start_time_minutes is a final fallback for the (untested) case of a
    # multi-slot day with no "Session N" wording in its names.
    sessions.sort(key=lambda s: (
        weekday_order.get(s["day"], 99),
        s["date"] or "",
        session_number(s["name"]),
        start_time_minutes(s["time"]),
    ))

    output = {
        "scraped_at": now.isoformat(),
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
