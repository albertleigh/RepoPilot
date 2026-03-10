"""
Teammate manager – spawns autonomous teammate agent threads.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from pathlib import Path

from .base_tools import run_bash, run_read, run_write, run_edit
from .message_bus import MessageBus
from .task_manager import TaskManager

_log = logging.getLogger(__name__)

POLL_INTERVAL = 5
IDLE_TIMEOUT = 60

TEAMMATE_TOOLS: list[dict] = [
    {"name": "bash", "description": "Run command.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "read_file", "description": "Read file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Write file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
    {"name": "edit_file", "description": "Edit file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
    {"name": "send_message", "description": "Send message to teammate.",
     "input_schema": {"type": "object", "properties": {"to": {"type": "string"}, "content": {"type": "string"}}, "required": ["to", "content"]}},
    {"name": "idle", "description": "Signal no more work.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "claim_task", "description": "Claim task by ID.",
     "input_schema": {"type": "object", "properties": {"task_id": {"type": "integer"}}, "required": ["task_id"]}},
]


class TeammateManager:
    """Manages persistent autonomous teammates for an EngineerManager."""

    def __init__(self, workdir: Path, bus: MessageBus,
                 task_mgr: TaskManager, llm_client,
                 event_bus=None) -> None:
        self._workdir = workdir
        self._team_dir = workdir / ".team"
        self._team_dir.mkdir(exist_ok=True)
        self.bus = bus
        self.task_mgr = task_mgr
        self._llm = llm_client
        self._event_bus = event_bus
        self.config_path = self._team_dir / "config.json"
        self.config = self._load_config()
        self.threads: dict[str, threading.Thread] = {}

    def _load_config(self) -> dict:
        if self.config_path.exists():
            return json.loads(self.config_path.read_text())
        return {"team_name": "default", "members": []}

    def _save_config(self) -> None:
        self.config_path.write_text(json.dumps(self.config, indent=2))

    def _find(self, name: str) -> dict | None:
        for m in self.config["members"]:
            if m["name"] == name:
                return m
        return None

    def spawn(self, name: str, role: str, prompt: str) -> str:
        member = self._find(name)
        if member:
            if member["status"] not in ("idle", "shutdown"):
                return f"Error: '{name}' is currently {member['status']}"
            member["status"] = "working"
            member["role"] = role
        else:
            member = {"name": name, "role": role, "status": "working"}
            self.config["members"].append(member)
        self._save_config()
        t = threading.Thread(
            target=self._loop, args=(name, role, prompt), daemon=True)
        t.start()
        self.threads[name] = t
        self._emit_teammate_event("spawned", name)
        return f"Spawned '{name}' (role: {role})"

    def _set_status(self, name: str, status: str) -> None:
        member = self._find(name)
        if member:
            member["status"] = status
            self._save_config()

    def _loop(self, name: str, role: str, prompt: str) -> None:
        workdir = self._workdir
        team_name = self.config["team_name"]
        sys_prompt = (
            f"You are '{name}', role: {role}, team: {team_name}, "
            f"at {workdir}. Use idle when done with current work. "
            f"You may auto-claim tasks."
        )

        messages: list[dict] = [{"role": "user", "content": prompt}]

        dispatch = {
            "bash": lambda **kw: run_bash(workdir, kw["command"]),
            "read_file": lambda **kw: run_read(workdir, kw["path"]),
            "write_file": lambda **kw: run_write(workdir, kw["path"], kw["content"]),
            "edit_file": lambda **kw: run_edit(workdir, kw["path"], kw["old_text"], kw["new_text"]),
            "send_message": lambda **kw: self.bus.send(name, kw["to"], kw["content"]),
            "claim_task": lambda **kw: self.task_mgr.claim(kw["task_id"], name),
        }

        while True:
            # -- WORK PHASE --
            for _ in range(50):
                inbox = self.bus.read_inbox(name)
                for msg in inbox:
                    if msg.get("type") == "shutdown_request":
                        self._set_status(name, "shutdown")
                        self._emit_teammate_event("stopped", name)
                        return
                    messages.append({"role": "user", "content": json.dumps(msg)})
                try:
                    response = self._llm.send_with_tools(
                        messages, TEAMMATE_TOOLS, sys_prompt,
                    )
                except Exception:
                    _log.exception("Teammate '%s' LLM call failed", name)
                    self._set_status(name, "shutdown")
                    self._emit_teammate_event("stopped", name)
                    return

                messages.append(response.assistant_message)

                if response.stop_reason != "tool_use":
                    if response.text:
                        self._emit_teammate_event("message", name, response.text)
                    break

                # Dispatch tools
                idle_requested = False
                results = []
                for tc in response.tool_calls:
                    if tc.name == "idle":
                        idle_requested = True
                        output = "Entering idle phase."
                    else:
                        handler = dispatch.get(tc.name, lambda **kw: "Unknown")
                        try:
                            output = str(handler(**tc.input))
                        except Exception as e:
                            output = f"Error: {e}"
                    _log.debug("  [%s] %s: %s", name, tc.name, str(output)[:120])
                    results.append({"tool_use_id": tc.id, "output": str(output)})

                messages.extend(self._llm.make_tool_results(results))

                if idle_requested:
                    break

            # -- IDLE PHASE --
            self._set_status(name, "idle")
            resume = False
            for _ in range(IDLE_TIMEOUT // max(POLL_INTERVAL, 1)):
                time.sleep(POLL_INTERVAL)
                inbox = self.bus.read_inbox(name)
                if inbox:
                    for msg in inbox:
                        if msg.get("type") == "shutdown_request":
                            self._set_status(name, "shutdown")
                            self._emit_teammate_event("stopped", name)
                            return
                        messages.append({"role": "user", "content": json.dumps(msg)})
                    resume = True
                    break
            if not resume:
                self._set_status(name, "shutdown")
                self._emit_teammate_event("stopped", name)
                return
            self._set_status(name, "working")

    def list_all(self) -> str:
        if not self.config["members"]:
            return "No teammates."
        lines = [f"Team: {self.config['team_name']}"]
        for m in self.config["members"]:
            lines.append(f"  {m['name']} ({m['role']}): {m['status']}")
        return "\n".join(lines)

    def member_names(self) -> list[str]:
        return [m["name"] for m in self.config["members"]]

    # ------------------------------------------------------------------
    # Event emission
    # ------------------------------------------------------------------

    def _emit_teammate_event(self, kind: str, name: str, text: str = "") -> None:
        if self._event_bus is None:
            return
        from core.events import (
            TeammateSpawnedEvent, TeammateStoppedEvent, TeammateMessageEvent,
        )
        workdir = str(self._workdir)
        if kind == "spawned":
            self._event_bus.emit_async(TeammateSpawnedEvent(
                workdir=workdir, teammate_id=name,
            ))
        elif kind == "stopped":
            self._event_bus.emit_async(TeammateStoppedEvent(
                workdir=workdir, teammate_id=name,
            ))
        elif kind == "message":
            self._event_bus.emit_async(TeammateMessageEvent(
                workdir=workdir, teammate_id=name, text=text,
            ))
