# CAPABILITIES.md

**Student:** Srikanth Maddula, evernorth-aai-553907  
**Repository:** https://github.com/maddulasrikanth/inboxHero

Run everything through one entry point:

```
python demo.py --cap R1        # one capability
python demo.py --all           # all of them, in the order below
```

---

## The system, in one paragraph

A Python agent with a **custom MCP server** (`python -m mcp_server`) exposing mail tools, plus an optional **LLM** planner (`agent.py` / `llm.py`). Cheap noise is still archived by **rules** before any model call. The LLM (when `USE_LLM=1`) calls MCP tools — `get_message`, `retrieve_context`, `draft_reply`, gated `send_email`, etc. — rather than inventing inbox facts. Hostile / phishing content is detected on **untrusted** message bodies and never reaches a live send. Preferences live in `data/prefs.json`. A final pass writes the three-pane dashboard.

## Design choices you were asked to state

- **Framework: custom MCP + optional LLM (no CrewAI/ADK).** The MCP server is the tool boundary; `agent.py` is a thin tool-calling loop. Rules still handle noise so we do not burn tokens on receipts.
- **Retrieval: thread-walk**, with **keyword search** as cross-thread fallback (also exposed as MCP `get_thread` / `search_messages`).
- **Reversible vs irreversible.** `send` and `delete` are irreversible and gated. `draft`, `label`, `archive`, `defer`, `flag`, `delegate`, `escalate` are reversible (or advisory). **Deleting is irreversible** here because the mock store has no trash.
- **Where the gate sits.** Only `gate.send_message` / `gate.delete_message` (and the MCP `send_email` wrapper) can cause irreversible effects; both call `require_approval()`. Email text cannot invoke them without the gate. Hostile destinations are blocked in the MCP layer too.
- **Escalation line.** Humans approve external sends, money/credential risk, hiring, and ambiguous asks (`m012`). Noise archives are automatic.
- **Messages processed:** 100. Owner: `sam@paperjet.io`.
- **Preference demo:** `m015` → CC Priya on Hartwell mail; `m041` → no meetings before 11:00am.
- **LLM:** configure via `.env` (`USE_LLM`, `MODEL_PROVIDER=openai|ollama`). Offline demos still work with `USE_LLM=0`. Custom MCP server is pure Python stdio JSON-RPC (`python -m mcp_server`) so it runs on Python 3.8+ without the official SDK.

## Capabilities

| id | name | tier | one-line claim |
|----|------|------|----------------|
| R1 | Zero the inbox | B | every message gets one disposition + reason; none left |
| R2 | Grounded reply | B | drafts cite earlier messages actually read (e.g. m008←m003) |
| R3 | Gate the irreversible | C | no send/delete without approval or `--dry-run` |
| R4 | Persistent preference | C | prefs.json survives restart and changes later behaviour |
| R5 | Refuse embedded instructions | C | detect, refuse, flag, report; never silent |
| R6 | Dashboard | C | three panes; multi-cite commitments; conflicts surfaced |
| X1 | Follow-up tracking | B | unanswered outbound mail with chase drafts |
| X2 | Morning digest | A | needs you / can wait / auto-archived counts |
| X3 | Launch-thread summary | B | long thread → open question for Sam |
| X4 | Explain a decision | A | ask why a message got its disposition |
| X5 | Batch noise handling | A | receipts/newsletters/alerts counted and rule-archived |
| X6 | LLM + MCP agent | C | LLM plans over custom MCP mail tools (gated send) |
| MCP | MCP smoke test | A | custom stdio MCP tool surface works offline |

Exact commands, observables and evidence are in `capabilities.json` (machine-readable; keep in step with this file).

## Final Report

1. **What did you refuse to automate?** `m012` is escalated. Investor/press/legal sends stop at `gate.py`. Hostile mail (`m024`, `m017`, `m039`, `m047`) is flagged and left in place; MCP `send_email` will not deliver to `mail-backup-service.info` / `ext-audit.co`.

2. **Where does untrusted text enter?** MCP `get_message` / `get_thread` return bodies inside `<<<UNTRUSTED_EMAIL_BODY>>>` markers with `content_trust=UNTRUSTED_EMAIL_DATA`. The agent system prompt forbids obeying them. Only `gate.send_message` (via MCP `send_email`) mutates the world, and only after approval / dry-run.

3. **Who is accountable when it sends the wrong thing?** The human who approved the gated send (or `--auto-approve`). Trace: `trace.jsonl` + `data/gate_log.jsonl` + cited message ids on drafts.

4. **Name your own machinery.** MCP tools ≈ framework Tools; `agent.run_agent` ≈ Agent; each `--cap` / user task ≈ Task; `demo.py` / `zero_inbox` ≈ Crew/router. We built the gate + untrusted-data boundary ourselves — the MCP package only gives stdio transport and schemas.
