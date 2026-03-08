"""
Abstract base class for LLM clients and a registry to manage them.
"""
from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class LLMClient(ABC):
    """Abstract base for all LLM client implementations.

    Every provider adapter must implement these methods so that the rest
    of the application can treat all providers uniformly.

    Subclasses must also define two class-level attributes:

    - ``PROVIDER``  – human-readable provider label (str)
    - ``FIELDS``    – list of field descriptors used by the creation
      dialog to render a data-driven form.  Each entry is a dict::

          {
              "key":         str,   # kwarg name passed to __init__
              "label":       str,   # UI label
              "placeholder": str,   # placeholder text
              "default":     str,   # pre-filled value ("" if empty)
              "required":    bool,
              "secret":      bool,  # True → password echo mode
          }
    """

    PROVIDER: str = ""
    FIELDS: list[dict] = []

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
        self._base_dir = base_dir
        self._provider_registry = provider_registry

    @property
    def _json_path(self) -> Path | None:
        if self._base_dir is None:
            return None
        return self._base_dir / _LLM_CLIENTS_FILE

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
        self._save()

    def update(self, name: str, client: LLMClient,
               config: dict | None = None) -> None:
        """Replace an existing client's instance and config in-place."""
        self._clients[name] = client
        if config is not None:
            self._configs[name] = config
        self._save()

    def unregister(self, name: str) -> None:
        self._clients.pop(name, None)
        self._configs.pop(name, None)
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
