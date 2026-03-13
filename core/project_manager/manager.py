"""
ProjectManager – orchestration agent that coordinates EngineerManager
instances across multiple repositories.

Inspired by the multi-agent patterns in Claude Code and OpenAI Codex,
this manager operates at the *project* level: it decomposes user
requirements into per-repo tasks, dispatches them to engineer agents,
monitors progress, and verifies completion.

Unlike a pure dispatcher, the PM has **direct access** to every
registered repository (bash, read, write, edit) so it can:

- Inspect code and tests before planning — think critically, not blindly.
- Make surgical cross-repo fixes itself (shared interfaces, configs).
- Debate with engineers and challenge their approaches.
- Relay context between repos to keep contracts in sync.

Architecture
------------
- One ProjectManager per project / session.
- Communicates with EngineerManagers via their public ``send_message``
  / ``get_event_history`` APIs and the shared ``EventBus``.
- Maintains its own LLM-powered tool loop for planning & coordination.
- Uses the same wake/cancel/shutdown lifecycle as EngineerManager.
- Reuses ``base_tools`` functions for sandboxed file/shell operations.

Tool palette (see ``tool_definitions.py``):
    bash, read_file, write_file, edit_file,
    plan_create, plan_list, plan_get,
    dispatch_task, check_engineer, list_engineers, stop_engineer,
    wait_for_engineer, wait_for_engineers, discuss_with_engineer,
    verify_task, broadcast_engineers, query_engineer, share_context,
    background_run, check_background,
    TodoWrite, compress, progress_report
"""
from __future__ import annotations

import json
import logging
import platform
import threading
import time
import uuid
from enum import Enum, auto
from pathlib import Path
from queue import Empty, Queue
from typing import Any, Callable

from core.LLMClients.base import LLMClient
from core.events import (
    EventBus,
    TodoUpdatedEvent,
)
from core.engineer_manager.background_manager import BackgroundManager
from core.engineer_manager.base_tools import run_bash, run_edit, run_read, run_write
from core.engineer_manager.compression import (
    TOKEN_THRESHOLD,
    auto_compact,
    estimate_tokens,
    microcompact,
)
from core.engineer_manager.todo_manager import TodoManager
from core.engineer_manager.registry import EngineerManagerRegistry
from core.mcp.registry import McpServerRegistry
from core.repo_registry import RepoRegistry

from .tool_definitions import PM_TOOLS
from .events import (
    PMStartedEvent,
    PMStoppedEvent,
    PMMessageEvent,
    PMToolCallEvent,
    PMToolResultEvent,
    PMErrorEvent,
    PMProgressEvent,
    PMTaskDispatchedEvent,
    PMTaskVerifiedEvent,
)

_log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 60  # higher cap than engineer — coordination takes more turns


class PMStatus(Enum):
    IDLE = auto()
    RUNNING = auto()
    STOPPED = auto()


class ProjectManager:
    """High-level orchestration agent for multi-repo projects.

    Parameters
    ----------
    llm_client:
        A configured :class:`LLMClient` used for the PM's own LLM calls.
    engineer_registry:
        The shared :class:`EngineerManagerRegistry` so the PM can look up
        and communicate with running engineer agents.
    repo_registry:
        The shared :class:`RepoRegistry` for resolving repo names → paths.
    event_bus:
        Global event bus for emitting PM-specific events.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        engineer_registry: EngineerManagerRegistry,
        repo_registry: RepoRegistry,
        event_bus: EventBus | None = None,
        mcp_server_registry: McpServerRegistry | None = None,
    ) -> None:
        self._llm = llm_client
        self._eng_reg = engineer_registry
        self._repo_reg = repo_registry
        self._event_bus = event_bus
        self._mcp = mcp_server_registry
        self.status: PMStatus = PMStatus.IDLE

        # -- sub-services --
        self.todo = TodoManager()
        self._bg_managers: dict[str, BackgroundManager] = {}  # repo path → bg mgr

        # -- plans --
        self._plans: dict[str, dict] = {}  # plan_id → plan data

        # -- dispatch tracking --
        self._dispatched: dict[str, dict] = {}  # dispatch_id → tracking info

        # -- thread plumbing --
        self._inbox: Queue[str] = Queue()
        self._stop = threading.Event()
        self._cancel = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

        # -- conversation history --
        self._messages: list[dict] = []

        # -- event log --
        self._event_log: list = []
        self._log_lock = threading.Lock()

        # -- tool dispatch map --
        self._handlers: dict[str, Callable[..., Any]] = self._build_handlers()

    # ------------------------------------------------------------------
    # Tool handler wiring
    # ------------------------------------------------------------------

    def _build_handlers(self) -> dict[str, Callable[..., Any]]:
        return {
            # -- direct repo access (reuses engineer base_tools) --
            "bash":                lambda **kw: self._repo_tool(kw["repo"], run_bash, kw["command"]),
            "read_file":           lambda **kw: self._repo_tool(kw["repo"], run_read, kw["path"], kw.get("start_line"), kw.get("end_line")),
            "write_file":          lambda **kw: self._repo_tool(kw["repo"], run_write, kw["path"], kw["content"]),
            "edit_file":           lambda **kw: self._repo_tool(kw["repo"], run_edit, kw["path"], kw["old_text"], kw["new_text"]),
            # -- planning --
            "plan_create":         lambda **kw: self._handle_plan_create(kw["title"], kw["tasks"]),
            "plan_list":           lambda **kw: self._handle_plan_list(),
            "plan_get":            lambda **kw: self._handle_plan_get(kw["plan_id"]),
            # -- engineer dispatch & monitoring --
            "dispatch_task":       lambda **kw: self._handle_dispatch(kw["repo"], kw["prompt"], kw.get("plan_id"), kw.get("task_index")),
            "check_engineer":      lambda **kw: self._handle_check_engineer(kw["repo"]),
            "list_engineers":      lambda **kw: self._handle_list_engineers(),
            "stop_engineer":       lambda **kw: self._handle_stop_engineer(kw["repo"]),
            # -- synchronous wait --
            "wait_for_engineer":   lambda **kw: self._handle_wait_for_engineer(kw["repo"], kw.get("timeout", 300)),
            "wait_for_engineers":  lambda **kw: self._handle_wait_for_engineers(kw["repos"], kw.get("timeout", 600)),
            # -- debate / discussion --
            "discuss_with_engineer": lambda **kw: self._handle_discuss(kw["repo"], kw["message"], kw.get("timeout", 300)),
            # -- verification --
            "verify_task":         lambda **kw: self._handle_verify(kw["repo"], kw["acceptance_criteria"], kw.get("plan_id"), kw.get("task_index")),
            # -- cross-repo coordination --
            "broadcast_engineers": lambda **kw: self._handle_broadcast(kw["message"]),
            "query_engineer":      lambda **kw: self._handle_query(kw["repo"], kw["question"]),
            "share_context":       lambda **kw: self._handle_share_context(kw["source_repo"], kw["source_path"], kw["target_repo"], kw["message"]),
            # -- background --
            "background_run":      lambda **kw: self._handle_background_run(kw["repo"], kw["command"], kw.get("timeout", 120)),
            "check_background":    lambda **kw: self._handle_check_background(kw.get("task_id")),
            # -- internal --
            "TodoWrite":           lambda **kw: self._handle_todo_write(kw["items"]),
            "compress":            lambda **kw: "Compressing...",
            "progress_report":     lambda **kw: self._handle_progress_report(),
        }

    # ------------------------------------------------------------------
    # Repo resolution (shared by all repo-scoped tools)
    # ------------------------------------------------------------------

    def _resolve_workdir(self, repo_name: str) -> tuple[Path | None, str | None]:
        """Resolve a repo display name → absolute Path, or an error string."""
        path_str = self._repo_reg.get(repo_name)
        if not path_str:
            return None, f"Repository '{repo_name}' not found in registry."
        return Path(path_str), None

    def _repo_tool(self, repo_name: str, fn: Callable, *args: Any) -> str:
        """Call a ``base_tools`` function after resolving *repo_name* → workdir."""
        workdir, err = self._resolve_workdir(repo_name)
        if err:
            return f"Error: {err}"
        return fn(workdir, *args)

    def _get_bg_manager(self, repo_name: str) -> tuple[BackgroundManager | None, str | None]:
        """Get-or-create a BackgroundManager for *repo_name*."""
        workdir, err = self._resolve_workdir(repo_name)
        if err:
            return None, err
        key = str(workdir)
        if key not in self._bg_managers:
            self._bg_managers[key] = BackgroundManager(workdir)
        return self._bg_managers[key], None

    # ------------------------------------------------------------------
    # Plan management
    # ------------------------------------------------------------------

    def _handle_plan_create(self, title: str, tasks: list[dict]) -> str:
        plan_id = str(uuid.uuid4())[:8]
        plan = {
            "id": plan_id,
            "title": title,
            "status": "active",
            "tasks": [],
        }
        for i, t in enumerate(tasks):
            plan["tasks"].append({
                "index": i,
                "repo": t.get("repo", ""),
                "description": t.get("description", ""),
                "acceptance_criteria": t.get("acceptance_criteria", ""),
                "priority": t.get("priority", "medium"),
                "depends_on": t.get("depends_on", []),
                "status": "pending",
                "dispatch_id": None,
                "verification": None,
            })
        self._plans[plan_id] = plan
        return json.dumps(plan, indent=2)

    def _handle_plan_list(self) -> str:
        summary = []
        for pid, p in self._plans.items():
            total = len(p["tasks"])
            done = sum(1 for t in p["tasks"] if t["status"] == "completed")
            summary.append({
                "id": pid, "title": p["title"],
                "status": p["status"],
                "progress": f"{done}/{total}",
            })
        return json.dumps(summary, indent=2) if summary else "No plans created yet."

    def _handle_plan_get(self, plan_id: str) -> str:
        plan = self._plans.get(plan_id)
        if not plan:
            return f"Error: Plan '{plan_id}' not found."
        return json.dumps(plan, indent=2)

    # ------------------------------------------------------------------
    # Engineer dispatch & monitoring
    # ------------------------------------------------------------------

    def _resolve_engineer(self, repo_name: str):
        """Resolve repo name → running EngineerManager, or None."""
        path_str = self._repo_reg.get(repo_name)
        if not path_str:
            return None, f"Repository '{repo_name}' not found in registry."
        mgr = self._eng_reg.get(Path(path_str))
        if mgr is None or not mgr.is_running:
            return None, f"No running engineer for '{repo_name}'. Start one first."
        return mgr, None

    def _handle_dispatch(self, repo: str, prompt: str,
                         plan_id: str | None = None,
                         task_index: int | None = None) -> str:
        mgr, err = self._resolve_engineer(repo)
        if err:
            return f"Error: {err}"

        dispatch_id = str(uuid.uuid4())[:8]
        mgr.send_message(prompt, source="Project Manager")

        tracking = {
            "dispatch_id": dispatch_id,
            "repo": repo,
            "prompt": prompt[:200],
            "plan_id": plan_id,
            "task_index": task_index,
            "status": "dispatched",
        }
        self._dispatched[dispatch_id] = tracking

        # Update plan task status
        if plan_id and task_index is not None:
            plan = self._plans.get(plan_id)
            if plan and 0 <= task_index < len(plan["tasks"]):
                plan["tasks"][task_index]["status"] = "in_progress"
                plan["tasks"][task_index]["dispatch_id"] = dispatch_id

        self._emit_event(PMTaskDispatchedEvent(
            repo=repo, dispatch_id=dispatch_id, prompt=prompt[:200],
        ))
        return json.dumps(tracking, indent=2)

    def _handle_check_engineer(self, repo: str) -> str:
        mgr, err = self._resolve_engineer(repo)
        if err:
            return f"Error: {err}"

        events = mgr.get_event_history()
        recent = events[-10:] if len(events) > 10 else events

        status_info = {
            "repo": repo,
            "status": mgr.status.name,
            "total_events": len(events),
            "recent_events": [
                {
                    "kind": getattr(e, "kind", "?").name if hasattr(getattr(e, "kind", None), "name") else str(getattr(e, "kind", "?")),
                    "text": getattr(e, "text", "")[:200] if hasattr(e, "text") else "",
                    "tool_name": getattr(e, "tool_name", None),
                    "error": getattr(e, "error", None),
                }
                for e in recent
            ],
        }
        return json.dumps(status_info, indent=2)

    def _handle_list_engineers(self) -> str:
        engineers = []
        for key, mgr in self._eng_reg.all_managers().items():
            engineers.append({
                "workdir": key,
                "name": Path(key).name,
                "status": mgr.status.name,
                "is_running": mgr.is_running,
            })
        return json.dumps(engineers, indent=2) if engineers else "No engineers running."

    def _handle_stop_engineer(self, repo: str) -> str:
        path_str = self._repo_reg.get(repo)
        if not path_str:
            return f"Error: Repository '{repo}' not found."
        self._eng_reg.remove(Path(path_str))
        return f"Engineer for '{repo}' stopped and removed."

    # ------------------------------------------------------------------
    # Synchronous wait (Promise-style)
    # ------------------------------------------------------------------

    def _handle_wait_for_engineer(self, repo: str, timeout: int = 300) -> str:
        """Block until the engineer for *repo* becomes idle, then return its result."""
        mgr, err = self._resolve_engineer(repo)
        if err:
            return f"Error: {err}"

        self._emit_event(PMProgressEvent(
            phase="waiting",
            detail=f"Waiting for {repo} engineer (timeout {timeout}s)\u2026",
        ))

        ok = mgr.wait_until_idle(timeout=timeout)
        if not ok:
            return json.dumps({
                "repo": repo,
                "status": "timeout",
                "message": f"Engineer did not finish within {timeout}s.",
            })

        last = mgr.get_last_response()
        events = mgr.get_event_history()
        recent_events = events[-5:] if len(events) > 5 else events

        return json.dumps({
            "repo": repo,
            "status": "completed",
            "last_response": last[:3000] if last else "(no text response)",
            "engineer_status": mgr.status.name,
            "recent_events": [
                {
                    "kind": getattr(e, "kind", "?").name if hasattr(getattr(e, "kind", None), "name") else str(getattr(e, "kind", "?")),
                    "text": getattr(e, "text", "")[:300] if hasattr(e, "text") else "",
                }
                for e in recent_events
            ],
        }, indent=2)

    def _handle_wait_for_engineers(self, repos: list[str], timeout: int = 600) -> str:
        """Wait for multiple engineers in parallel (Promise.all semantics)."""
        # Resolve all engineers first
        engineers: list[tuple[str, Any]] = []
        errors: list[dict] = []
        for repo in repos:
            mgr, err = self._resolve_engineer(repo)
            if err:
                errors.append({"repo": repo, "error": err})
            else:
                engineers.append((repo, mgr))

        if not engineers:
            return json.dumps({"errors": errors, "results": []}, indent=2)

        self._emit_event(PMProgressEvent(
            phase="waiting",
            detail=f"Waiting for {len(engineers)} engineer(s) (timeout {timeout}s)\u2026",
        ))

        # Wait for all with a shared deadline
        deadline = time.monotonic() + timeout
        results: list[dict] = []
        for repo, mgr in engineers:
            remaining = max(0.1, deadline - time.monotonic())
            ok = mgr.wait_until_idle(timeout=remaining)
            if ok:
                last = mgr.get_last_response()
                results.append({
                    "repo": repo,
                    "status": "completed",
                    "last_response": last[:3000] if last else "(no text response)",
                })
            else:
                results.append({
                    "repo": repo,
                    "status": "timeout",
                    "message": "Did not finish before deadline.",
                })

        return json.dumps({"errors": errors, "results": results}, indent=2)

    # ------------------------------------------------------------------
    # Verification
    # ------------------------------------------------------------------

    def _handle_verify(self, repo: str, criteria: str,
                       plan_id: str | None = None,
                       task_index: int | None = None) -> str:
        mgr, err = self._resolve_engineer(repo)
        if err:
            return f"Error: {err}"

        verification_prompt = (
            "VERIFICATION REQUEST: Please verify the following has been completed correctly.\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            "Inspect the relevant files and tests, then respond with:\n"
            "1. PASS or FAIL\n"
            "2. A brief explanation of what you found.\n"
            "3. Any remaining issues."
        )
        mgr.send_message(verification_prompt, source="Project Manager")

        result = {
            "repo": repo,
            "status": "verification_dispatched",
            "criteria": criteria,
        }

        if plan_id and task_index is not None:
            plan = self._plans.get(plan_id)
            if plan and 0 <= task_index < len(plan["tasks"]):
                plan["tasks"][task_index]["verification"] = "pending"

        self._emit_event(PMTaskVerifiedEvent(
            repo=repo, criteria=criteria[:200],
        ))
        return json.dumps(result, indent=2)

    # ------------------------------------------------------------------
    # Cross-repo coordination
    # ------------------------------------------------------------------

    def _handle_broadcast(self, message: str) -> str:
        count = 0
        for _key, mgr in self._eng_reg.all_managers().items():
            if mgr.is_running:
                mgr.send_message(f"[FROM PROJECT MANAGER]: {message}", source="Project Manager")
                count += 1
        return f"Broadcast sent to {count} engineer(s)."

    def _handle_query(self, repo: str, question: str) -> str:
        mgr, err = self._resolve_engineer(repo)
        if err:
            return f"Error: {err}"
        mgr.send_message(f"[PROJECT MANAGER QUERY]: {question}", source="Project Manager")
        return f"Query sent to '{repo}' engineer. Check status later with check_engineer."

    # ------------------------------------------------------------------
    # Debate / synchronous discussion
    # ------------------------------------------------------------------

    def _handle_discuss(self, repo: str, message: str, timeout: int = 300) -> str:
        """Send a message to an engineer and block until it replies.

        This is the core "debate" primitive: the PM sends a question,
        critique, or design proposal, then waits for the engineer to
        finish its tool loop before reading the response.
        """
        mgr, err = self._resolve_engineer(repo)
        if err:
            return f"Error: {err}"

        self._emit_event(PMProgressEvent(
            phase="discussing",
            detail=f"Discussing with {repo} engineer\u2026",
        ))
        mgr.send_message(
            f"[PROJECT MANAGER — DISCUSSION]: {message}",
            source="Project Manager",
        )
        ok = mgr.wait_until_idle(timeout=timeout)
        if not ok:
            return json.dumps({
                "repo": repo, "status": "timeout",
                "message": f"Engineer did not respond within {timeout}s.",
            })

        last = mgr.get_last_response()
        return json.dumps({
            "repo": repo,
            "status": "replied",
            "response": last[:5000] if last else "(no text response)",
        }, indent=2)

    # ------------------------------------------------------------------
    # Cross-repo context sharing
    # ------------------------------------------------------------------

    def _handle_share_context(
        self, source_repo: str, source_path: str,
        target_repo: str, message: str,
    ) -> str:
        """Read a file from *source_repo* and relay it to *target_repo*'s engineer."""
        # Read content from source repo (reuses base_tools.run_read)
        content = self._repo_tool(source_repo, run_read, source_path)
        if content.startswith("Error:"):
            return content

        target_mgr, err = self._resolve_engineer(target_repo)
        if err:
            return f"Error (target): {err}"

        relay = (
            f"[CROSS-REPO CONTEXT from {source_repo}]\n"
            f"File: {source_path}\n"
            f"Note: {message}\n\n"
            f"```\n{content[:8000]}\n```"
        )
        target_mgr.send_message(relay, source="Project Manager")
        return (
            f"Shared {source_repo}/{source_path} "
            f"({len(content)} chars) with {target_repo} engineer."
        )

    # ------------------------------------------------------------------
    # Background execution (repo-scoped)
    # ------------------------------------------------------------------

    def _handle_background_run(self, repo: str, command: str, timeout: int = 120) -> str:
        bg, err = self._get_bg_manager(repo)
        if err:
            return f"Error: {err}"
        return bg.run(command, timeout)

    def _handle_check_background(self, task_id: str | None = None) -> str:
        # Aggregate across all repo bg managers
        if task_id:
            for bg in self._bg_managers.values():
                result = bg.check(task_id)
                if not result.startswith("Unknown"):
                    return result
            return f"Unknown task: {task_id}"
        parts = []
        for repo_path, bg in self._bg_managers.items():
            status = bg.check()
            if status != "No bg tasks.":
                parts.append(f"[{Path(repo_path).name}]\n{status}")
        return "\n\n".join(parts) if parts else "No background tasks."

    # ------------------------------------------------------------------
    # Todo / progress
    # ------------------------------------------------------------------

    def _handle_todo_write(self, items: list) -> str:
        result = self.todo.update(items)
        self._emit_event(TodoUpdatedEvent(
            workdir="project_manager", items=self.todo.items,
        ))
        return result

    def _handle_progress_report(self) -> str:
        report = {
            "plans": [],
            "engineers": [],
            "dispatched_tasks": len(self._dispatched),
        }
        for pid, plan in self._plans.items():
            total = len(plan["tasks"])
            done = sum(1 for t in plan["tasks"] if t["status"] == "completed")
            in_prog = sum(1 for t in plan["tasks"] if t["status"] == "in_progress")
            report["plans"].append({
                "id": pid, "title": plan["title"],
                "total": total, "completed": done, "in_progress": in_prog,
            })
        for key, mgr in self._eng_reg.all_managers().items():
            report["engineers"].append({
                "repo": Path(key).name,
                "status": mgr.status.name,
                "is_running": mgr.is_running,
                "events_count": len(mgr.get_event_history()),
            })
        return json.dumps(report, indent=2)

    # ------------------------------------------------------------------
    # System prompt
    # ------------------------------------------------------------------

    def _system_prompt(self) -> str:
        os_info = f"{platform.system()} ({platform.machine()})"
        shell_hint = (
            "The shell is PowerShell. Use PowerShell syntax for bash commands "
            "(e.g. Get-ChildItem instead of ls, Get-Content instead of cat, "
            "Select-String instead of grep)."
            if platform.system() == "Windows"
            else ""
        )

        repos = self._repo_reg.all_repos()  # {name: path}
        repo_list = "\n".join(
            f"  - {name}: {path}" for name, path in repos.items()
        ) if repos else "  (none registered)"

        running = [
            Path(k).name
            for k, m in self._eng_reg.all_managers().items()
            if m.is_running
        ]

        return (
            f"You are a **Project Manager** agent — a senior technical lead "
            f"who coordinates multi-repository software projects.\n"
            f"OS: {os_info}. {shell_hint}\n\n"
            f"REGISTERED REPOSITORIES:\n{repo_list}\n\n"
            f"RUNNING ENGINEERS: {', '.join(running) if running else 'none'}\n\n"
            # ---- MINDSET ----
            "MINDSET: You are a hands-on tech lead, not a blind dispatcher.\n"
            "Read and understand code BEFORE planning. Think critically about "
            "architecture, deps, and risks. Make small cross-repo fixes yourself "
            "when delegation is wasteful.\n\n"
            # ---- TOOLS ----
            "TOOLS:\n"
            "- DIRECT: bash, read_file, write_file, edit_file (scoped to any repo).\n"
            "- COORDINATION: plan_create, dispatch_task, wait_for_engineer, "
            "discuss_with_engineer, verify_task, share_context, broadcast_engineers.\n\n"
            # ---- WORKFLOW ----
            "WORKFLOW:\n"
            "1. UNDERSTAND — Read code across repos before planning.\n"
            "2. PLAN — plan_create with file paths, test commands, acceptance criteria.\n"
            "3. EXECUTE — Self-do (small/cross-repo) or dispatch (large/isolated).\n"
            "4. COORDINATE — share_context to relay APIs/types between repos.\n"
            "5. REVIEW — Read engineer changes, discuss_with_engineer to debate.\n"
            "6. VERIFY — Run tests, check acceptance criteria end-to-end.\n"
            "7. REPORT — Summarize results and remaining risks.\n\n"
            # ---- MANDATORY MONITORING ----
            "MANDATORY MONITORING (CRITICAL):\n"
            "You are RESPONSIBLE for every task you assign. You MUST await and "
            "monitor engineer responses every time you send a message or dispatch "
            "a task. Never fire-and-forget.\n"
            "- After dispatch_task → ALWAYS call wait_for_engineer immediately.\n"
            "- After discuss_with_engineer → read the reply and act on it.\n"
            "- After query_engineer → follow up with check_engineer or wait_for_engineer.\n"
            "- For parallel dispatches → wait_for_engineers for all of them.\n"
            "- After verification → read the result and confirm PASS/FAIL.\n"
            "- If an engineer times out or fails → re-dispatch, debug, or do it yourself.\n"
            "- Do NOT move to the next task until the current one is confirmed done.\n"
            "- Track ALL dispatched work with TodoWrite and progress_report.\n\n"
            # ---- RULES ----
            "RULES:\n"
            "- Always read code before dispatching tasks about it.\n"
            "- Be specific: include file paths, test commands, acceptance criteria.\n"
            "- Prefer fewer, well-scoped tasks over many small ones.\n"
            "- Challenge engineers when their approach seems wrong.\n"
            "- Keep shared interfaces and configs in sync across repos.\n"
        )

    # ------------------------------------------------------------------
    # Agent loop
    # ------------------------------------------------------------------

    def _agent_loop(self) -> None:
        """Process user messages via the PM tool loop."""
        msgs = self._messages
        _log.debug("[PM] _agent_loop STARTED")

        while not self._stop.is_set():
            self._wake.wait()
            if self._stop.is_set():
                break
            self._wake.clear()

            while not self._stop.is_set():
                try:
                    user_text = self._inbox.get_nowait()
                except Empty:
                    break

                self.status = PMStatus.RUNNING
                msgs.append({"role": "user", "content": user_text})
                self._emit_event(PMStartedEvent())

                self._cancel.clear()
                try:
                    self._run_tool_loop(msgs)
                except Exception:
                    _log.exception("PM agent loop error")
                    self._emit_event(PMErrorEvent(
                        error="Internal project manager error – see logs.",
                    ))
                finally:
                    self._cancel.clear()
                    self.status = PMStatus.IDLE
                    self._emit_event(PMStoppedEvent())

    def _run_tool_loop(self, msgs: list) -> None:
        """Inner loop: LLM call → tool dispatch → repeat until end_turn."""
        tool_round = 0
        while not self._stop.is_set() and not self._cancel.is_set():
            tool_round += 1
            if tool_round > MAX_TOOL_ROUNDS:
                _log.warning("PM tool-loop hit %d rounds, forcing stop", MAX_TOOL_ROUNDS)
                self._emit_event(PMMessageEvent(
                    text=f"\u26a0\ufe0f Reached maximum tool rounds ({MAX_TOOL_ROUNDS}).",
                ))
                break

            # -- compression --
            microcompact(msgs)
            if estimate_tokens(msgs) > TOKEN_THRESHOLD:
                self._emit_event(PMProgressEvent(
                    phase="compressing",
                    detail="Compacting conversation history\u2026",
                ))
                msgs[:] = auto_compact(msgs, self._llm, Path("."))

            # -- drain background notifications --
            bg_notifs: list[str] = []
            for repo_path, bg in self._bg_managers.items():
                for n in bg.drain():
                    bg_notifs.append(
                        f"[bg:{n['task_id']}@{Path(repo_path).name}] "
                        f"{n['status']}: {n['result']}"
                    )
            if bg_notifs:
                msgs.append({
                    "role": "user",
                    "content": f"<background-results>\n{''.join(bg_notifs)}\n</background-results>",
                })
                msgs.append({"role": "assistant", "content": "Noted background results."})

            # -- LLM call --
            self._emit_event(PMProgressEvent(
                phase="thinking",
                detail=f"Thinking (round {tool_round})\u2026",
            ))

            # Merge built-in PM tools with MCP tools (respect provider limit)
            all_tools = PM_TOOLS
            if self._mcp:
                budget = self._llm.MAX_TOOLS - len(PM_TOOLS)
                mcp_tools = self._mcp.get_all_mcp_tool_definitions(budget=budget)
                if mcp_tools:
                    all_tools = PM_TOOLS + mcp_tools

            response = self._llm.send_with_tools(
                msgs, all_tools, self._system_prompt(),
            )
            msgs.append(response.assistant_message)

            if response.text:
                self._emit_event(PMMessageEvent(text=response.text))

            if response.stop_reason != "tool_use":
                break

            # -- tool dispatch --
            results = []
            manual_compress = False
            for tc in response.tool_calls:
                if self._cancel.is_set():
                    break
                if tc.name == "compress":
                    manual_compress = True

                # Build descriptive progress detail
                if tc.name == "bash":
                    cmd_preview = tc.input.get("command", "")[:80]
                    repo_label = tc.input.get("repo", "?")
                    progress_detail = f"[{repo_label}] Running: {cmd_preview}\u2026"
                elif tc.name in ("read_file", "write_file", "edit_file"):
                    repo_label = tc.input.get("repo", "?")
                    path_label = tc.input.get("path", "?")
                    progress_detail = f"[{repo_label}] {tc.name}: {path_label}"
                elif tc.name == "discuss_with_engineer":
                    progress_detail = f"Discussing with {tc.input.get('repo', '?')} engineer\u2026"
                elif tc.name == "share_context":
                    progress_detail = (
                        f"Sharing {tc.input.get('source_repo', '?')}/"
                        f"{tc.input.get('source_path', '?')} → "
                        f"{tc.input.get('target_repo', '?')}"
                    )
                else:
                    progress_detail = f"Running {tc.name}\u2026"

                self._emit_event(PMProgressEvent(
                    phase="executing_tool",
                    detail=progress_detail,
                ))
                handler = self._handlers.get(tc.name)
                try:
                    if self._mcp and self._mcp.is_mcp_tool(tc.name):
                        output = self._mcp.call_mcp_tool(tc.name, tc.input)
                    elif handler:
                        output = handler(**tc.input)
                    else:
                        output = f"Unknown tool: {tc.name}"
                except Exception as e:
                    output = f"Error: {e}"
                    _log.warning("[PM TOOL] %s raised: %s", tc.name, e)
                results.append({"tool_use_id": tc.id, "output": str(output)})
                self._emit_event(PMToolCallEvent(
                    tool_name=tc.name, tool_input=tc.input,
                ))
                self._emit_event(PMToolResultEvent(
                    tool_name=tc.name, output=str(output)[:2000],
                ))

            # Ensure ALL tool_use blocks get a tool_result (cancel may
            # have skipped some).  The API requires 1-to-1 matching.
            result_ids = {r["tool_use_id"] for r in results}
            for tc in response.tool_calls:
                if tc.id not in result_ids:
                    results.append({
                        "tool_use_id": tc.id,
                        "output": "[cancelled]",
                    })

            msgs.extend(self._llm.make_tool_results(results))

            if manual_compress:
                msgs[:] = auto_compact(msgs, self._llm, Path("."))

        if self._cancel.is_set():
            msgs.append({"role": "assistant", "content": "[Cancelled by user]"})
            self._emit_event(PMMessageEvent(text="\u26d4 Stopped by user."))

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------

    def _emit_event(self, event: Any) -> None:
        with self._log_lock:
            self._event_log.append(event)
        if self._event_bus is not None:
            self._event_bus.emit_async(event)

    # ------------------------------------------------------------------
    # Public API (thread-safe)
    # ------------------------------------------------------------------

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self.status = PMStatus.IDLE
        self._thread = threading.Thread(
            target=self._agent_loop, daemon=True,
            name="project-manager",
        )
        self._thread.start()

    def get_event_history(self) -> list:
        with self._log_lock:
            return list(self._event_log)

    def send_message(self, text: str) -> None:
        self._inbox.put(text)
        self.wake()

    def wake(self) -> None:
        self._wake.set()

    def cancel(self) -> None:
        self._cancel.set()

    def shutdown(self) -> None:
        self._stop.set()
        self._wake.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self.status = PMStatus.STOPPED

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
