"""
File-backed message bus scoped to a workdir.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

VALID_MSG_TYPES = frozenset({
    "message", "broadcast", "shutdown_request",
    "shutdown_response", "plan_approval_response",
})


class MessageBus:
    """JSONL-file backed inbox system under ``<workdir>/.team/inbox/``."""

    def __init__(self, workdir: Path) -> None:
        self._inbox_dir = workdir / ".team" / "inbox"
        self._inbox_dir.mkdir(parents=True, exist_ok=True)

    def send(self, sender: str, to: str, content: str,
             msg_type: str = "message", extra: dict | None = None) -> str:
        msg: dict = {
            "type": msg_type, "from": sender,
            "content": content, "timestamp": time.time(),
        }
        if extra:
            msg.update(extra)
        with open(self._inbox_dir / f"{to}.jsonl", "a") as f:
            f.write(json.dumps(msg) + "\n")
        return f"Sent {msg_type} to {to}"

    def read_inbox(self, name: str) -> list[dict]:
        path = self._inbox_dir / f"{name}.jsonl"
        if not path.exists():
            return []
        msgs = [json.loads(line) for line in path.read_text().strip().splitlines() if line]
        path.write_text("")
        return msgs

    def broadcast(self, sender: str, content: str, names: list[str]) -> str:
        count = 0
        for n in names:
            if n != sender:
                self.send(sender, n, content, "broadcast")
                count += 1
        return f"Broadcast to {count} teammates"
