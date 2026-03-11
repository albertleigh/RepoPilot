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
from core.events import (
    EventBus,
    EngineerErrorEvent,
    EngineerMessageEvent,
    EngineerProgressEvent,
    EngineerStartedEvent,
    EngineerStoppedEvent,
    EngineerToolCallEvent,
    EngineerToolResultEvent,
    EngineerUserMessageEvent,
    TodoUpdatedEvent,
    TaskCreatedEvent,
    TaskUpdatedEvent,
    TeammateSpawnedEvent,
    TeammateStoppedEvent,
    SkillRegisteredEvent,
)
from core.mcp.registry import McpServerRegistry

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

MAX_TOOL_ROUNDS = 200  # hard cap to prevent infinite tool-loop spirals


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
        event_bus: EventBus | None = None,
        mcp_server_registry: McpServerRegistry | None = None,
    ) -> None:
        self.workdir = workdir.resolve()
        self._llm = llm_client
        self._event_bus = event_bus
        self._mcp = mcp_server_registry
        self.status: Status = Status.IDLE

        # -- sub-services --
        self.todo = TodoManager()
        self.tasks = TaskManager(self.workdir)
        self.skills = SkillLoader(skills_dir or (self.workdir / "skills"))
        self.bus = MessageBus(self.workdir)
        self.bg = BackgroundManager(self.workdir)
        self.team = TeammateManager(
            self.workdir, self.bus, self.tasks, self._llm,
            event_bus=self._event_bus,
            mcp_server_registry=self._mcp,
        )

        # -- shutdown / plan tracking --
        self._shutdown_requests: dict[str, dict] = {}
        self._plan_requests: dict[str, dict] = {}

        # -- thread plumbing --
        self._inbox: Queue[str] = Queue()  # user → agent
        self._stop = threading.Event()
        self._cancel = threading.Event()   # soft cancel: abort current run, keep thread alive
        self._wake = threading.Event()      # set to unblock idle loop
        self._idle_event = threading.Event()  # set when agent returns to IDLE
        self._idle_event.set()  # starts idle
        self._thread: threading.Thread | None = None
        self._last_response: str = ""  # last assistant text for external callers

        # -- conversation history --
        self._messages: list[dict] = []

        # -- UI event log (thread-safe) --
        self._event_log: list = []
        self._log_lock = threading.Lock()

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
            "TodoWrite":        lambda **kw: self._handle_todo_write(kw["items"]),
            "task":             lambda **kw: self._run_subagent(kw["prompt"], kw.get("agent_type", "Explore")),
            "load_skill":       lambda **kw: self._handle_load_skill(kw["name"]),
            "compress":         lambda **kw: "Compressing...",
            "background_run":   lambda **kw: self.bg.run(kw["command"], kw.get("timeout", 120)),
            "check_background": lambda **kw: self.bg.check(kw.get("task_id")),
            "task_create":      lambda **kw: self._handle_task_create(kw["subject"], kw.get("description", "")),
            "task_get":         lambda **kw: self.tasks.get(kw["task_id"]),
            "task_update":      lambda **kw: self._handle_task_update(kw["task_id"], kw.get("status"), kw.get("add_blocked_by"), kw.get("add_blocks")),
            "task_list":        lambda **kw: self.tasks.list_all(),
            "claim_task":       lambda **kw: self.tasks.claim(kw["task_id"], "lead"),
            "spawn_teammate":   lambda **kw: self._handle_spawn_teammate(kw["name"], kw["role"], kw["prompt"]),
            "list_teammates":   lambda **kw: self.team.list_all(),
            "send_message":     lambda **kw: self.bus.send("lead", kw["to"], kw["content"], kw.get("msg_type", "message")),
            "read_inbox":       lambda **kw: json.dumps(self.bus.read_inbox("lead"), indent=2),
            "broadcast":        lambda **kw: self.bus.broadcast("lead", kw["content"], self.team.member_names()),
            "shutdown_request": lambda **kw: self._handle_shutdown_request_with_event(kw["teammate"]),
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

    # ------------------------------------------------------------------
    # Event-emitting handler wrappers
    # ------------------------------------------------------------------

    def _handle_todo_write(self, items: list) -> str:
        result = self.todo.update(items)
        self._emit_event(TodoUpdatedEvent(
            workdir=str(self.workdir), items=self.todo.items,
        ))
        return result

    def _handle_task_create(self, subject: str, description: str) -> str:
        result = self.tasks.create(subject, description)
        task = json.loads(result)
        self._emit_event(TaskCreatedEvent(
            workdir=str(self.workdir),
            task_id=str(task["id"]),
            title=task["subject"],
        ))
        return result

    def _handle_task_update(self, task_id: int, status=None,
                            add_blocked_by=None, add_blocks=None) -> str:
        result = self.tasks.update(task_id, status, add_blocked_by, add_blocks)
        self._emit_event(TaskUpdatedEvent(
            workdir=str(self.workdir),
            task_id=str(task_id),
            status=status or "",
        ))
        return result

    def _handle_spawn_teammate(self, name: str, role: str, prompt: str) -> str:
        result = self.team.spawn(name, role, prompt)
        if not result.startswith("Error"):
            self._emit_event(TeammateSpawnedEvent(
                workdir=str(self.workdir), teammate_id=name,
            ))
        return result

    def _handle_load_skill(self, name: str) -> str:
        result = self.skills.load(name)
        if not result.startswith("Error"):
            self._emit_event(SkillRegisteredEvent(name=name))
        return result

    def _handle_shutdown_request_with_event(self, teammate: str) -> str:
        result = self._handle_shutdown_request(teammate)
        self._emit_event(TeammateStoppedEvent(
            workdir=str(self.workdir), teammate_id=teammate,
        ))
        return result

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
        import platform
        os_info = f"{platform.system()} ({platform.machine()})"
        shell_hint = (
            "The shell is PowerShell. Use PowerShell syntax for bash commands "
            "(e.g. Get-ChildItem instead of ls, Get-Content instead of cat, "
            "Select-String instead of grep, Select-Object -First N instead of head -N). "
            "Unix commands like ls, head, tail, cat, grep will NOT work."
            if platform.system() == "Windows"
            else ""
        )
        return (
            f"You are a coding agent at {self.workdir}. "
            f"OS: {os_info}. {shell_hint}\n"
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
        """Process user messages via the full tool-use loop.

        Multiple messages may arrive while the agent is busy.  After
        each tool-loop completes we re-check the inbox so queued
        messages are never starved.
        """
        rounds_without_todo = 0
        msgs = self._messages
        _log.debug("[DIAG] _agent_loop STARTED for %s", self.workdir)

        while not self._stop.is_set():
            # --- block until woken (no busy-wait) ---
            _log.debug("[DIAG] _agent_loop waiting on _wake for %s", self.workdir)
            self._wake.wait()
            if self._stop.is_set():
                _log.debug("[DIAG] _agent_loop stop requested, exiting for %s", self.workdir)
                break
            self._wake.clear()
            _log.debug("[DIAG] _agent_loop WOKEN, inbox size ~%d for %s", self._inbox.qsize(), self.workdir)

            # --- drain all queued messages one-by-one ---
            drain_count = 0
            while not self._stop.is_set():
                try:
                    user_text = self._inbox.get_nowait()
                except Empty:
                    _log.debug("[DIAG] _agent_loop inbox drained, processed %d messages for %s", drain_count, self.workdir)
                    break  # inbox empty, go back to _wake.wait()

                drain_count += 1
                _log.debug("[DIAG] _agent_loop dequeued msg #%d (len=%d): %.80s... for %s", drain_count, len(user_text), user_text, self.workdir)
                self.status = Status.RUNNING
                self._idle_event.clear()
                msgs.append({"role": "user", "content": user_text})
                self._emit_event(EngineerStartedEvent(workdir=str(self.workdir)))

                self._cancel.clear()
                try:
                    self._run_tool_loop(msgs, rounds_without_todo)
                    _log.debug("[DIAG] _run_tool_loop completed normally for %s", self.workdir)
                except Exception:
                    _log.exception("Agent loop error in %s", self.workdir)
                    self._emit_event(EngineerErrorEvent(
                        workdir=str(self.workdir),
                        error="Internal agent error – see logs.",
                    ))
                finally:
                    self._cancel.clear()
                    self.status = Status.IDLE
                    self._idle_event.set()
                    self._emit_event(EngineerStoppedEvent(workdir=str(self.workdir)))
                    _log.debug("[DIAG] _agent_loop emitted STOPPED, back to drain for %s", self.workdir)

    def _run_tool_loop(self, msgs: list, rounds_without_todo: int) -> None:
        """Inner loop: LLM call → tool dispatch → repeat until end_turn."""
        tool_round = 0
        while not self._stop.is_set() and not self._cancel.is_set():
            tool_round += 1
            if tool_round > MAX_TOOL_ROUNDS:
                _log.warning("Tool-loop hit %d rounds, forcing stop for %s", MAX_TOOL_ROUNDS, self.workdir)
                self._emit_event(EngineerMessageEvent(
                    workdir=str(self.workdir),
                    text=f"\u26a0\ufe0f Reached maximum tool rounds ({MAX_TOOL_ROUNDS}). Stopping to avoid infinite loop.",
                ))
                break
            _log.debug("[DIAG] _run_tool_loop round %d starting for %s", tool_round, self.workdir)
            # -- compression --
            microcompact(msgs)
            if estimate_tokens(msgs) > TOKEN_THRESHOLD:
                _log.info("Auto-compact triggered for %s", self.workdir)
                self._emit_event(EngineerProgressEvent(
                    workdir=str(self.workdir),
                    phase="compressing",
                    detail="Compacting conversation history\u2026",
                ))
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
            self._emit_event(EngineerProgressEvent(
                workdir=str(self.workdir),
                phase="thinking",
                detail=f"Waiting for LLM response (round {tool_round})\u2026",
            ))
            _log.debug("[DIAG] _run_tool_loop calling LLM (round %d) for %s", tool_round, self.workdir)

            # Merge built-in tools with MCP tools (respect provider limit)
            all_tools = TOOLS
            if self._mcp:
                budget = self._llm.MAX_TOOLS - len(TOOLS)
                mcp_tools = self._mcp.get_all_mcp_tool_definitions(budget=budget)
                if mcp_tools:
                    all_tools = TOOLS + mcp_tools

            response = self._llm.send_with_tools(
                msgs, all_tools, self._system_prompt(),
            )
            _log.debug("[DIAG] LLM responded: stop_reason=%s, has_text=%s, num_tool_calls=%d for %s",
                       response.stop_reason, bool(response.text), len(response.tool_calls or []), self.workdir)
            msgs.append(response.assistant_message)

            if response.text:
                self._last_response = response.text
                _log.debug("[DIAG] Emitting ENGINEER_MESSAGE (len=%d): %.120s... for %s",
                           len(response.text), response.text, self.workdir)
                self._emit_event(EngineerMessageEvent(
                    workdir=str(self.workdir), text=response.text,
                ))

            if response.stop_reason != "tool_use":
                _log.debug("[DIAG] _run_tool_loop DONE (stop_reason=%s) after %d rounds for %s",
                           response.stop_reason, tool_round, self.workdir)
                break

            # -- Tool dispatch --
            results = []
            used_todo = False
            manual_compress = False
            for tc in response.tool_calls:
                if self._cancel.is_set():
                    _log.info("Cancel requested mid-tool-dispatch, breaking for %s", self.workdir)
                    break
                if tc.name == "compress":
                    manual_compress = True
                # Build a descriptive progress message
                if tc.name == "bash":
                    cmd_preview = tc.input.get("command", "")[:80]
                    progress_detail = f"Running: {cmd_preview}\u2026"
                else:
                    progress_detail = f"Running {tc.name}\u2026"
                self._emit_event(EngineerProgressEvent(
                    workdir=str(self.workdir),
                    phase="executing_tool",
                    detail=progress_detail,
                ))
                handler = self._handlers.get(tc.name)
                _log.info("[TOOL] Dispatching %s (round %d) for %s", tc.name, tool_round, self.workdir)
                try:
                    if self._mcp and self._mcp.is_mcp_tool(tc.name):
                        output = self._mcp.call_mcp_tool(tc.name, tc.input)
                    elif handler:
                        output = handler(**tc.input)
                    else:
                        output = f"Unknown tool: {tc.name}"
                except Exception as e:
                    output = f"Error: {e}"
                    _log.warning("[TOOL] %s raised: %s", tc.name, e)
                _log.info("[TOOL] %s completed (output_len=%d) for %s", tc.name, len(str(output)), self.workdir)
                _log.debug("> %s: %s", tc.name, str(output)[:200])
                results.append({"tool_use_id": tc.id, "output": str(output)})
                self._emit_event(EngineerToolCallEvent(
                    workdir=str(self.workdir),
                    tool_name=tc.name,
                    tool_input=tc.input,
                ))
                self._emit_event(EngineerToolResultEvent(
                    workdir=str(self.workdir),
                    tool_name=tc.name,
                    output=str(output)[:2000],
                ))
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

        # If cancelled, note it in the conversation so context is preserved
        if self._cancel.is_set():
            _log.info("Tool loop cancelled by user for %s", self.workdir)
            msgs.append({"role": "assistant", "content": "[Cancelled by user]"})
            self._emit_event(EngineerMessageEvent(
                workdir=str(self.workdir),
                text="\u26d4 Stopped by user.",
            ))

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _emit_event(self, event: Any) -> None:
        """Emit a typed event on the global bus (async, non-blocking)."""
        _log.debug("[DIAG] _emit_event: kind=%s, bus=%s for %s",
                   getattr(event, 'kind', '?'), self._event_bus is not None, self.workdir)
        with self._log_lock:
            self._event_log.append(event)
        if self._event_bus is not None:
            self._event_bus.emit_async(event)
        else:
            _log.warning("[DIAG] _emit_event: NO event_bus! Event lost: %s", getattr(event, 'kind', '?'))

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

    def get_event_history(self) -> list:
        """Return a copy of all events emitted so far (thread-safe)."""
        with self._log_lock:
            return list(self._event_log)

    def send_message(self, text: str, source: str = "") -> None:
        """Send a user message into the agent loop (thread-safe).

        Automatically wakes the loop if it is idle.

        Parameters
        ----------
        text:
            The message content.
        source:
            Optional label for the sender (e.g. ``"Project Manager"``).
            When non-empty an :class:`EngineerUserMessageEvent` is
            emitted so the UI can display the external message.
        """
        if source:
            self._emit_event(EngineerUserMessageEvent(
                workdir=str(self.workdir), text=text, source=source,
            ))
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

    def cancel(self) -> None:
        """Soft-cancel the current tool loop.

        The agent thread stays alive and the conversation history is
        preserved.  The loop will break at the next check-point and
        return to idle, ready for the next user message.
        """
        self._cancel.set()

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """Block until this engineer finishes its current task.

        Returns ``True`` if the engineer became idle within *timeout*
        seconds, ``False`` on timeout.  If the engineer is already
        idle this returns immediately.
        """
        return self._idle_event.wait(timeout=timeout)

    def get_last_response(self) -> str:
        """Return the last assistant text produced by the tool loop."""
        return self._last_response

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
