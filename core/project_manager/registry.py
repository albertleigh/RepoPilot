"""
Singleton-style registry for the :class:`ProjectManager`.

Unlike the engineer registry (one per repo), there is typically one
ProjectManager instance per application session.
"""
from __future__ import annotations

import logging

from pathlib import Path

from core.LLMClients.base import LLMClient
from core.events import EventBus
from core.engineer_manager.registry import EngineerManagerRegistry
from core.mcp.registry import McpServerRegistry
from core.repo_registry import RepoRegistry

from .manager import ProjectManager

_log = logging.getLogger(__name__)


class ProjectManagerRegistry:
    """Manages the singleton ProjectManager instance."""

    def __init__(
        self,
        engineer_registry: EngineerManagerRegistry,
        repo_registry: RepoRegistry,
        event_bus: EventBus | None = None,
        mcp_server_registry: McpServerRegistry | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self._eng_reg = engineer_registry
        self._repo_reg = repo_registry
        self._event_bus = event_bus
        self._mcp_server_registry = mcp_server_registry
        self._base_dir = base_dir
        self._instance: ProjectManager | None = None

    def create(
        self,
        llm_client: LLMClient,
        *,
        auto_start: bool = True,
    ) -> ProjectManager:
        """Create and optionally start the ProjectManager.

        If an old instance exists (running or stopped), it is shut down
        first so the new one starts fresh with the given *llm_client*.
        """
        if self._instance is not None:
            if self._instance.is_running:
                self._instance.shutdown()
            self._instance = None
        self._instance = ProjectManager(
            llm_client=llm_client,
            engineer_registry=self._eng_reg,
            repo_registry=self._repo_reg,
            event_bus=self._event_bus,
            mcp_server_registry=self._mcp_server_registry,
            base_dir=self._base_dir,
        )
        self._instance.load_messages()
        if auto_start:
            self._instance.start()
        _log.info("Created ProjectManager with LLM %s", type(llm_client).__name__)
        return self._instance

    def get(self) -> ProjectManager | None:
        return self._instance

    @property
    def is_running(self) -> bool:
        return self._instance is not None and self._instance.is_running

    def shutdown(self) -> None:
        if self._instance:
            self._instance.save_messages()
            self._instance.shutdown()
            self._instance = None
            _log.info("ProjectManager shut down")
