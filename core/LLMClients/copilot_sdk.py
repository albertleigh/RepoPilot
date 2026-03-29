"""Copilot SDK provider — GitHub Copilot models via github-copilot-sdk.

The SDK communicates with the Copilot CLI server via JSON-RPC and provides
access to GitHub Copilot models.  Authentication is through GitHub CLI login
(``copilot auth login``) or a personal-access / OAuth token.

The SDK manages its own agent loop with built-in tools (file editing, shell
commands, file reading, etc.).  When used through RepoPilot's engineer agent
the SDK handles tool execution internally and returns the final assistant
response.

Prerequisites
-------------
* ``pip install github-copilot-sdk``
* GitHub Copilot CLI installed and accessible in PATH
* A valid GitHub Copilot subscription (free tier included)
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Any, Callable

from .base import LLMClient, LLMResponse, ToolCall


@dataclass
class _CallerContext:
    """Per-thread state — own event loop, CLI subprocess, and session."""

    loop: Any = None              # asyncio event loop (dedicated thread)
    loop_thread: Any = None       # Thread running the event loop
    client: Any = None            # CopilotClient (own subprocess)
    session: Any = None
    last_system: str = ""
    last_tool_names: frozenset[str] = field(default_factory=frozenset)
    tool_handlers: dict[str, Callable[..., Any]] = field(default_factory=dict)
    mcp_registry: Any = None

_log = logging.getLogger(__name__)

# Hard-coded known models.  The Copilot SDK routes to GitHub's infrastructure
# and model availability may change over time.  Update this list when GitHub
# adds or retires models.  Users can also type any model string manually.
KNOWN_MODELS = [
    "claude-sonnet-4.6",
    "claude-opus-4.6",
    "claude-opus-4.6-1m",
    "claude-sonnet-4.5",
    "claude-sonnet-4",
    "gpt-5.4",
    "gpt-5.1-codex",
    "gpt-4.1",
]
DEFAULT_MODEL = "claude-sonnet-4.6"


class CopilotSDKClient(LLMClient):
    """LLM provider backed by the GitHub Copilot SDK."""

    PROVIDER = "Copilot SDK (GitHub Login)"

    FIELDS = [
        {
            "type": "action",
            "key": "github_login",
            "label": "Login with GitHub",
        },
        {
            "type": "choices",
            "key": "model",
            "label": "Model",
            "placeholder": f"e.g. {', '.join(KNOWN_MODELS)}",
            "default": DEFAULT_MODEL,
            "required": True,
            "secret": False,
        },
        {
            "key": "github_token",
            "label": "GitHub Token (optional — leave blank to use CLI login)",
            "placeholder": "ghp_… or leave empty for CLI auth",
            "default": "",
            "required": False,
            "secret": True,
        },
    ]

    # The SDK has its own built-in tools.  We also forward RepoPilot's
    # custom tools (TodoWrite, MCP tools, etc.) to the SDK session.
    MAX_TOOLS = 128

    # Cached model list (class-level, shared across instances)
    _cached_models: list[str] | None = None

    @classmethod
    def on_field_action(cls, key: str) -> dict:
        if key == "github_login":
            return cls._launch_github_login()
        return {}

    @classmethod
    def get_field_choices(cls, key: str) -> list[str]:
        if key == "model":
            return cls._fetch_models()
        return []

    @classmethod
    def _fetch_models(cls) -> list[str]:
        """Query the SDK for available models, with fallback to KNOWN_MODELS."""
        if cls._cached_models is not None:
            return cls._cached_models

        try:
            from copilot import CopilotClient

            async def _list():
                client = CopilotClient()
                await client.start()
                try:
                    models = await client.list_models()
                    return [m.id for m in models]
                finally:
                    await client.stop()

            loop = asyncio.new_event_loop()
            try:
                model_ids = loop.run_until_complete(
                    asyncio.wait_for(_list(), timeout=15)
                )
            finally:
                loop.close()

            if model_ids:
                cls._cached_models = model_ids
                return model_ids
        except Exception:
            _log.debug("Failed to fetch models from SDK", exc_info=True)

        return list(KNOWN_MODELS)

    @classmethod
    def _launch_github_login(cls) -> dict:
        """Launch ``copilot login`` in a visible console window."""
        import subprocess
        import sys

        try:
            from copilot.client import _get_bundled_cli_path
        except ImportError:
            return {
                "status": "error",
                "message": (
                    "github-copilot-sdk is not installed.\n"
                    "Run:  pip install github-copilot-sdk"
                ),
            }

        cli_path = _get_bundled_cli_path()
        if not cli_path:
            return {
                "status": "error",
                "message": "Copilot CLI binary not found in the SDK package.",
            }

        try:
            kwargs: dict = {}
            if sys.platform == "win32":
                kwargs["creationflags"] = subprocess.CREATE_NEW_CONSOLE
            subprocess.Popen([cli_path, "login"], **kwargs)
            return {
                "status": "launched",
                "message": (
                    "A login window has opened.\n\n"
                    "Complete the GitHub login in your browser, "
                    "then use 'Test Connection' to verify."
                ),
            }
        except Exception as exc:
            return {
                "status": "error",
                "message": f"Failed to launch login:\n{exc}",
            }

    def __init__(self, model: str = DEFAULT_MODEL, github_token: str = ""):
        self._model = model.strip() or DEFAULT_MODEL
        self._github_token = github_token.strip() if github_token else ""

        # Per-caller contexts keyed by thread ID.  Each engineer,
        # project manager, or teammate thread gets its own event loop,
        # CopilotClient (CLI subprocess), session, tool handlers, and
        # system prompt so they are fully isolated.
        self._callers: dict[int, _CallerContext] = {}
        self._callers_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    #  External tool registration                                         #
    # ------------------------------------------------------------------ #

    def register_tool_handlers(
        self,
        handlers: dict[str, Callable[..., Any]],
        mcp_registry=None,
    ) -> None:
        """Register RepoPilot tool handlers so the SDK can invoke them.

        Called by the engineer/PM/teammate before entering its tool loop.
        *handlers* maps tool name → callable(**kwargs) → str.
        *mcp_registry* is the optional ``McpServerRegistry`` for MCP tools.

        State is stored per-thread so concurrent callers don't
        overwrite each other's handlers.
        """
        ctx = self._get_caller_ctx()
        ctx.tool_handlers = handlers
        ctx.mcp_registry = mcp_registry

    def _get_caller_ctx(self) -> _CallerContext:
        """Return the ``_CallerContext`` for the current thread."""
        tid = threading.get_ident()
        with self._callers_lock:
            ctx = self._callers.get(tid)
            if ctx is None:
                ctx = _CallerContext()
                self._callers[tid] = ctx
            return ctx

    # ------------------------------------------------------------------ #
    #  Async ↔ sync bridge                                                #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _ensure_loop(ctx: _CallerContext) -> None:
        """Spin up a dedicated asyncio event loop for this caller."""
        if ctx.loop is not None and ctx.loop.is_running():
            return
        ctx.loop = asyncio.new_event_loop()
        ctx.loop_thread = threading.Thread(
            target=ctx.loop.run_forever,
            daemon=True,
            name=f"copilot-sdk-loop-{threading.get_ident()}",
        )
        ctx.loop_thread.start()

    def _run(self, coro, *, timeout: float | None = None):
        """Submit an async coroutine and block the calling thread.

        If *timeout* is ``None`` (default), waits indefinitely — the
        coroutine is expected to manage its own internal timeouts via
        ``asyncio.wait_for``.  If a finite timeout is given and expires,
        the future is **cancelled** so no zombie coroutine is left
        behind, and the empty-string fallback is returned instead of
        raising ``TimeoutError``.
        """
        ctx = self._get_caller_ctx()
        self._ensure_loop(ctx)
        assert ctx.loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, ctx.loop)
        try:
            return fut.result(timeout=timeout)
        except TimeoutError:
            fut.cancel()
            _log.error("[SDK] _run: outer timeout fired (%s s), future cancelled", timeout)
            return ""

    # ------------------------------------------------------------------ #
    #  SDK lifecycle                                                      #
    # ------------------------------------------------------------------ #

    async def _ensure_client(self, caller_ctx: _CallerContext):
        if caller_ctx.client is not None:
            _log.debug("[SDK] _ensure_client: reusing existing client (tid=%d)", threading.get_ident())
            return
        _log.info("[SDK] _ensure_client: creating new CopilotClient (tid=%d)", threading.get_ident())
        try:
            from copilot import CopilotClient, SubprocessConfig
        except ImportError as exc:
            raise RuntimeError(
                "github-copilot-sdk is not installed. "
                "Run:  pip install github-copilot-sdk"
            ) from exc

        cfg_kw: dict = {}
        if self._github_token:
            cfg_kw["github_token"] = self._github_token
            cfg_kw["use_logged_in_user"] = False

        config = SubprocessConfig(**cfg_kw) if cfg_kw else None
        caller_ctx.client = CopilotClient(config)
        await caller_ctx.client.start()

    async def _ensure_session(
        self,
        caller_ctx: _CallerContext,
        system: str = "",
        sdk_tools: list | None = None,
    ):
        await self._ensure_client(caller_ctx)

        tool_names = frozenset(
            t.name if hasattr(t, "name") else "" for t in (sdk_tools or [])
        )
        need_new = (
            caller_ctx.session is None
            or (system and system != caller_ctx.last_system)
            or tool_names != caller_ctx.last_tool_names
        )
        _log.debug(
            "[SDK] _ensure_session: need_new=%s, has_session=%s, "
            "system_changed=%s, tools_changed=%s, tool_count=%d",
            need_new, caller_ctx.session is not None,
            (system and system != caller_ctx.last_system),
            tool_names != caller_ctx.last_tool_names,
            len(sdk_tools or []),
        )
        if not need_new:
            return caller_ctx.session

        # Tear down old session
        if caller_ctx.session is not None:
            _log.debug("[SDK] Disconnecting old session")
            try:
                await caller_ctx.session.disconnect()
            except Exception:
                _log.debug("session disconnect error (ignored)", exc_info=True)
            caller_ctx.session = None

        from copilot import PermissionHandler

        kw: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "model": self._model,
        }
        if system:
            kw["system_message"] = {"content": system}
        if sdk_tools:
            kw["tools"] = sdk_tools

        _log.info(
            "[SDK] Creating new session: model=%s, has_system=%s, num_tools=%d (tid=%d)",
            self._model, bool(system), len(sdk_tools or []), threading.get_ident(),
        )
        caller_ctx.session = await caller_ctx.client.create_session(**kw)
        caller_ctx.last_system = system
        caller_ctx.last_tool_names = tool_names
        _log.debug("[SDK] Session created: %s", caller_ctx.session)
        return caller_ctx.session

    def _build_sdk_tools(
        self, tool_defs: list[dict], caller_ctx: _CallerContext,
    ) -> list:
        """Convert RepoPilot tool definitions to SDK ``Tool`` objects.

        Skips tools that overlap with the SDK's built-in tools (the CLI
        already has its own file-editing and shell tools).  For each
        remaining tool, wraps the registered handler so the SDK can
        invoke it during its agent loop.
        """
        from copilot.tools import Tool, ToolInvocation, ToolResult

        # Tools to skip: SDK built-ins that overlap, plus RepoPilot
        # internal-only tools that don't make sense inside the SDK agent.
        SDK_SKIP = frozenset({
            # SDK already provides these via the CLI
            "bash", "read_file", "write_file", "edit_file",
            # "task" conflicts with an SDK built-in tool of the same name
            "task",
            # Internal control signals, not real tools
            "compress", "idle",
        })

        sdk_tools: list[Tool] = []
        skipped: list[str] = []
        for tdef in tool_defs:
            name = tdef.get("name", "")
            if name in SDK_SKIP:
                skipped.append(name)
                continue

            handler_fn = caller_ctx.tool_handlers.get(name)
            is_mcp = (
                caller_ctx.mcp_registry is not None
                and caller_ctx.mcp_registry.is_mcp_tool(name)
            )
            if not handler_fn and not is_mcp:
                continue

            # Translate Anthropic schema → SDK parameters
            schema = tdef.get("input_schema", {})

            # Capture name/handler/mcp_registry in closure
            def _make_handler(
                tool_name: str,
                h: Callable[..., Any] | None,
                mcp: bool,
                mcp_reg,
            ):
                def _handler(invocation: ToolInvocation) -> ToolResult:
                    args = invocation.arguments or {}
                    try:
                        if mcp and mcp_reg:
                            out = mcp_reg.call_mcp_tool(
                                tool_name, args,
                            )
                        elif h:
                            out = h(**args)
                        else:
                            out = f"No handler for {tool_name}"
                    except Exception as exc:
                        out = f"Error: {exc}"
                    return ToolResult(
                        text_result_for_llm=str(out),
                        result_type="success",
                    )
                return _handler

            sdk_tools.append(Tool(
                name=name,
                description=tdef.get("description", ""),
                parameters=schema,
                handler=_make_handler(
                    name, handler_fn, is_mcp, caller_ctx.mcp_registry,
                ),
            ))
        _log.info(
            "[SDK] _build_sdk_tools: %d registered, %d skipped (%s), "
            "registered=%s",
            len(sdk_tools), len(skipped), skipped,
            [t.name for t in sdk_tools],
        )
        return sdk_tools

    async def _send_and_collect(
        self,
        message: str,
        caller_ctx: _CallerContext,
        system: str = "",
        sdk_tools: list | None = None,
        timeout: float = 900,
        max_retries: int = 2,
    ) -> str:
        """Send *message*, wait for the agent to go idle, return text.

        On timeout, tears down the stale session and retries up to
        *max_retries* times with a fresh session before giving up.
        """
        for attempt in range(1, max_retries + 1):
            _log.info(
                "[SDK] _send_and_collect attempt %d/%d: msg_len=%d, "
                "msg_preview=%.120s",
                attempt, max_retries, len(message), message,
            )
            try:
                session = await asyncio.wait_for(
                    self._ensure_session(
                        caller_ctx, system, sdk_tools=sdk_tools,
                    ),
                    timeout=60,
                )
            except asyncio.TimeoutError:
                _log.error(
                    "[SDK] _ensure_session timed out (attempt %d/%d)",
                    attempt, max_retries,
                )
                await self._destroy_session(caller_ctx)
                if attempt < max_retries:
                    _log.info("[SDK] Will retry after session setup timeout")
                    continue
                return ""

            done = asyncio.Event()
            collected: list[str] = []
            event_count = 0

            def _on_event(event):
                nonlocal event_count
                event_count += 1
                etype = event.type.value
                data = event.data

                data_summary = ""
                if hasattr(data, "content") and data.content:
                    data_summary = f", content_len={len(data.content)}"
                elif hasattr(data, "delta") and data.delta:
                    data_summary = f", delta_len={len(data.delta)}"
                elif hasattr(data, "message") and data.message:
                    data_summary = f", message={str(data.message)[:200]}"
                _log.info(
                    "[SDK] event #%d: type=%s%s",
                    event_count, etype, data_summary,
                )

                if etype == "assistant.message":
                    content = getattr(data, "content", None)
                    if content:
                        collected.append(content)
                elif etype == "assistant.message_delta":
                    delta = getattr(data, "delta", None) or getattr(data, "content", None)
                    if delta:
                        collected.append(delta)
                elif etype == "session.idle":
                    _log.info(
                        "[SDK] session.idle received after %d events, "
                        "collected %d message(s), total_len=%d",
                        event_count, len(collected),
                        sum(len(c) for c in collected),
                    )
                    done.set()
                elif etype == "session.error":
                    err_msg = getattr(data, "message", None) or str(data)
                    _log.error("[SDK] session.error: %s", err_msg)
                    done.set()

            unsub = session.on(_on_event)
            timed_out = False
            try:
                _log.debug("[SDK] Sending message to session...")
                await asyncio.wait_for(session.send(message), timeout=60)
                _log.debug("[SDK] session.send() returned, waiting for idle...")
                await asyncio.wait_for(done.wait(), timeout=timeout)
            except asyncio.TimeoutError:
                timed_out = True
                _log.error(
                    "[SDK] Timed out (attempt %d/%d)", attempt, max_retries,
                )
            except Exception:
                _log.exception("[SDK] Error in _send_and_collect")
            finally:
                if callable(unsub):
                    unsub()

            if timed_out:
                await self._destroy_session(caller_ctx)
                if attempt < max_retries:
                    _log.info("[SDK] Will retry with a fresh session")
                    continue
                # Final attempt also timed out — return whatever we got
                _log.warning(
                    "[SDK] All %d attempts timed out, returning partial "
                    "result (%d chars)",
                    max_retries, sum(len(c) for c in collected),
                )

            result = "\n".join(collected) if collected else ""
            _log.info(
                "[SDK] _send_and_collect done: attempt=%d, events=%d, "
                "collected=%d, result_len=%d",
                attempt, event_count, len(collected), len(result),
            )
            return result

        # Should never reach here, but just in case
        return ""

    async def _destroy_session(self, caller_ctx: _CallerContext) -> None:
        """Tear down a stale session so the next call creates a fresh one."""
        _log.warning("[SDK] Destroying stale session")
        try:
            if caller_ctx.session:
                await caller_ctx.session.disconnect()
        except Exception:
            _log.debug("session disconnect error (ignored)", exc_info=True)
        caller_ctx.session = None

    async def _cleanup_ctx(self, ctx: _CallerContext) -> None:
        """Disconnect session and stop client for a single caller."""
        try:
            if ctx.session:
                await ctx.session.disconnect()
                ctx.session = None
        except Exception:
            pass
        try:
            if ctx.client:
                await ctx.client.stop()
                ctx.client = None
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  LLMClient interface                                                #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Shut down all CLI subprocesses and background event loops."""
        with self._callers_lock:
            callers = list(self._callers.items())
            self._callers.clear()
        for tid, ctx in callers:
            if not ctx.loop or not ctx.loop.is_running():
                continue
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._cleanup_ctx(ctx), ctx.loop,
                )
                fut.result(timeout=10)
            except Exception:
                _log.debug("close() cleanup error for tid=%d", tid, exc_info=True)
            try:
                ctx.loop.call_soon_threadsafe(ctx.loop.stop)
            except Exception:
                pass
            ctx.loop = None
            ctx.loop_thread = None

    def provider_name(self) -> str:
        return self.PROVIDER

    def model_id(self) -> str:
        return self._model

    def send_message(self, message: str, history: list[dict] | None = None) -> str:
        ctx = self._get_caller_ctx()
        return self._run(self._send_and_collect(message, ctx))

    def send_messages(self, messages: list[dict]) -> str:
        ctx = self._get_caller_ctx()
        last_user = self._extract_last_user_message(messages)
        return self._run(self._send_and_collect(last_user, ctx))

    def is_available(self) -> bool:
        try:
            ctx = self._get_caller_ctx()
            self._run(self._ensure_session(ctx), timeout=30)
            return True
        except Exception:
            _log.debug("Copilot SDK not available", exc_info=True)
            return False

    def send_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        """Send via the Copilot SDK agent loop.

        The SDK manages tool calling internally through the Copilot CLI's
        built-in tools (file editing, shell, reading, etc.) **plus** any
        custom RepoPilot tools registered via ``register_tool_handlers``.
        We pass the latest user message, wait for the agent to finish all
        rounds, and return the final assistant text with
        ``stop_reason="end_turn"``.

        Each calling thread gets its own SDK session so concurrent
        engineers / PM / teammates don't interfere.
        """
        ctx = self._get_caller_ctx()
        tid = threading.get_ident()
        last_user = self._extract_last_user_message(messages)
        _log.info(
            "[SDK] send_with_tools: tid=%d, msg_count=%d, "
            "tool_count=%d, last_user_len=%d, last_user=%.120s",
            tid, len(messages), len(tools), len(last_user), last_user,
        )
        if not last_user:
            _log.warning("[SDK] send_with_tools: empty user message, returning early")
            return LLMResponse(
                text="",
                tool_calls=[],
                stop_reason="end_turn",
                assistant_message={"role": "assistant", "content": ""},
            )

        sdk_tools = self._build_sdk_tools(tools, ctx) if tools else None
        _log.debug(
            "[SDK] send_with_tools: built %d sdk_tools",
            len(sdk_tools) if sdk_tools else 0,
        )
        text = self._run(
            self._send_and_collect(
                last_user, ctx, system=system, sdk_tools=sdk_tools,
            )
        )
        _log.info(
            "[SDK] send_with_tools result: tid=%d, text_len=%d, text=%.200s",
            tid, len(text), text,
        )
        return LLMResponse(
            text=text,
            tool_calls=[],
            stop_reason="end_turn",
            assistant_message={"role": "assistant", "content": text},
        )

    def make_tool_results(self, results: list[dict]) -> list[dict]:
        # Tool execution is handled internally by the SDK — nothing to do.
        return []

    # ------------------------------------------------------------------ #
    #  Helpers                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_last_user_message(messages: list[dict]) -> str:
        """Pull the most recent user message text from a messages list."""
        for msg in reversed(messages):
            if msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                return " ".join(parts)
        return ""

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass
