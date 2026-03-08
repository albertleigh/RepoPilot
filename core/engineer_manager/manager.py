"""
EngineerManager – autonomous agent loop bound to a single git repo.

Each instance owns isolated sub-services and runs in a dedicated daemon
thread.  The UI communicates with it via a thread-safe
:class:`queue.Queue`.

Wake protocol
-------------
While the agent is **IDLE** (waiting for work), the loop blocks on an
internal ``threading.Event`` (``_wake``).  Any thread that enqueues work
must call :meth:`wake` (or use :meth:`send_message`, which does so
automatically) so the loop unblocks and processes the new input.

When to call :meth:`wake`:

* After pushing a user message via :meth:`send_message` – handled
  automatically.
* After injecting synthetic messages into ``_inbox`` from an external
  coordination layer.
* From background-manager drain callbacks or teammate completions
  that should prompt the lead agent to re-enter its tool loop.

:meth:`wake` is a no-op when the agent is already RUNNING, so it is
always safe to call.
"""
from __future__ import annotations

import json
import logging
import threading
import uuid
from enum import Enum, auto
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

from core.LLMClients.base import LLMClient

from .background_manager import BackgroundManager
from .base_tools import run_bash, run_edit, run_read, run_write
from .compression import (
    TOKEN_THRESHOLD,
    auto_compact,
    estimate_tokens,
    microcompact,
)
from .message_bus import MessageBus
from .skill_loader import SkillLoader
from .task_manager import TaskManager
from .teammate_manager import TeammateManager
from .todo_manager import TodoManager
from .tool_definitions import TOOLS

_log = logging.getLogger(__name__)


class Status(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPED = auto()


class EngineerManager:
    """One manager per git repository.

    Parameters
    ----------
    workdir:
        Absolute path to the git repo root.
    llm_client:
        A configured :class:`LLMClient` instance used for LLM calls.
    skills_dir:
        Optional override for the skills folder (defaults to
        ``<workdir>/skills``).
    """

    def __init__(
        self,
        workdir: Path,
        llm_client: LLMClient,
        skills_dir: Path | None = None,
    ) -> None:
        self.workdir = workdir.resolve()
        self._llm = llm_client
        self.status: Status = Status.IDLE

        # -- sub-services --
        self.todo = TodoManager()
        self.tasks = TaskManager(self.workdir)
        self.skills = SkillLoader(skills_dir or (self.workdir / "skills"))
        self.bus = MessageBus(self.workdir)
        self.bg = BackgroundManager(self.workdir)
        self.team = TeammateManager(
            self.workdir, self.bus, self.tasks, self._llm,
        )

        # -- shutdown / plan tracking --
        self._shutdown_requests: dict[str, dict] = {}
        self._plan_requests: dict[str, dict] = {}

        # -- thread plumbing --
        self._inbox: Queue[str] = Queue()  # user → agent
        self._outbox: Queue[dict] = Queue()  # agent → UI
        self._stop = threading.Event()
        self._wake = threading.Event()      # set to unblock idle loop
        self._thread: threading.Thread | None = None

        # -- conversation history --
        self._messages: list[dict] = []

        # -- tool dispatch map --
        self._handlers: dict[str, Callable[..., Any]] = self._build_handlers()

    # ------------------------------------------------------------------
    # Tool handler wiring
    # ------------------------------------------------------------------

    def _build_handlers(self) -> dict[str, Callable[..., Any]]:
        w = self.workdir
        return {
            "bash":             lambda **kw: run_bash(w, kw["command"]),
            "read_file":        lambda **kw: run_read(w, kw["path"], kw.get("limit")),
            "write_file":       lambda **kw: run_write(w, kw["path"], kw["content"]),
            "edit_file":        lambda **kw: run_edit(w, kw["path"], kw["old_text"], kw["new_text"]),
            "TodoWrite":        lambda **kw: self.todo.update(kw["items"]),
            "task":             lambda **kw: self._run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
            "load_skill":       lambda **kw: self.skills.load(kw["name"]),
            "compress":         lambda **kw: "Compressing...",
            "background_run":   lambda **kw: self.bg.run(kw["command"], kw.get("timeout", 120)),
            "check_background": lambda **kw: self.bg.check(kw.get("task_id")),
            "task_create":      lambda **kw: self.tasks.create(kw["subject"], kw.get("description", "")),
            "task_get":         lambda **kw: self.tasks.get(kw["task_id"]),
            "task_update":      lambda **kw: self.tasks.update(kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("add_blocks")),
            "task_list":        lambda **kw: self.tasks.list_all(),
            "claim_task":       lambda **kw: self.tasks.claim(kw["task_id"], "lead"),
            "spawn_teammate":   lambda **kw: self.team.spawn(kw["name"], kw["role"], kw["prompt"]),
            "list_teammates":   lambda **kw: self.team.list_all(),
            "send_message":     lambda **kw: self.bus.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
            "read_inbox":       lambda **kw: json.dumps(self.bus.read_inbox("lead"), indent=2),
            "broadcast":        lambda **kw: self.bus.broadcast("lead", kw["content"], self.team.member_names()),
            "shutdown_request": lambda **kw: self._handle_shutdown_request(kw["teammate"]),
            "plan_approval":    lambda **kw: self._handle_plan_review(kw["request_id"], kw["approve"], kw.get("feedback", "")),
            "idle":             lambda **kw: "Lead does not idle.",
        }

    # ------------------------------------------------------------------
    # Subagent
    # ------------------------------------------------------------------

    def _run_subagent(self, prompt: str, agent_type: str = "Explore") -> str:
        """Spawn a short-lived sub-agent with its own tool loop."""
        sub_tools: list[dict] = [
            {"name": "bash", "description": "Run command.",
             "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
            {"name": "read_file", "description": "Read file.",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        ]
        if agent_type != "Explore":
            sub_tools += [
                {"name": "write_file", "description": "Write file.",
                 "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}},
                {"name": "edit_file", "description": "Edit file.",
                 "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old_text": {"type": "string"}, "new_text": {"type": "string"}}, "required": ["path", "old_text", "new_text"]}},
            ]
        sub_handlers = {
            "bash":       lambda **kw: run_bash(self.workdir, kw["command"]),
            "read_file":  lambda **kw: run_read(self.workdir, kw["path"]),
            "write_file": lambda **kw: run_write(self.workdir, kw["path"], kw["content"]),
            "edit_file":  lambda **kw: run_edit(self.workdir, kw["path"], kw["old_text"], kw["new_text"]),
        }
        sub_msgs: list[dict] = [{"role": "user", "content": prompt}]
        for _ in range(30):
            response = self._llm.send_with_tools(sub_msgs, sub_tools)
            sub_msgs.append(response.assistant_message)
            if response.stop_reason != "tool_use":
                return response.text or "(no summary)"
            results = []
            for tc in response.tool_calls:
                handler = sub_handlers.get(tc.name, lambda **kw: "Unknown tool")
                output = str(handler(**tc.input))[:50_000]
                results.append({"tool_use_id": tc.id, "output": output})
            sub_msgs.extend(self._llm.make_tool_results(results))
        return "(subagent max iterations)"

    # ------------------------------------------------------------------
    # Shutdown / plan protocols
    # ------------------------------------------------------------------

    def _handle_shutdown_request(self, teammate: str) -> str:
        req_id = str(uuid.uuid4())[:8]
        self._shutdown_requests[req_id] = {
            "target": teammate, "status": "pending",
        }
        self.bus.send(
            "lead", teammate, "Please shut down.",
            "shutdown_request", {"request_id": req_id},
        )
        return f"Shutdown request {req_id} sent to '{teammate}'"

    def _handle_plan_review(
        self, request_id: str, approve: bool, feedback: str = "",
    ) -> str:
        req = self._plan_requests.get(request_id)
        if not req:
            return f"Error: Unknown plan request_id '{request_id}'"
        req["status"] = "approved" if approve else "rejected"
        self.bus.send(
            "lead", req["from"], feedback, "plan_approval_response",
            {"request_id": request_id, "approve": approve, "feedback": feedback},
        )
        return f"Plan {req['status']} for '{req['from']}'"

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        return (
            f"You are a coding agent at {self.workdir}. "
            "Use tools to solve tasks.\n"
            "Prefer task_create/task_update/task_list for multi-step work. "
            "Use TodoWrite for short checklists.\n"
            "Use task for subagent delegation. "
            "Use load_skill for specialized knowledge.\n"
            f"Skills: {self.skills.descriptions()}"
        )

    # ------------------------------------------------------------------
    # Agent loop (runs inside a daemon thread)
    # ------------------------------------------------------------------

    def _agent_loop(self) -> None:
        """Process one user message per iteration via the full tool-use loop."""
        rounds_without_todo = 0
        msgs = self._messages

        while not self._stop.is_set():
            # --- block until woken (no busy-wait) ---
            self._wake.wait()
            if self._stop.is_set():
                break
            self._wake.clear()

            # --- drain all queued messages ---
            try:
                user_text = self._inbox.get_nowait()
            except Empty:
                continue

            self.status = Status.RUNNING
            msgs.append({"role": "user", "content": user_text})
            self._emit("status", "running")

            try:
                self._run_tool_loop(msgs, rounds_without_todo)
            except Exception:
                _log.exception("Agent loop error in %s", self.workdir)
                self._emit("error", "Internal agent error – see logs.")
            finally:
                self.status = Status.IDLE
                self._emit("status", "idle")

    def _run_tool_loop(self, msgs: list, rounds_without_todo: int) -> None:
        """Inner loop: LLM call → tool dispatch → repeat until end_turn."""
        while not self._stop.is_set():
            # -- compression --
            microcompact(msgs)
            if estimate_tokens(msgs) > TOKEN_THRESHOLD:
                _log.info("Auto-compact triggered for %s", self.workdir)
                msgs[:] = auto_compact(msgs, self._llm, self.workdir)

            # -- drain background notifications --
            notifs = self.bg.drain()
            if notifs:
                txt = "\n".join(
                    f"[bg:{n['task_id']}] {n['status']}: {n['result']}"
                    for n in notifs
                )
                msgs.append({"role": "user", "content": f"<background-results>\n{txt}\n</background-results>"})
                msgs.append({"role": "assistant", "content": "Noted background results."})

            # -- check lead inbox --
            inbox = self.bus.read_inbox("lead")
            if inbox:
                msgs.append({"role": "user", "content": f"<inbox>{json.dumps(inbox, indent=2)}</inbox>"})
                msgs.append({"role": "assistant", "content": "Noted inbox messages."})

            # -- LLM call with tools --
            response = self._llm.send_with_tools(
                msgs, TOOLS, self._system_prompt(),
            )
            msgs.append(response.assistant_message)

            if response.text:
                self._emit("assistant", response.text)

            if response.stop_reason != "tool_use":
                break

            # -- Tool dispatch --
            results = []
            used_todo = False
            manual_compress = False
            for tc in response.tool_calls:
                if tc.name == "compress":
                    manual_compress = True
                handler = self._handlers.get(tc.name)
                try:
                    output = handler(**tc.input) if handler else f"Unknown tool: {tc.name}"
                except Exception as e:
                    output = f"Error: {e}"
                _log.debug("> %s: %s", tc.name, str(output)[:200])
                results.append({"tool_use_id": tc.id, "output": str(output)})
                if tc.name == "TodoWrite":
                    used_todo = True

            # nag reminder (only when todo workflow is active)
            rounds_without_todo = 0 if used_todo else rounds_without_todo + 1
            if self.todo.has_open_items() and rounds_without_todo >= 3:
                results.insert(0, {"tool_use_id": "_nag", "output": "<reminder>Update your todos.</reminder>"})

            msgs.extend(self._llm.make_tool_results(results))

            # -- manual compress --
            if manual_compress:
                _log.info("Manual compact for %s", self.workdir)
                msgs[:] = auto_compact(msgs, self._llm, self.workdir)

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------

    def _emit(self, kind: str, payload: Any) -> None:
        """Push an event onto the outbox for the UI to consume."""
        self._outbox.put({"kind": kind, "payload": payload})

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the agent loop in a daemon thread."""
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.status = Status.IDLE
        self._thread = threading.Thread(
            target=self._agent_loop, daemon=True,
            name=f"engineer-{self.workdir.name}",
        )
        self._thread.start()

    def send_message(self, text: str) -> None:
        """Send a user message into the agent loop (thread-safe).

        Automatically wakes the loop if it is idle.
        """
        self._inbox.put(text)
        self.wake()

    def wake(self) -> None:
        """Signal the agent loop to unblock and check for work.

        Safe to call from any thread and at any time.  Has no effect
        when the agent is already processing a request (RUNNING).
        Use this after enqueuing work into ``_inbox`` from outside
        :meth:`send_message`, or when external events (background
        task completions, teammate messages) should prompt the lead
        agent to re-enter its tool loop.
        """
        self._wake.set()

    def poll_events(self, timeout: float = 0) -> list[dict]:
        """Drain all pending events from the outbox.

        Returns a (possibly empty) list of ``{kind, payload}`` dicts.
        """
        events: list[dict] = []
        while True:
            try:
                events.append(self._outbox.get_nowait())
            except Empty:
                break
        return events

    def shutdown(self) -> None:
        """Signal the loop to stop and wait for the thread to finish."""
        self._stop.set()
        self._wake.set()  # unblock if waiting
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self.status = Status.STOPPED

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
