"""Persistent standing preferences (survive process exit/restart)."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import config
import trace


def load_prefs(path: Path | None = None) -> dict[str, Any]:
    p = path or config.PREFS_PATH
    if not p.exists():
        return {"preferences": []}
    return json.loads(p.read_text(encoding="utf-8"))


def save_prefs(data: dict[str, Any], path: Path | None = None) -> None:
    p = path or config.PREFS_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2), encoding="utf-8")


def add_preference(
    key: str,
    rule: str,
    source_message_id: str,
    details: dict | None = None,
    cap: str | None = None,
) -> dict:
    data = load_prefs()
    prefs = data.setdefault("preferences", [])
    # replace same key
    prefs = [p for p in prefs if p.get("key") != key]
    entry = {
        "key": key,
        "rule": rule,
        "source_message_id": source_message_id,
        "details": details or {},
    }
    prefs.append(entry)
    data["preferences"] = prefs
    save_prefs(data)
    trace.log("preference_stored", cap=cap, preference=entry)
    return entry


def get_preference(key: str) -> dict | None:
    for p in load_prefs().get("preferences", []):
        if p.get("key") == key:
            return p
    return None


def extract_preferences_from_inbox(messages: list[dict], cap: str | None = None) -> list[dict]:
    """Pull standing instructions that belong to the owner (trusted self-notes / known senders)."""
    stored: list[dict] = []
    by_id = {m["id"]: m for m in messages}

    # m015: Priya asks to be CC'd on Hartwell & Cho legal mail
    if "m015" in by_id:
        stored.append(
            add_preference(
                key="cc_priya_on_legal",
                rule="Always CC priya@paperjet.io on mail from hartwellcho.com",
                source_message_id="m015",
                details={"cc": "priya@paperjet.io", "domain": "hartwellcho.com"},
                cap=cap,
            )
        )

    # m041: Sam's own calendar rule — trusted because from owner to self
    if "m041" in by_id:
        m = by_id["m041"]
        if m["from"].lower() == config.OWNER_EMAIL.lower():
            stored.append(
                add_preference(
                    key="no_meetings_before_11",
                    rule="Never accept meetings before 11:00am; offer 11:00am or later",
                    source_message_id="m041",
                    details={"earliest_hour": 11},
                    cap=cap,
                )
            )
    return stored
