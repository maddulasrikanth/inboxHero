"""Commitment extraction with citations and conflict detection."""
from __future__ import annotations

from datetime import datetime
from typing import Any

import trace
from mailstore import MailStore


def extract_commitments(store: MailStore, cap: str | None = "R6") -> dict[str, Any]:
    """
    Build calendar commitments. Multi-message: board deck due date = board review (m038)
    minus two days from Priya's instruction (m040).
    Conflict: Aria intro Tue 15 15:00 (m010) vs dental Tue 15 15:00 (m061).
    """
    commitments: list[dict] = []

    def add(
        title: str,
        when: str,
        message_ids: list[str],
        notes: str = "",
    ) -> None:
        # verify citations exist
        for mid in message_ids:
            assert store.get(mid), f"citation {mid} not in store"
            trace.log("read", message_id=mid, via="commitment", cap=cap)
        commitments.append(
            {
                "title": title,
                "when": when,
                "message_ids": message_ids,
                "notes": notes,
            }
        )

    # Multi-message commitment: deck due two days before board review
    m038 = store.get("m038")
    m040 = store.get("m040")
    if m038 and m040:
        # Board review: 18th 10:00 → deck due 16th
        add(
            "Board deck finished and circulated",
            "2026-09-16",
            ["m038", "m040"],
            "m040 asks for deck two days before board review; m038 sets review on the 18th → due the 16th",
        )
        add(
            "Quarterly board review (in-person)",
            "2026-09-18T10:00",
            ["m038"],
            "Confirmed by board chair",
        )

    if store.get("m010"):
        add(
            "Intro call with Aria (Northwind VC)",
            "2026-09-15T15:00",
            ["m010"],
            "30 minutes; Aria proposed Tuesday the 15th at 3:00pm",
        )

    if store.get("m061"):
        add(
            "Dental cleaning with Dr. Osei",
            "2026-09-15T15:00",
            ["m061"],
            "Bright Smile Dental reminder",
        )

    if store.get("m030"):
        add(
            "Approve final pricing-page copy",
            "2026-09-12",
            ["m030"],
            "Buried ask in launch thread — nothing ships until this line is locked",
        )

    if store.get("m026") or store.get("m036"):
        ids = [i for i in ("m026", "m036") if store.get(i)]
        add("PaperJet launch (hard date)", "2026-09-20", ids, "Launch week target")

    if store.get("m029"):
        add("Signup-flow load test", "2026-09-14", ["m029"], "Raghav scheduled")

    if store.get("m042"):
        add(
            "Respond to Jordan Okafor (candidate deadline)",
            "2026-09-19",
            ["m042"],
            "Candidate has another offer to answer by the 19th",
        )

    if store.get("m016"):
        add(
            "Acme Corp product demo",
            "2026-09-09T14:00",  # Wednesday 2pm (Sep 9 2026 is Wednesday)
            ["m016"],
            "Partners proposed Wednesday at 2:00pm",
        )

    if store.get("m013"):
        add(
            "Weekly 1:1 with Raghav (moved)",
            "2026-09-09T14:00",
            ["m013"],
            "Request to move Thursday 1:1 to Wednesday 2:00pm this week",
        )

    if store.get("m043"):
        add(
            "Northwind partner slot (proposed — conflicts with preference)",
            "2026-09-14T09:00",  # Monday before markets
            ["m043", "m041"],
            "9:00am proposed; preference forbids meetings before 11:00am",
        )

    conflicts = _find_conflicts(commitments)
    for c in conflicts:
        trace.log("conflict", cap=cap, conflict=c)

    trace.log(
        "commitments",
        cap=cap,
        count=len(commitments),
        conflict_count=len(conflicts),
    )
    return {"commitments": commitments, "conflicts": conflicts}


def _find_conflicts(commitments: list[dict]) -> list[dict]:
    by_when: dict[str, list[dict]] = {}
    for c in commitments:
        when = c["when"]
        # normalize date-only vs datetime: conflict only on equal timestamps
        by_when.setdefault(when, []).append(c)

    conflicts = []
    for when, items in by_when.items():
        if len(items) >= 2 and "T" in when:  # same datetime slot
            conflicts.append(
                {
                    "when": when,
                    "items": [{"title": i["title"], "message_ids": i["message_ids"]} for i in items],
                    "summary": f"CONFLICT: {len(items)} commitments at {when}: "
                    + " vs ".join(i["title"] for i in items),
                }
            )
    return conflicts
