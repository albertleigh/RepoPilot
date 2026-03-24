"""
Registry of :class:`EngineerManager` instances keyed by repo path.
"""
from __future__ import annotations

import logging
from pathlib import Path

from core.LLMClients.base import LLMClient
from core.events import EventBus
from core.mcp.registry import McpServerRegistry

from .manager import EngineerManager

_log = logging.getLogger(__name__)


class EngineerManagerRegistry:
    """Maps normalised repo paths to live :class:`EngineerManager` instances."""

    def __init__(self, event_bus: EventBus | None = None,
                 mcp_server_registry: McpServerRegistry | None = None,
                 base_dir: Path | None = None) -> None:
        self._managers: dict[str, EngineerManager] = {}
        self._event_bus = event_bus
        self._mcp_server_registry = mcp_server_registry
        self._base_dir = base_dir

    @staticmethod
    def _key(workdir: Path) -> str:
        return str(workdir.resolve())

    def create(
        self,
        workdir: Path,
        llm_client: LLMClient,
        *,
        skills_dir: Path | None = None,
        auto_start: bool = True,
    ) -> EngineerManager:
        """Create and optionally start a new manager for *workdir*.

        Raises ``ValueError`` if one already exists for that path.
        """
        key = self._key(workdir)
        if key in self._managers:
            raise ValueError(f"Manager already exists for {workdir}")
        mgr = EngineerManager(
            workdir, llm_client,
            skills_dir=skills_dir,
            event_bus=self._event_bus,
            mcp_server_registry=self._mcp_server_registry,
        )
        self._managers[key] = mgr
        if auto_start:
            mgr.start()
        if self._base_dir:
            mgr.load_messages(self._base_dir)
        _log.info("Created EngineerManager for %s", workdir)
        return mgr

    def get(self, workdir: Path) -> EngineerManager | None:
        return self._managers.get(self._key(workdir))

    def remove(self, workdir: Path) -> None:
        """Shut down and de-register the manager for *workdir*."""
        key = self._key(workdir)
        mgr = self._managers.pop(key, None)
        if mgr:
            if self._base_dir:
                mgr.save_messages(self._base_dir)
            mgr.shutdown()
            _log.info("Removed EngineerManager for %s", workdir)

    def all_managers(self) -> dict[str, EngineerManager]:
        return dict(self._managers)

    def names(self) -> list[str]:
        """Return human-friendly labels (last path component)."""
        return [Path(k).name for k in self._managers]

    def shutdown_all(self) -> None:
        """Stop every active manager."""
        for mgr in self._managers.values():
            if self._base_dir:
                mgr.save_messages(self._base_dir)
            mgr.shutdown()
        self._managers.clear()
