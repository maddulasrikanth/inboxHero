# inboxHero

**Repository:** https://github.com/maddulasrikanth/inboxHero

Agentic local inbox agent for Assignment 06. Reads `inbox.json`, assigns dispositions, drafts grounded replies, gates irreversible sends, remembers preferences, refuses injections/phishing, and writes a three-pane dashboard.

**Stack:** custom **MCP server** (`python -m mcp_server`) + optional **LLM** tool-calling agent (`agent.py` / `llm.py`). Rules still handle noise offline.

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
# Edit .env: set OPENAI_API_KEY (or Ollama) and USE_LLM=1

python demo.py --cap R1          # offline rules OK
python demo.py --cap MCP         # custom MCP tools smoke test
python demo.py --cap X6 --msg m008   # LLM + MCP agent (needs API key)
python -m mcp_server             # stdio MCP for Cursor / Claude Desktop
```

Point Cursor at `mcp.json.example` (set `cwd` to this project).

## Architecture

| Role | Code |
|------|------|
| MCP tools (shared) | `mcp_tools.py` |
| MCP stdio server | `mcp_server/` (`python -m mcp_server`) |
| LLM client | `llm.py` (OpenAI-compatible + Ollama, 429 backoff) |
| LLM agent loop | `agent.py` |
| Mail store / retrieval | `mailstore.py` |
| Router | `triage.py` + `rules.py` |
| Untrusted-content scan | `hostile.py` |
| Draft / cite | `drafting.py` (+ optional LLM polish) |
| Irreversible gate | `gate.py` → `outbox/` |
| Memory | `memory.py` → `data/prefs.json` |
| Entry | `demo.py --cap …` |

Email bodies returned by MCP tools are wrapped as `UNTRUSTED_EMAIL_DATA`. `send_email` defaults to `dry_run=true` and blocks known exfil destinations.

## Layout

```
demo.py              # --cap R1..R6, X1..X6, MCP
agent.py / llm.py    # LLM + tool loop
mcp_tools.py         # shared tool impls
mcp_server/          # custom MCP stdio server
mcp.json.example     # Cursor MCP config fragment
config.py            # env-based config
inbox.json
outbox/
data/prefs.json
trace.jsonl
dashboard.html
CAPABILITIES.md
capabilities.json
```
