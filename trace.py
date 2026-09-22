"""Append-only JSONL event log for evidence and audit."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import config


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def reset(path: Path | None = None) -> None:
    p = path or config.TRACE_PATH
    p.write_text("", encoding="utf-8")


def log(event: str, cap: str | None = None, **fields: Any) -> dict:
    record = {"ts": _now(), "event": event, **fields}
    if cap:
        record["cap"] = cap
    path = config.TRACE_PATH
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
