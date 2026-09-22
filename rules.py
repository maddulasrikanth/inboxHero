"""Rule-based triage for obvious noise — no LLM required."""
from __future__ import annotations

import re

NOISE_THREAD_PREFIXES = ("t-noise-",)
NOISE_SENDER_FRAGMENTS = (
    "no-reply@",
    "noreply@",
    "no_reply@",
    "notifications@",
    "alerts@",
    "receipts@",
    "billing@",
    "orders@",
    "newsletter@",
    "digest@",
    "mailer-daemon@",
    "calendar-notification@",
    "invoice+",
    "feedback@",
    "updates@",
    "insights@",
    "checkin@",
    "status@",
    "ship-confirm@",
    "info@members.",
    "info@twitter.",
)

NOISE_SUBJECT_PATTERNS = [
    re.compile(r"\breceipt\b", re.I),
    re.compile(r"\binvoice\b", re.I),
    re.compile(r"\bstatement\b", re.I),
    re.compile(r"\bnewsletter\b", re.I),
    re.compile(r"daily digest|weekly digest|screen time|security digest", re.I),
    re.compile(r"your .+ (bill|invoice|receipt|order|payout|statement)", re.I),
    re.compile(r"cloud recording is ready|monitor OK|incident resolved", re.I),
    re.compile(r"unread messages in #|appeared in \d+ searches", re.I),
    re.compile(r"verification code is \d+", re.I),
    re.compile(r"new (sign-in|login)|password was changed", re.I),
    re.compile(r"flight check-in|timesheet|office closed|1:1 notes", re.I),
]

FYI_ONLY = {
    "t-fyi1",  # uptime report
    "t-support2",  # dispute opened, no action
    "t-vendor",  # renewal notice FYI
    "t-fill-117",
    "t-fill-118",
    "t-fill-119",
}


def is_rule_noise(message: dict) -> tuple[bool, str]:
    tid = message.get("thread_id", "")
    fr = message.get("from", "").lower()
    subj = message.get("subject", "")

    if tid.startswith(NOISE_THREAD_PREFIXES):
        return True, "automated noise thread (receipt/newsletter/alert)"
    if tid in FYI_ONLY:
        return True, "FYI-only status/system notice, no reply needed"
    if any(frag in fr for frag in NOISE_SENDER_FRAGMENTS) and tid.startswith("t-noise"):
        return True, "no-reply / notification sender"
    if tid.startswith("t-fill-"):
        return True, "internal FYI / fill message"
    for pat in NOISE_SUBJECT_PATTERNS:
        if pat.search(subj) and (
            any(frag in fr for frag in NOISE_SENDER_FRAGMENTS) or tid.startswith("t-noise")
        ):
            return True, f"matches noise subject pattern ({pat.pattern[:40]})"
    return False, ""
