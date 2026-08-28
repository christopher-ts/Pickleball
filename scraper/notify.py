"""Compares the freshly scraped data/sessions.json against the previous
snapshot (data/sessions.prev.json, staged by the workflow before scraping
runs) and pushes an ntfy.sh notification for anything new: a session id we
haven't seen before, or one whose status flipped into "Open"."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SESSIONS_PATH = DATA_DIR / "sessions.json"
PREV_SESSIONS_PATH = DATA_DIR / "sessions.prev.json"

OPEN_STATUSES = {"open", "available"}


def load_sessions(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return {}
    return {
        s["id"]: s
        for s in data.get("sessions", [])
        if s.get("id")
    }


def is_open(session: dict) -> bool:
    status = (session.get("status") or "").strip().lower()
    return status in OPEN_STATUSES


def notify(topic: str, session: dict, reason: str) -> None:
    title = f"Pickleball: {reason}"
    lines = [session.get("name") or "Pickleball session"]
    if session.get("day") or session.get("time"):
        lines.append(f"{session.get('day', '')} {session.get('time', '')}".strip())
    if session.get("location"):
        lines.append(session["location"])
    body = "\n".join(lines)

    headers = {"Title": title, "Priority": "high"}
    if session.get("register_url"):
        headers["Click"] = session["register_url"]

    resp = requests.post(
        f"https://ntfy.sh/{topic}",
        data=body.encode("utf-8"),
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()


def main() -> int:
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        print("NTFY_TOPIC not set; skipping notifications.")
        return 0

    prev = load_sessions(PREV_SESSIONS_PATH)
    current = load_sessions(SESSIONS_PATH)

    sent = 0
    for session_id, session in current.items():
        prev_session = prev.get(session_id)
        if prev_session is None:
            notify(topic, session, "new session found")
            sent += 1
        elif not is_open(prev_session) and is_open(session):
            notify(topic, session, "registration is now open")
            sent += 1

    print(f"Sent {sent} notification(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
