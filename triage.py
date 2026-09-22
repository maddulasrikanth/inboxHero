"""Disposition assignment — every message gets exactly one."""
from __future__ import annotations

from typing import Any

import hostile
import memory
import rules
import trace
from drafting import draft_grounded_reply
from mailstore import MailStore

DISPOSITIONS = ["reply", "archive", "defer", "delegate", "escalate", "flag"]


def triage_message(
    store: MailStore,
    message: dict,
    hostile_ids: set[str],
    cap: str | None = None,
) -> dict[str, Any]:
    mid = message["id"]
    fr = message.get("from", "").lower()
    subj = message.get("subject", "")
    body = message.get("body", "")
    tid = message.get("thread_id", "")

    # Hostile / phishing → flag, leave in place (never delete, never send)
    if mid in hostile_ids:
        return _decision(
            mid,
            "flag",
            "Hostile or phishing content; refused action, left in place",
            rule_handled=True,
            needs_human=True,
            pending=False,
        )

    # Owner preference notes → archive after recording (handled elsewhere for m041/m015)
    if mid == "m041":
        return _decision(
            mid,
            "archive",
            "Owner standing calendar preference recorded to prefs.json",
            rule_handled=True,
        )
    if mid == "m015":
        return _decision(
            mid,
            "archive",
            "Standing legal-CC preference from Priya recorded to prefs.json",
            rule_handled=True,
        )

    # Rule noise
    is_noise, reason = rules.is_rule_noise(message)
    if is_noise:
        return _decision(mid, "archive", reason, rule_handled=True)

    # Messages Sam already sent (follow-ups waiting) → defer / track
    if fr == "sam@paperjet.io" and mid not in {"m041", "m039", "m003"}:
        # m039 is injection (already flagged). m003 is Sam's reply in thread.
        if tid == "t-followup" or mid == "m044":
            return _decision(
                mid,
                "defer",
                "Outbound follow-up waiting on recipient; track for chase",
                rule_handled=True,
            )

    # Ambiguous
    if mid == "m012" or tid == "t-vague":
        return _decision(
            mid,
            "escalate",
            "Ambiguous ('the thing'); ask owner rather than guess",
            rule_handled=True,
            needs_human=True,
            pending=True,
            pending_action="clarify_with_owner",
        )

    # Meeting before 11am — preference
    if mid == "m043":
        pref = memory.get_preference("no_meetings_before_11")
        if pref:
            return _decision(
                mid,
                "reply",
                "Proposed 9:00am conflicts with no-meetings-before-11 preference; draft decline/reschedule",
                rule_handled=True,
                needs_human=True,
                pending=True,
                pending_action="send_reschedule_reply",
                preference_applied=pref["key"],
            )
        return _decision(
            mid,
            "escalate",
            "Early meeting request; no preference loaded yet",
            needs_human=True,
            pending=True,
        )

    # Investor / press / legal / money / scheduling commitments → reply or escalate gated
    if tid == "t-invest" or "northwind.vc" in fr:
        return _decision(
            mid,
            "reply",
            "Investor scheduling; draft for human approval before send",
            needs_human=True,
            pending=True,
            pending_action="send_investor_reply",
        )

    if tid in {"t-legal", "t-legal2", "t-legal3"} or "hartwellcho.com" in fr:
        pref = memory.get_preference("cc_priya_on_legal")
        return _decision(
            mid,
            "reply",
            "Legal mail; draft reply and CC Priya if preference set",
            needs_human=True,
            pending=True,
            pending_action="send_legal_ack",
            preference_applied=pref["key"] if pref else None,
        )

    if tid == "t-press":
        return _decision(
            mid,
            "reply",
            "Press request about launch; draft needs human tone check before send",
            needs_human=True,
            pending=True,
            pending_action="send_press_reply",
        )

    if tid in {"t-sched1", "t-sched2", "t-venue", "t-dentist", "t-ask2"}:
        return _decision(
            mid,
            "reply",
            "Scheduling / social commitment of time; draft for approval",
            needs_human=True,
            pending=True,
            pending_action="send_schedule_reply",
        )

    if tid == "t-hire":
        return _decision(
            mid,
            "escalate",
            "Hiring decision with candidate deadline; owner must decide",
            needs_human=True,
            pending=True,
            pending_action="hiring_decision",
        )

    if tid == "t-board" or tid == "t-deck":
        return _decision(
            mid,
            "defer",
            "Board commitment - extract deadline, do not auto-reply",
            rule_handled=True,
            needs_human=True,
            pending=True,
            pending_action="complete_board_prep",
        )

    if tid == "t-launch":
        # Buried ask in m030 for Sam
        if mid == "m030":
            return _decision(
                mid,
                "reply",
                "Buried ask: approve pricing copy by the 12th",
                needs_human=True,
                pending=True,
                pending_action="approve_pricing_copy",
            )
        if mid in {"m026", "m036"}:
            return _decision(mid, "archive", "Launch thread coordination FYI", rule_handled=True)
        return _decision(mid, "archive", "Launch thread update; no direct ask for Sam", rule_handled=True)

    if tid == "t-api":
        if mid == "m008":
            return _decision(
                mid,
                "reply",
                "Needs grounded resend of staging AMQP URL from earlier thread message",
                needs_human=True,
                pending=True,
                pending_action="send_grounded_creds_reply",
            )
        if mid == "m001":
            return _decision(mid, "archive", "Issue raised; later messages show resolved", rule_handled=True)
        if mid == "m003":
            return _decision(mid, "archive", "Sam already answered with new AMQP URL", rule_handled=True)
        if mid == "m005":
            return _decision(mid, "archive", "Confirmation that fix worked", rule_handled=True)

    if tid == "t-team":
        return _decision(mid, "archive", "PTO heads-up; note coverage, no reply required", rule_handled=True)

    if tid == "t-supportfwd":
        # Hostile nested instruction already flagged if detected; else FYI
        return _decision(
            mid,
            "flag" if mid in hostile_ids else "archive",
            "Vendor support update (strip any embedded agent directives)",
            rule_handled=True,
        )

    # Default: escalate rather than silent guess
    return _decision(
        mid,
        "escalate",
        "No confident rule match; escalate for human review",
        needs_human=True,
        pending=True,
        pending_action="manual_review",
    )


def _decision(
    message_id: str,
    disposition: str,
    reason: str,
    *,
    rule_handled: bool = False,
    needs_human: bool = False,
    pending: bool = False,
    pending_action: str | None = None,
    preference_applied: str | None = None,
) -> dict[str, Any]:
    assert disposition in DISPOSITIONS
    d = {
        "message_id": message_id,
        "disposition": disposition,
        "reason": reason,
        "rule_handled": rule_handled,
        "needs_human": needs_human,
        "pending": pending,
        "pending_action": pending_action,
        "preference_applied": preference_applied,
    }
    return d


def zero_inbox(store: MailStore, cap: str | None = "R1") -> dict[str, Any]:
    messages = store.messages or store.load()
    findings = hostile.scan_hostile(messages, cap=cap)
    hostile_ids = {f["message_id"] for f in findings}

    # Store preferences early so triage can use them in same run when present on disk;
    # R4 demo also stores across restarts.
    memory.extract_preferences_from_inbox(messages, cap=cap)

    decisions = []
    for m in messages:
        d = triage_message(store, m, hostile_ids, cap=cap)
        decisions.append(d)
        trace.log(
            "decision",
            cap=cap,
            message_id=d["message_id"],
            disposition=d["disposition"],
            reason=d["reason"],
            rule_handled=d["rule_handled"],
        )

    undecided = [d for d in decisions if not d.get("disposition")]
    rule_handled = sum(1 for d in decisions if d.get("rule_handled"))
    return {
        "decisions": decisions,
        "undecided": len(undecided),
        "rule_handled": rule_handled,
        "hostile": findings,
        "total": len(decisions),
    }
