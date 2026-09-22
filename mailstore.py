"""Mail store: load inbox, thread walk, keyword search."""
from __future__ import annotations

import json
import re
from pathlib import Path

import config
import trace


class MailStore:
    def __init__(self, path: Path | None = None):
        self.path = path or config.INBOX_PATH
        self.messages: list[dict] = []
        self.by_id: dict[str, dict] = {}
        self.by_thread: dict[str, list[dict]] = {}

    def load(self) -> list[dict]:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.messages = sorted(raw, key=lambda m: m["timestamp"])
        self.by_id = {m["id"]: m for m in self.messages}
        self.by_thread = {}
        for m in self.messages:
            self.by_thread.setdefault(m["thread_id"], []).append(m)
        for tid in self.by_thread:
            self.by_thread[tid].sort(key=lambda m: m["timestamp"])
        return self.messages

    def get(self, mid: str) -> dict | None:
        return self.by_id.get(mid)

    def thread(self, thread_id: str) -> list[dict]:
        return list(self.by_thread.get(thread_id, []))

    def thread_before(self, message: dict) -> list[dict]:
        """Earlier messages in the same thread (thread-walk retrieval)."""
        earlier = [
            m
            for m in self.thread(message["thread_id"])
            if m["timestamp"] < message["timestamp"]
        ]
        for m in earlier:
            trace.log("read", message_id=m["id"], via="thread-walk")
        return earlier

    def keyword_search(self, query: str, exclude_id: str | None = None, limit: int = 10) -> list[dict]:
        tokens = [t.lower() for t in re.findall(r"[a-zA-Z0-9@./:_-]{3,}", query)]
        if not tokens:
            return []
        scored: list[tuple[int, dict]] = []
        for m in self.messages:
            if exclude_id and m["id"] == exclude_id:
                continue
            blob = f"{m['subject']}\n{m['body']}\n{m['from']}".lower()
            score = sum(1 for t in tokens if t in blob)
            if score:
                scored.append((score, m))
        scored.sort(key=lambda x: (-x[0], x[1]["timestamp"]))
        hits = [m for _, m in scored[:limit]]
        for m in hits:
            trace.log("read", message_id=m["id"], via="keyword")
        return hits
