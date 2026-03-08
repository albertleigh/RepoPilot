"""
Background task runner – executes shell commands in daemon threads.
"""
from __future__ import annotations

import subprocess
import threading
import uuid
from pathlib import Path
from queue import Queue


class BackgroundManager:
    """Run shell commands in background threads with notification queue."""

    def __init__(self, workdir: Path) -> None:
        self._workdir = workdir
        self.tasks: dict[str, dict] = {}
        self.notifications: Queue = Queue()

    def run(self, command: str, timeout: int = 120) -> str:
        tid = str(uuid.uuid4())[:8]
        self.tasks[tid] = {"status": "running", "command": command, "result": None}
        threading.Thread(
            target=self._exec, args=(tid, command, timeout), daemon=True,
        ).start()
        return f"Background task {tid} started: {command[:80]}"

    def _exec(self, tid: str, command: str, timeout: int) -> None:
        try:
            r = subprocess.run(
                command, shell=True, cwd=self._workdir,
                capture_output=True, text=True, timeout=timeout,
            )
            output = (r.stdout + r.stderr).strip()[:50000]
            self.tasks[tid].update({"status": "completed", "result": output or "(no output)"})
        except Exception as e:
            self.tasks[tid].update({"status": "error", "result": str(e)})
        self.notifications.put({
            "task_id": tid,
            "status": self.tasks[tid]["status"],
            "result": self.tasks[tid]["result"][:500],
        })

    def check(self, tid: str | None = None) -> str:
        if tid:
            t = self.tasks.get(tid)
            if not t:
                return f"Unknown: {tid}"
            return f"[{t['status']}] {t.get('result', '(running)')}"
        return ("\n".join(
            f"{k}: [{v['status']}] {v['command'][:60]}"
            for k, v in self.tasks.items()
        ) or "No bg tasks.")

    def drain(self) -> list[dict]:
        notifs = []
        while not self.notifications.empty():
            notifs.append(self.notifications.get_nowait())
        return notifs
