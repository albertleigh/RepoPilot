"""
Abstract base class for LLM clients and a registry to manage them.
"""
from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


@dataclass
class ToolCall:
    """A single tool invocation requested by the LLM."""

    id: str
    name: str
    input: dict


@dataclass
class LLMResponse:
    """Structured response from an LLM that may include tool calls."""

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" or "tool_use"
    assistant_message: dict = field(default_factory=dict)


class LLMClient(ABC):
    """Abstract base for all LLM client implementations.

    Every provider adapter must implement these methods so that the rest
    of the application can treat all providers uniformly.

    Subclasses must also define two class-level attributes:

    - ``PROVIDER``  – human-readable provider label (str)
    - ``MAX_TOOLS`` – maximum number of tool definitions the provider
      API accepts per request (default 128).
    - ``FIELDS``    – list of field descriptors used by the creation
      dialog to render a data-driven form.  Each entry is a dict::

          {
              "key":         str,   # kwarg name passed to __init__
              "label":       str,   # UI label
              "placeholder": str,   # placeholder text
              "default":     str,   # pre-filled value ("" if empty)
              "required":    bool,
              "secret":      bool,  # True → password echo mode
              "type":        str,   # "text" (default), "action", or "choices"
          }

      Action fields render as a button instead of a text input.
      Clicking the button calls ``cls.on_field_action(key)``.

      Choices fields render as an editable combo-box populated by
      ``cls.get_field_choices(key)``.  The user can pick from the
      list or type a custom value.
    """

    PROVIDER: str = ""
    MAX_TOOLS: int = 128
    FIELDS: list[dict] = []
    RETRY_MAX_ATTEMPTS: int = 3
    RETRY_WAIT_SECONDS: int = 60

    # Optional callback for streaming progress updates during long
    # operations (e.g. SDK agent loops).  Set by the caller (manager)
    # before invoking send_with_tools.  Signature: (detail: str) -> None
    progress_callback: Callable[[str], None] | None = None

    @classmethod
    def on_field_action(cls, key: str) -> dict:
        """Handle a FIELDS entry of ``"type": "action"``.

        Called by the creation / configure dialog when the user clicks
        an action button.  *key* is the ``"key"`` value of the field.

        Returns a dict with ``"status"`` (``"ok"`` | ``"error"`` |
        ``"launched"``) and an optional ``"message"`` string that the
        dialog will display.
        """
        return {}

    @classmethod
    def get_field_choices(cls, key: str) -> list[str]:
        """Return available choices for a ``"type": "choices"`` field.

        Called by the dialog when rendering a choices field.  Override
        in subclasses to provide dynamic lists (e.g. model names from
        an API).  Return an empty list to show an empty editable combo.
        """
        return []

    # Exception types considered transient connection failures.
    _TRANSIENT_EXC_NAMES = frozenset({
        "APIConnectionError", "ConnectError", "ConnectTimeout",
    })

    def _is_transient(self, exc: Exception) -> bool:
        """Return True if *exc* is a transient error worth retrying."""
        status = getattr(exc, "status_code", None)
        if status in (429, 529):
            return True
        # Connection-level errors (DNS failure, timeout, reset, etc.)
        if type(exc).__name__ in self._TRANSIENT_EXC_NAMES:
            return True
        return False

    def _call_with_retry(self, func, *args, **kwargs):
        """Call *func* with automatic retry on transient errors.

        Retries on HTTP 429 (rate-limit), 529 (overloaded), and
        connection errors (DNS failures, timeouts) up to
        ``RETRY_MAX_ATTEMPTS`` times, waiting ``RETRY_WAIT_SECONDS``
        between each attempt.  Raises the original exception if all
        attempts are exhausted.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self.RETRY_MAX_ATTEMPTS + 1):
            try:
                return func(*args, **kwargs)
            except Exception as exc:
                if self._is_transient(exc) and attempt < self.RETRY_MAX_ATTEMPTS:
                    _log.warning(
                        "Transient API error %s (attempt %d/%d). "
                        "Retrying in %ds…",
                        type(exc).__name__,
                        attempt,
                        self.RETRY_MAX_ATTEMPTS,
                        self.RETRY_WAIT_SECONDS,
                    )
                    last_exc = exc
                    time.sleep(self.RETRY_WAIT_SECONDS)
                    continue
                raise
        raise last_exc  # should not be reached, but keeps linters happy

    @abstractmethod
    def provider_name(self) -> str:
        """Human-readable provider label (e.g. 'Claude on Azure')."""

    @abstractmethod
    def model_id(self) -> str:
        """Return the model identifier being used."""

    @abstractmethod
    def send_message(self, message: str, history: list[dict] | None = None) -> str:
        """Send a user message (with optional history) and return the
        assistant's text reply."""

    @abstractmethod
    def send_messages(self, messages: list[dict]) -> str:
        """Send a full messages list in provider format and return the
        assistant's text reply."""

    @abstractmethod
    def is_available(self) -> bool:
        """Quick connectivity / auth check.  Return True when usable."""

    @abstractmethod
    def send_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        """Send messages with tool definitions and return a structured
        response that may contain tool-use requests."""

    @abstractmethod
    def make_tool_results(self, results: list[dict]) -> list[dict]:
        """Convert tool execution results to provider-native message format.

        Each entry in *results* is ``{"tool_use_id": str, "output": str}``.
        Returns one or more message dicts to append to the conversation.
        """

    def close(self) -> None:
        """Release resources held by this client.

        Called by the registry when the client is replaced or removed.
        Override in subclasses that manage long-lived resources (e.g.
        background processes, persistent sessions).
        """


class LLMProviderRegistry:
    """Registry that maps provider names to their LLMClient subclasses.

    Used by the creation dialog to discover available providers and
    their form fields at runtime."""

    def __init__(self):
        self._providers: dict[str, type[LLMClient]] = {}

    def register(self, cls_: type[LLMClient]) -> type[LLMClient]:
        """Register a provider class.  Can also be used as a decorator."""
        self._providers[cls_.PROVIDER] = cls_
        return cls_

    def get(self, provider_name: str) -> type[LLMClient] | None:
        return self._providers.get(provider_name)

    def provider_names(self) -> list[str]:
        return list(self._providers.keys())

    def all_providers(self) -> dict[str, type[LLMClient]]:
        return dict(self._providers)


_log = logging.getLogger(__name__)

_LLM_CLIENTS_FILE = "llm_clients.json"
_LLM_SELECTED_FILE = "llm_selected.json"


class LLMClientRegistry:
    """Registry that keeps track of all configured LLM client instances
    at runtime **and** persists their configuration to disk.

    Parameters
    ----------
    base_dir:
        Application data directory (e.g. ``~/.manager_code``).
        The registry stores ``llm_clients.json`` there.
    provider_registry:
        Used when loading persisted configs to resolve provider classes.
    """

    def __init__(
        self,
        base_dir: Path | None = None,
        provider_registry: LLMProviderRegistry | None = None,
    ):
        self._clients: dict[str, LLMClient] = {}
        self._configs: dict[str, dict] = {}  # name → {"provider", "fields"}
        self._selected: str | None = None
        self._base_dir = base_dir
        self._provider_registry = provider_registry

    @property
    def _json_path(self) -> Path | None:
        if self._base_dir is None:
            return None
        return self._base_dir / _LLM_CLIENTS_FILE

    @property
    def _selected_path(self) -> Path | None:
        if self._base_dir is None:
            return None
        return self._base_dir / _LLM_SELECTED_FILE

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, name: str, client: LLMClient,
                 config: dict | None = None) -> None:
        """Register a live client and optionally its serialisable config.

        *config* should be ``{"provider": str, "fields": dict}`` so the
        client can be reconstructed after restart.
        """
        self._clients[name] = client
        if config is not None:
            self._configs[name] = config
        if self._selected is None:
            self._selected = name
            self._save_selected()
        self._save()

    def update(self, name: str, client: LLMClient,
               config: dict | None = None) -> None:
        """Replace an existing client's instance and config in-place."""
        old = self._clients.get(name)
        if old is not None and old is not client:
            try:
                old.close()
            except Exception:
                _log.debug("close() failed for %r", name, exc_info=True)
        self._clients[name] = client
        if config is not None:
            self._configs[name] = config
        self._save()

    def unregister(self, name: str) -> None:
        old = self._clients.pop(name, None)
        if old is not None:
            try:
                old.close()
            except Exception:
                _log.debug("close() failed for %r", name, exc_info=True)
        self._configs.pop(name, None)
        if self._selected == name:
            self._selected = None
            self._save_selected()
        self._save()

    def get(self, name: str) -> LLMClient | None:
        return self._clients.get(name)

    def get_config(self, name: str) -> dict | None:
        """Return the persisted config dict for *name*, or ``None``."""
        return self._configs.get(name)

    def all_clients(self) -> dict[str, LLMClient]:
        return dict(self._clients)

    def names(self) -> list[str]:
        return list(self._clients.keys())

    def count_by_provider(self, provider_name: str) -> int:
        """Return how many registered instances belong to *provider_name*."""
        return sum(
            1 for c in self._clients.values()
            if c.provider_name() == provider_name
        )

    def next_display_name(self, provider_name: str) -> str:
        """Generate a unique display name like 'Claude on Azure 1'."""
        n = self.count_by_provider(provider_name) + 1
        return f"{provider_name} {n}"

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def select(self, name: str | None) -> None:
        """Set the currently selected LLM client and persist the choice."""
        self._selected = name
        self._save_selected()

    def selected_name(self) -> str | None:
        """Return the display name of the currently selected client."""
        return self._selected

    def selected_client(self) -> LLMClient | None:
        """Return the live client instance for the current selection."""
        if self._selected is None:
            return None
        return self._clients.get(self._selected)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        """Write current configs to ``llm_clients.json``."""
        path = self._json_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._configs, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            _log.exception("Failed to save LLM client configs to %s", path)

    def _save_selected(self) -> None:
        """Write the selected client name to ``llm_selected.json``."""
        path = self._selected_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps({"selected": self._selected}, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            _log.exception("Failed to save selected LLM to %s", path)

    def _load_selected(self) -> None:
        """Read the selected client name from ``llm_selected.json``."""
        path = self._selected_path
        if path is None or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            name = raw.get("selected")
            if name and name in self._clients:
                self._selected = name
        except (OSError, json.JSONDecodeError):
            _log.exception("Failed to read selected LLM from %s", path)

    def load(self) -> None:
        """Load persisted client configs from disk and reconstruct live
        client instances.  Requires *provider_registry* to be set."""
        path = self._json_path
        if path is None or not path.exists():
            return
        if self._provider_registry is None:
            _log.warning("Cannot load clients: no provider registry set")
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            _log.exception("Failed to read LLM client configs from %s", path)
            return

        for name, cfg in raw.items():
            provider = cfg.get("provider", "")
            fields = cfg.get("fields", {})
            cls = self._provider_registry.get(provider)
            if cls is None:
                _log.warning("Unknown provider %r for client %r – skipped",
                             provider, name)
                continue
            try:
                client = cls(**fields)
                self._clients[name] = client
                self._configs[name] = cfg
            except Exception:
                _log.exception("Failed to reconstruct client %r", name)

        self._load_selected()
