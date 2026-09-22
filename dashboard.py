"""Three-pane dashboard: pending actions, flagged, commitments."""
from __future__ import annotations

import html
import json
from typing import Any

import config
import trace
from commitments import extract_commitments
from mailstore import MailStore


def build_dashboard(
    store: MailStore,
    decisions: list[dict],
    hostile: list[dict],
    cap: str | None = "R6",
) -> dict[str, Any]:
    by_id = {m["id"]: m for m in store.messages}

    pending = []
    for d in decisions:
        if not d.get("pending"):
            continue
        m = by_id.get(d["message_id"], {})
        pending.append(
            {
                "message_id": d["message_id"],
                "from": m.get("from", ""),
                "subject": m.get("subject", ""),
                "proposed_action": d.get("pending_action") or d["disposition"],
                "why_human": d["reason"],
            }
        )

    flagged = []
    for f in hostile:
        flagged.append(
            {
                "message_id": f["message_id"],
                "kind": f.get("kind"),
                "attempted": f.get("attempted"),
                "system_did": f.get("action", "refused_flagged_left_in_place"),
            }
        )
    # Also surface ungroundable / escalate-without-draft
    for d in decisions:
        if d["disposition"] == "escalate" and d["message_id"] not in {f["message_id"] for f in flagged}:
            if "Ambiguous" in d["reason"] or "not" in d["reason"].lower():
                flagged.append(
                    {
                        "message_id": d["message_id"],
                        "kind": "ungrounded",
                        "attempted": "infer intent / auto-reply",
                        "system_did": f"escalated: {d['reason']}",
                    }
                )

    cal = extract_commitments(store, cap=cap)

    payload = {
        "pending_actions": pending,
        "flagged": flagged,
        "commitments": cal["commitments"],
        "conflicts": cal["conflicts"],
    }

    config.DASHBOARD_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    config.DASHBOARD_HTML.write_text(_render_html(payload), encoding="utf-8")
    trace.log(
        "dashboard",
        cap=cap,
        pending=len(pending),
        flagged=len(flagged),
        commitments=len(cal["commitments"]),
        conflicts=len(cal["conflicts"]),
    )
    return payload


def _render_html(data: dict) -> str:
    def rows_pending(items):
        if not items:
            return "<tr><td colspan='4'>(none)</td></tr>"
        out = []
        for i in items:
            out.append(
                "<tr>"
                f"<td>{html.escape(i['message_id'])}</td>"
                f"<td>{html.escape(i.get('subject',''))}<br><small>{html.escape(i.get('from',''))}</small></td>"
                f"<td>{html.escape(str(i.get('proposed_action','')))}</td>"
                f"<td>{html.escape(i.get('why_human',''))}</td>"
                "</tr>"
            )
        return "\n".join(out)

    def rows_flagged(items):
        if not items:
            return "<tr><td colspan='4'>(none)</td></tr>"
        out = []
        for i in items:
            out.append(
                "<tr>"
                f"<td>{html.escape(i['message_id'])}</td>"
                f"<td>{html.escape(str(i.get('kind','')))}</td>"
                f"<td>{html.escape(str(i.get('attempted','')))}</td>"
                f"<td>{html.escape(str(i.get('system_did','')))}</td>"
                "</tr>"
            )
        return "\n".join(out)

    def rows_commitments(items, conflicts):
        out = []
        for i in items:
            cites = ", ".join(i.get("message_ids", []))
            out.append(
                "<tr>"
                f"<td>{html.escape(i.get('when',''))}</td>"
                f"<td>{html.escape(i.get('title',''))}</td>"
                f"<td>[{html.escape(cites)}]</td>"
                f"<td>{html.escape(i.get('notes',''))}</td>"
                "</tr>"
            )
        for c in conflicts:
            out.append(
                f"<tr class='conflict'><td colspan='4'><strong>{html.escape(c['summary'])}</strong></td></tr>"
            )
        return "\n".join(out) if out else "<tr><td colspan='4'>(none)</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>inboxHero Dashboard</title>
<style>
  body {{ font-family: Georgia, 'Times New Roman', serif; margin: 2rem; background: #f7f4ef; color: #1a1a1a; }}
  h1 {{ font-size: 1.6rem; }}
  h2 {{ margin-top: 2rem; border-bottom: 2px solid #333; padding-bottom: 0.3rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 0.5rem; background: #fff; }}
  th, td {{ text-align: left; padding: 0.5rem 0.6rem; border: 1px solid #ddd; vertical-align: top; font-size: 0.92rem; }}
  th {{ background: #e8e2d6; }}
  tr.conflict td {{ background: #ffe0e0; }}
  .pane {{ margin-bottom: 1.5rem; }}
  code {{ background: #eee; padding: 0 0.25rem; }}
</style>
</head>
<body>
<h1>inboxHero — run dashboard</h1>
<p>Reproducible from the last pipeline run. Three panes required by Part 7.</p>

<div class="pane">
<h2>1. Pending actions</h2>
<p>Everything the system wants to do but may not do alone under the irreversible gate.</p>
<table>
<thead><tr><th>Message</th><th>Subject / From</th><th>Proposed action</th><th>Why human</th></tr></thead>
<tbody>
{rows_pending(data.get("pending_actions", []))}
</tbody>
</table>
</div>

<div class="pane">
<h2>2. Flagged</h2>
<p>Hostile injections, phishing, and anything that could not be grounded.</p>
<table>
<thead><tr><th>Message</th><th>Kind</th><th>What was attempted</th><th>What the system did</th></tr></thead>
<tbody>
{rows_flagged(data.get("flagged", []))}
</tbody>
</table>
</div>

<div class="pane">
<h2>3. Commitments</h2>
<p>Dates and obligations with message-id citations. Conflicts are called out, not silent.</p>
<table>
<thead><tr><th>When</th><th>Commitment</th><th>Cited</th><th>Notes</th></tr></thead>
<tbody>
{rows_commitments(data.get("commitments", []), data.get("conflicts", []))}
</tbody>
</table>
</div>
</body>
</html>
"""


def print_terminal_dashboard(data: dict) -> None:
    print("\n=== PENDING ACTIONS ===")
    for i in data.get("pending_actions", []):
        print(f"  {i['message_id']}: {i['proposed_action']} — {i['why_human']}")
    print("\n=== FLAGGED ===")
    for i in data.get("flagged", []):
        print(f"  {i['message_id']} [{i.get('kind')}]: {i.get('attempted')}")
        print(f"    -> {i.get('system_did')}")
    print("\n=== COMMITMENTS ===")
    for i in data.get("commitments", []):
        print(f"  {i['when']}: {i['title']}  cited={i['message_ids']}")
    print("\n=== CONFLICTS ===")
    for c in data.get("conflicts", []):
        print(f"  !! {c['summary']}")
