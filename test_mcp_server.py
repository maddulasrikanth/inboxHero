"""Quick local test of the stdio MCP server (newline-delimited JSON)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main() -> int:
    proc = subprocess.Popen(
        [sys.executable, "-m", "mcp_server"],
        cwd=str(ROOT),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert proc.stdin and proc.stdout

    def send(obj):
        # Use Content-Length framing
        raw = json.dumps(obj).encode("utf-8")
        proc.stdin.write(f"Content-Length: {len(raw)}\r\n\r\n".encode("ascii"))
        proc.stdin.write(raw)
        proc.stdin.flush()

    def recv():
        # Read headers
        headers = {}
        while True:
            line = proc.stdout.readline()
            if not line or line in (b"\r\n", b"\n"):
                break
            if b":" in line:
                k, v = line.decode().split(":", 1)
                headers[k.strip().lower()] = v.strip()
        length = int(headers.get("content-length", "0"))
        body = proc.stdout.read(length) if length else b"{}"
        return json.loads(body.decode("utf-8"))

    send(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
    )
    init = recv()
    assert init["result"]["serverInfo"]["name"] == "inboxHero"

    send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = recv()
    names = {t["name"] for t in tools["result"]["tools"]}
    assert "get_message" in names and "send_email" in names

    send(
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "get_message", "arguments": {"message_id": "m003"}},
        }
    )
    call = recv()
    text = call["result"]["content"][0]["text"]
    payload = json.loads(text)
    assert payload["content_trust"] == "UNTRUSTED_EMAIL_DATA"
    assert "amqp://" in payload["body"]

    proc.terminate()
    print("MCP stdio server OK")
    print(f"tools: {sorted(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
