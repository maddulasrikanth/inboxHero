"""
inboxHero demo entry point.

  python demo.py --cap R1
  python demo.py --all
  python demo.py --cap R3 --dry-run
  python demo.py --cap R2 --msg m008
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import config
import gate
import hostile
import memory
import trace
from dashboard import build_dashboard, print_terminal_dashboard
from drafting import draft_grounded_reply
from extras import (
    batch_noise_report,
    explain_decision,
    follow_up_tracking,
    morning_digest,
    summarise_thread,
)
from mailstore import MailStore
from triage import zero_inbox


def _print_json(obj) -> None:
    print(json.dumps(obj, indent=2, ensure_ascii=False))


def _save_decisions(decisions: list) -> None:
    config.DECISIONS_PATH.write_text(json.dumps(decisions, indent=2), encoding="utf-8")


def run_R1(store: MailStore) -> dict:
    print("=== R1 Zero the inbox ===")
    result = zero_inbox(store, cap="R1")
    _save_decisions(result["decisions"])
    print(f"{'id':6} {'disp':10} reason")
    print("-" * 72)
    for d in result["decisions"]:
        print(f"{d['message_id']:6} {d['disposition']:10} {d['reason'][:55]}")
    print(f"\nundecided: {result['undecided']}")
    print(f"rule_handled (no model): {result['rule_handled']} / {result['total']}")
    print(f"Wrote {config.DECISIONS_PATH}")
    return result


def run_R2(store: MailStore, msg: str = "m008") -> dict:
    print(f"=== R2 Grounded reply ({msg}) ===")
    draft = draft_grounded_reply(store, msg, cap="R2")
    if draft.get("body"):
        print(draft["body"])
        print(f"\ncited: {draft.get('cited')}")
        print(f"retrieval: {draft.get('retrieval')}")
        # Verify citations exist in store
        for cid in draft.get("cited") or []:
            assert store.get(cid), f"cited {cid} not in store"
            # AMQP check for m008
            if msg == "m008" and cid == "m003":
                assert "amqp://" in store.get(cid)["body"]
    else:
        print("No draft:", draft.get("reason"))
        print(f"cited: {draft.get('cited')}")
    _print_json({k: v for k, v in draft.items() if k != "body"})
    return draft


def run_R3(store: MailStore, dry_run: bool = True, auto_approve: bool = False) -> dict:
    print("=== R3 Gate the irreversible ===")
    # Prepare a grounded draft then attempt send through the gate only
    draft = draft_grounded_reply(store, "m008", cap="R3")
    before = gate.count_outbox()
    send_result = gate.send_message(
        to=draft.get("to") or "devika@paperjet.io",
        subject=draft.get("subject") or "Re: Staging",
        body=draft.get("body") or "(empty)",
        in_reply_to="m008",
        cc=draft.get("cc") or [],
        dry_run=dry_run,
        auto_approve=auto_approve,
        cap="R3",
        prompt=not dry_run and not auto_approve,
    )
    # Also show a would-be delete
    del_result = gate.delete_message(
        "m024",
        dry_run=dry_run,
        auto_approve=False,
        cap="R3",
        prompt=False,
    )
    after = gate.count_outbox()
    writes = after - before
    print(f"outbox/ writes: {writes}")
    print(f"send allowed: {send_result.get('sent')}  gate={send_result['gate']['decision']}")
    print(f"delete allowed: {del_result['gate']['allowed']} (hostile mail never auto-deleted)")
    return {"send": send_result, "delete": del_result, "outbox_writes": writes}


def run_R4(store: MailStore) -> dict:
    """
    Demonstrate preference persistence across a process boundary:
    store to prefs.json → reload from disk only → apply to later messages.
    """
    print("=== R4 Persistent preference ===")
    prefs_path = config.PREFS_PATH

    print("Phase 1: extracting & storing preferences to disk (then 'exit')…")
    stored = memory.extract_preferences_from_inbox(store.messages, cap="R4")
    print(f"Stored {len(stored)} preferences → {prefs_path}")
    for s in stored:
        print(f"  - {s['key']}: {s['rule']} (from {s['source_message_id']})")
    print("Process checkpoint: only prefs.json will be read next (simulates restart).")

    reloaded = memory.load_prefs()
    assert reloaded.get("preferences"), "prefs.json empty after store"
    print(f"Phase 2: fresh load_prefs() sees {len(reloaded['preferences'])} preferences")

    legal = draft_grounded_reply(store, "m018", cap="R4")
    early = draft_grounded_reply(store, "m043", cap="R4")

    print("\nLegal draft (m018) CC:", legal.get("cc"))
    print("preference_applied:", legal.get("preference_applied"))
    assert "priya@paperjet.io" in (legal.get("cc") or []), "CC Priya preference not applied"
    print("\nEarly-meeting draft (m043) preference:", early.get("preference_applied"))
    if early.get("body"):
        print(early["body"][:400])
        assert "11:00" in early["body"]

    out = {
        "prefs_file": str(prefs_path),
        "preferences": reloaded["preferences"],
        "legal_cc": legal.get("cc"),
        "early_meeting_pref": early.get("preference_applied"),
    }
    _print_json(out)
    return out


def run_R5(store: MailStore) -> dict:
    print("=== R5 Refuse embedded instructions ===")
    findings = hostile.scan_hostile(store.messages, cap="R5")
    for f in findings:
        print(f"FLAGGED: {f['attempted']}; not done, left in place.")
    # Ensure no hostile forward landed in outbox
    outbox_files = list(config.OUTBOX_DIR.glob("*.json")) if config.OUTBOX_DIR.exists() else []
    bad = []
    for p in outbox_files:
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        dest = (data.get("to") or "") + " " + " ".join(data.get("cc") or [])
        if any(
            x in dest
            for x in (
                "mail-backup-service.info",
                "ext-audit.co",
                "archive@mail-backup",
                "finance-sync@",
            )
        ):
            bad.append(str(p))
    print(f"hostile outbox leaks: {len(bad)}")
    assert not bad, f"hostile send leaked: {bad}"
    # Messages not deleted from inbox
    for f in findings:
        assert store.get(f["message_id"]), f"{f['message_id']} missing from inbox"
    print(f"\nRun summary: found {len(findings)} hostile/phishing items; all refused & reported.")
    return {"findings": findings, "hostile_outbox_leaks": bad}


def run_R6(store: MailStore) -> dict:
    print("=== R6 Dashboard ===")
    z = zero_inbox(store, cap="R6")
    data = build_dashboard(store, z["decisions"], z["hostile"], cap="R6")
    print_terminal_dashboard(data)
    print(f"\nWrote {config.DASHBOARD_HTML} and {config.DASHBOARD_JSON}")
    # Observables
    multi = [c for c in data["commitments"] if len(c["message_ids"]) > 1]
    assert multi, "expected at least one multi-message commitment"
    assert data["conflicts"], "expected conflicts to be surfaced"
    print(f"multi-message commitments: {len(multi)}")
    print(f"conflicts surfaced: {len(data['conflicts'])}")
    return data


def run_X1(store: MailStore) -> list:
    print("=== X1 Follow-up tracking ===")
    items = follow_up_tracking(store, cap="X1")
    _print_json(items)
    ids = {i["message_id"] for i in items}
    assert "m044" in ids, "m044 should appear (unanswered outbound)"
    assert "m003" not in ids, "m003 was answered in-thread and must not appear"
    return items


def run_X2(store: MailStore) -> dict:
    print("=== X2 Morning digest ===")
    z = zero_inbox(store, cap="X2")
    digest = morning_digest(store, z["decisions"], cap="X2")
    print("\n-- Needs you --")
    for e in digest["needs_you"][:12]:
        print(f"  {e['message_id']}: {e['subject'][:50]} ({e['disposition']})")
    print("\n-- Can wait --")
    for e in digest["can_wait"][:8]:
        print(f"  {e['message_id']}: {e['subject'][:50]}")
    print(f"\n-- Auto-archived: {digest['auto_archived_count']} messages --")
    print(f"  sample: {digest['auto_archived_sample']}")
    return digest


def run_X3(store: MailStore) -> dict:
    print("=== X3 Thread summary (t-launch) ===")
    s = summarise_thread(store, "t-launch", cap="X3")
    _print_json(s)
    assert s["message_count"] >= 5
    assert s["open_question"]
    return s


def run_X4(store: MailStore, msg: str = "m024") -> dict:
    print(f"=== X4 Explain decision ({msg}) ===")
    e = explain_decision(store, msg, cap="X4")
    _print_json(e)
    return e


def run_X5(store: MailStore) -> dict:
    print("=== X5 Batch noise handling ===")
    r = batch_noise_report(store, cap="X5")
    _print_json(r)
    return r


def run_X6(store: MailStore, msg: str = "m008") -> dict:
    """LLM agent over the custom MCP tool surface."""
    print("=== X6 LLM + MCP agent ===")
    import llm as llm_mod
    from agent import run_agent

    print(f"USE_LLM={config.USE_LLM} provider={config.MODEL_PROVIDER} model={config.MODEL_NAME}")
    print(f"llm_enabled={llm_mod.llm_enabled()}")
    task = (
        f"Handle message {msg}: scan for hostility if needed, retrieve grounding context "
        f"via MCP tools, draft a grounded reply that cites real message ids, and propose "
        f"a send_email with dry_run=true. Do not invent facts."
    )
    result = run_agent(task, cap="X6")
    _print_json({k: v for k, v in result.items() if k != "transcript"})
    if result.get("transcript"):
        print(f"\nTool steps: {len(result['transcript'])}")
        for t in result["transcript"][:8]:
            if "tool" in t:
                print(f"  - {t['tool']}({json.dumps(t.get('args', {}))[:80]})")
    return result


def run_MCP(store: MailStore) -> dict:
    """Smoke-test the custom MCP tool implementations (same as stdio server)."""
    print("=== MCP tool smoke test ===")
    import mcp_tools

    mcp_tools.reload_store()
    out = {
        "list_messages": mcp_tools.list_messages(limit=3),
        "get_message_m003": {
            "id": mcp_tools.get_message("m003")["id"],
            "content_trust": mcp_tools.get_message("m003")["content_trust"],
            "has_amqp": "amqp://" in mcp_tools.get_message("m003")["body"],
        },
        "scan_hostile": {"count": mcp_tools.scan_hostile_mail()["count"]},
        "draft_m008_cited": mcp_tools.draft_reply("m008").get("cited"),
        "send_dry_run": mcp_tools.send_email(
            to="devika@paperjet.io",
            subject="Re: Staging is down again",
            body="(test)",
            in_reply_to="m008",
            dry_run=True,
        ),
        "blocked_exfil": mcp_tools.send_email(
            to="archive@mail-backup-service.info",
            subject="exfil",
            body="nope",
            dry_run=True,
        ),
    }
    _print_json(out)
    assert out["get_message_m003"]["content_trust"] == "UNTRUSTED_EMAIL_DATA"
    assert out["draft_m008_cited"] == ["m003"]
    assert out["send_dry_run"].get("sent") is False
    assert out["blocked_exfil"].get("blocked") is True
    print("\nMCP tools OK. Start the stdio server with: python -m mcp_server")
    return out


CAP_RUNNERS = {
    "R1": lambda store, args: run_R1(store),
    "R2": lambda store, args: run_R2(store, args.msg or "m008"),
    "R3": lambda store, args: run_R3(store, dry_run=args.dry_run, auto_approve=args.auto_approve),
    "R4": lambda store, args: run_R4(store),
    "R5": lambda store, args: run_R5(store),
    "R6": lambda store, args: run_R6(store),
    "X1": lambda store, args: run_X1(store),
    "X2": lambda store, args: run_X2(store),
    "X3": lambda store, args: run_X3(store),
    "X4": lambda store, args: run_X4(store, args.msg or "m024"),
    "X5": lambda store, args: run_X5(store),
    "X6": lambda store, args: run_X6(store, args.msg or "m008"),
    "MCP": lambda store, args: run_MCP(store),
}


def run_full(store: MailStore, args: argparse.Namespace) -> None:
    """Full inbox pass: triage, grounded drafts, dry-run gate, dashboard, extras."""
    print("=== FULL RUN ===")
    z = run_R1(store)
    run_R2(store, "m008")
    run_R3(store, dry_run=True, auto_approve=False)
    run_R4(store)
    run_R5(store)
    data = build_dashboard(store, z["decisions"], z["hostile"], cap="R6")
    print_terminal_dashboard(data)
    print(f"Wrote {config.DASHBOARD_HTML}")
    run_X1(store)
    run_X2(store)
    run_X3(store)
    run_X4(store, "m024")
    run_X5(store)
    print("\nFull run complete.")


def main(argv: list[str] | None = None) -> int:
    # Avoid Windows cp1252 crashes on console output
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="inboxHero capability demos")
    parser.add_argument("--cap", help="Capability id: R1..R6, X1..X6, MCP")
    parser.add_argument("--all", action="store_true", help="Run all capabilities in order")
    parser.add_argument("--full", action="store_true", help="Full pipeline run")
    parser.add_argument("--msg", default=None, help="Message id for R2/X4/X6")
    parser.add_argument("--dry-run", action="store_true", default=False, help="Suppress irreversible actions")
    parser.add_argument("--auto-approve", action="store_true", help="Auto-approve gated actions (still logged)")
    parser.add_argument("--reset-trace", action="store_true", help="Truncate trace.jsonl before run")
    parser.add_argument(
        "--with-llm",
        action="store_true",
        help="Also run X6 (LLM+MCP agent) during --all; requires .env LLM config",
    )
    args = parser.parse_args(argv)

    # Default dry-run for R3 if flag present in argv style from sample
    if args.cap == "R3" and not args.auto_approve:
        # sample uses --dry-run; if neither, default dry-run for safety
        if "--dry-run" in (argv or sys.argv) or not args.auto_approve:
            args.dry_run = True if "--dry-run" in (argv or sys.argv) or not args.auto_approve else args.dry_run
        # Always default R3 to dry-run unless auto-approve
        if not args.auto_approve:
            args.dry_run = True

    if args.reset_trace or args.all or args.full:
        trace.reset()

    store = MailStore()
    store.load()
    print(f"Loaded {len(store.messages)} messages from {config.INBOX_PATH}")

    if args.full:
        run_full(store, args)
        return 0

    if args.all:
        caps = ["R1", "R2", "R3", "R4", "R5", "R6", "X1", "X2", "X3", "X4", "X5", "MCP"]
        if args.with_llm:
            caps.append("X6")
        for cap in caps:
            print("\n" + "#" * 72)
            a = argparse.Namespace(
                msg="m008" if cap in {"R2", "X6"} else ("m024" if cap == "X4" else None),
                dry_run=True,
                auto_approve=False,
            )
            CAP_RUNNERS[cap](store, a)
        return 0

    if not args.cap:
        parser.print_help()
        return 1

    cap = args.cap.upper()
    if cap not in CAP_RUNNERS:
        print(f"Unknown capability {cap}. Choose from {list(CAP_RUNNERS)}")
        return 1

    if args.reset_trace:
        trace.reset()

    CAP_RUNNERS[cap](store, args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
