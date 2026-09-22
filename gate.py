"""Human gate for irreversible actions. Email content cannot call these without going through here."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config
import trace

# Classification documented in CAPABILITIES.md
IRREVERSIBLE = {"send", "delete"}
REVERSIBLE = {"draft", "label", "archive", "defer", "escalate", "flag", "delegate"}


def _gate_log(entry: dict) -> None:
    path = config.GATE_LOG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def require_approval(
    action: str,
    proposal: dict[str, Any],
    *,
    dry_run: bool | None = None,
    auto_approve: bool | None = None,
    cap: str | None = None,
    prompt: bool = True,
) -> dict[str, Any]:
    """
    Gate every irreversible action.
    dry_run=True → show what would happen, perform nothing.
    Otherwise ask y/n (or auto_approve for non-interactive demos that still log).
    """
    if action not in IRREVERSIBLE:
        return {"allowed": True, "decision": "n/a_reversible", "action": action}

    dry = config.DEFAULT_DRY_RUN if dry_run is None else dry_run
    auto = config.AUTO_APPROVE if auto_approve is None else auto_approve

    proposed = {
        "action": action,
        "proposal": proposal,
        "ts": datetime.now(timezone.utc).isoformat(),
    }

    if dry:
        decision = "dry-run_suppressed"
        allowed = False
        human = "dry-run"
        print(f"[GATE dry-run] WOULD {action}: {json.dumps(proposal, ensure_ascii=False)[:200]}")
    elif auto:
        decision = "auto_approved"
        allowed = True
        human = "auto-approve"
        print(f"[GATE auto] approved {action} for {proposal.get('to') or proposal.get('message_id')}")
    elif prompt:
        print(f"\n[GATE] Proposed IRREVERSIBLE action: {action}")
        print(json.dumps(proposal, indent=2, ensure_ascii=False)[:800])
        ans = input("Approve? [y/N]: ").strip().lower()
        human = ans or "n"
        allowed = ans in {"y", "yes"}
        decision = "approved" if allowed else "denied"
    else:
        decision = "denied_no_prompt"
        allowed = False
        human = "no-prompt"

    record = {
        **proposed,
        "human": human,
        "decision": decision,
        "allowed": allowed,
        "cap": cap,
    }
    _gate_log(record)
    trace.log(
        "gate",
        cap=cap,
        action=action,
        decision=decision,
        allowed=allowed,
        proposal_summary={
            k: proposal.get(k) for k in ("message_id", "to", "subject", "path") if k in proposal
        },
    )
    return record


def send_message(
    *,
    to: str,
    subject: str,
    body: str,
    in_reply_to: str | None = None,
    cc: list[str] | None = None,
    dry_run: bool | None = None,
    auto_approve: bool | None = None,
    cap: str | None = None,
    prompt: bool = True,
) -> dict[str, Any]:
    """Only path that writes to outbox/. Always gated."""
    proposal = {
        "message_id": in_reply_to,
        "to": to,
        "cc": cc or [],
        "subject": subject,
        "body_preview": body[:240],
    }
    gate = require_approval(
        "send",
        proposal,
        dry_run=dry_run,
        auto_approve=auto_approve,
        cap=cap,
        prompt=prompt,
    )
    if not gate["allowed"]:
        return {"sent": False, "gate": gate, "path": None}

    config.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    fname = f"{stamp}_{in_reply_to or 'out'}.json"
    path = config.OUTBOX_DIR / fname
    payload = {
        "from": config.OWNER_EMAIL,
        "to": to,
        "cc": cc or [],
        "subject": subject,
        "body": body,
        "in_reply_to": in_reply_to,
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    trace.log("send", cap=cap, path=str(path), to=to, in_reply_to=in_reply_to)
    return {"sent": True, "gate": gate, "path": str(path), "payload": payload}


def delete_message(
    message_id: str,
    *,
    dry_run: bool | None = None,
    auto_approve: bool | None = None,
    cap: str | None = None,
    prompt: bool = True,
) -> dict[str, Any]:
    """Deletes are irreversible in this design (no trash). Always gated; rarely used."""
    proposal = {"message_id": message_id, "note": "no trash — permanent in mock store"}
    gate = require_approval(
        "delete",
        proposal,
        dry_run=dry_run,
        auto_approve=auto_approve,
        cap=cap,
        prompt=prompt,
    )
    # We never actually delete from inbox.json; even if approved we only log intent.
    if gate["allowed"]:
        trace.log("delete_intent", cap=cap, message_id=message_id, note="logged only; inbox left intact")
    return {"deleted": False, "gate": gate, "note": "inbox left intact; delete is gated and not auto-applied to hostile mail"}


def count_outbox() -> int:
    if not config.OUTBOX_DIR.exists():
        return 0
    return len(list(config.OUTBOX_DIR.glob("*.json")))
