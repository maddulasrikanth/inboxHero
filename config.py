"""Configuration loaded from environment variables. Never hardcode secrets."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent
INBOX_PATH = Path(os.getenv("INBOX_PATH", ROOT / "inbox.json"))
OUTBOX_DIR = Path(os.getenv("OUTBOX_DIR", ROOT / "outbox"))
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data"))
TRACE_PATH = Path(os.getenv("TRACE_PATH", ROOT / "trace.jsonl"))
PREFS_PATH = DATA_DIR / "prefs.json"
DECISIONS_PATH = DATA_DIR / "decisions.json"
DASHBOARD_HTML = ROOT / "dashboard.html"
DASHBOARD_JSON = ROOT / "dashboard.json"
GATE_LOG_PATH = DATA_DIR / "gate_log.jsonl"

OWNER_EMAIL = os.getenv("OWNER_EMAIL", "sam@paperjet.io")
OWNER_NAME = os.getenv("OWNER_NAME", "Sam")

# LLM — set USE_LLM=1 and MODEL_PROVIDER=openai|ollama
MODEL_PROVIDER = os.getenv("MODEL_PROVIDER", "none").lower()  # none | openai | ollama
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
USE_LLM = os.getenv("USE_LLM", "0") == "1" and MODEL_PROVIDER not in {"none", ""}

# Rate-limit safety (free tiers ~15 rpm)
LLM_MIN_INTERVAL_SEC = float(os.getenv("LLM_MIN_INTERVAL_SEC", "2"))
LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "5"))
LLM_MAX_AGENT_STEPS = int(os.getenv("LLM_MAX_AGENT_STEPS", "12"))
OLLAMA_TIMEOUT_SEC = float(os.getenv("OLLAMA_TIMEOUT_SEC", "180"))
OLLAMA_TOOL_TIMEOUT_SEC = float(os.getenv("OLLAMA_TOOL_TIMEOUT_SEC", "300"))

# Dry-run / approval defaults
DEFAULT_DRY_RUN = os.getenv("DRY_RUN", "1") == "1"
AUTO_APPROVE = os.getenv("AUTO_APPROVE", "0") == "1"

DATA_DIR.mkdir(parents=True, exist_ok=True)
OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
