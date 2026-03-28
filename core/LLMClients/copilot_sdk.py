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

from .base import LLMClient, LLMResponse, ToolCall

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

    # The SDK handles tools internally; this limit is informational only.
    MAX_TOOLS = 0

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

        # Background asyncio event loop (created lazily)
        self._loop: asyncio.AbstractEventLoop | None = None
        self._loop_thread: threading.Thread | None = None

        # SDK objects (created lazily)
        self._client = None           # CopilotClient
        self._session = None          # Active session
        self._last_system: str = ""   # System prompt used to create session
        self._lock = threading.Lock() # Guards lazy init

    # ------------------------------------------------------------------ #
    #  Async ↔ sync bridge                                                #
    # ------------------------------------------------------------------ #

    def _ensure_loop(self) -> None:
        """Spin up a dedicated asyncio event loop in a daemon thread."""
        if self._loop is not None and self._loop.is_running():
            return
        self._loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._loop.run_forever,
            daemon=True,
            name="copilot-sdk-loop",
        )
        self._loop_thread.start()

    def _run(self, coro, *, timeout: float = 300):
        """Submit an async coroutine and block the calling thread."""
        with self._lock:
            self._ensure_loop()
        assert self._loop is not None
        fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    # ------------------------------------------------------------------ #
    #  SDK lifecycle                                                      #
    # ------------------------------------------------------------------ #

    async def _ensure_client(self):
        if self._client is not None:
            return
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
        self._client = CopilotClient(config)
        await self._client.start()

    async def _ensure_session(self, system: str = ""):
        await self._ensure_client()

        need_new = (
            self._session is None
            or (system and system != self._last_system)
        )
        if not need_new:
            return self._session

        # Tear down old session
        if self._session is not None:
            try:
                await self._session.disconnect()
            except Exception:
                _log.debug("session disconnect error (ignored)", exc_info=True)
            self._session = None

        from copilot import PermissionHandler

        kw: dict = {
            "on_permission_request": PermissionHandler.approve_all,
            "model": self._model,
        }
        if system:
            kw["system_message"] = {"content": system}

        self._session = await self._client.create_session(**kw)
        self._last_system = system
        return self._session

    async def _send_and_collect(self, message: str, system: str = "") -> str:
        """Send *message*, wait for the agent to go idle, return text."""
        session = await self._ensure_session(system)
        done = asyncio.Event()
        collected: list[str] = []

        def _on_event(event):
            etype = event.type.value
            if etype == "assistant.message":
                content = getattr(event.data, "content", None)
                if content:
                    collected.append(content)
            elif etype == "session.idle":
                done.set()

        unsub = session.on(_on_event)
        try:
            await session.send(message)
            await asyncio.wait_for(done.wait(), timeout=300)
        finally:
            if callable(unsub):
                unsub()

        return "\n".join(collected) if collected else ""

    async def _cleanup(self):
        try:
            if self._session:
                await self._session.disconnect()
                self._session = None
        except Exception:
            pass
        try:
            if self._client:
                await self._client.stop()
                self._client = None
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    #  LLMClient interface                                                #
    # ------------------------------------------------------------------ #

    def close(self) -> None:
        """Shut down the CLI subprocess and background event loop."""
        if self._loop and (self._client or self._session):
            try:
                fut = asyncio.run_coroutine_threadsafe(
                    self._cleanup(), self._loop
                )
                fut.result(timeout=10)
            except Exception:
                _log.debug("close() cleanup error", exc_info=True)
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._loop = None
            self._loop_thread = None

    def provider_name(self) -> str:
        return self.PROVIDER

    def model_id(self) -> str:
        return self._model

    def send_message(self, message: str, history: list[dict] | None = None) -> str:
        return self._run(self._send_and_collect(message))

    def send_messages(self, messages: list[dict]) -> str:
        last_user = self._extract_last_user_message(messages)
        return self._run(self._send_and_collect(last_user))

    def is_available(self) -> bool:
        try:
            self._run(self._ensure_session(), timeout=30)
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
        built-in tools (file editing, shell, reading, etc.).  We pass the
        latest user message, wait for the agent to finish all rounds, and
        return the final assistant text with ``stop_reason="end_turn"``.
        """
        last_user = self._extract_last_user_message(messages)
        if not last_user:
            return LLMResponse(
                text="",
                tool_calls=[],
                stop_reason="end_turn",
                assistant_message={"role": "assistant", "content": ""},
            )

        text = self._run(self._send_and_collect(last_user, system=system))
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
