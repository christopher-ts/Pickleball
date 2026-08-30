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


def build_session_entry(item: dict) -> dict:
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

    items_by_id: dict[str, dict] = {}
    for resp in activity_list_bodies:
        for item in (resp.get("body") or {}).get("activity_items", []):
            item_id = item.get("id")
            if item_id is not None:
                items_by_id[item_id] = item

    sessions = [
        build_session_entry(item)
        for item in items_by_id.values()
        if item.get("name") and OPEN_PLAY_PATTERN.search(item["name"])
    ]
    weekday_order = {day: i for i, day in enumerate(["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"])}
    sessions.sort(key=lambda s: (weekday_order.get(s["day"], 99), s["time"] or ""))

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
