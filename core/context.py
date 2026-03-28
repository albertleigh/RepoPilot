"""
Application context – lightweight dependency-injection container.

Create one ``AppContext`` at application start-up and pass it through
constructors so that every component shares the same service instances.
"""
from __future__ import annotations

import os
import platform
from pathlib import Path

from .events import EventBus
from .LLMClients.base import LLMClientRegistry, LLMProviderRegistry
from .engineer_manager.registry import EngineerManagerRegistry
from .mcp.registry import McpServerRegistry
from .project_manager.registry import ProjectManagerRegistry
from .repo_registry import RepoRegistry
from .skills.skill_registry import SkillRegistry


def _default_base_dir() -> Path:
    """Return the platform-appropriate application data directory."""
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "")
        root = Path(appdata) / "RepoPilot" if appdata else Path.home() / "AppData" / "Roaming" / "RepoPilot"
    else:
        root = Path.home() / ".repo_pilot"
    return root


class AppContext:
    """Holds shared service instances for the lifetime of the application."""

    def __init__(self, base_dir: Path | None = None) -> None:
        self.base_dir = base_dir or _default_base_dir()
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.event_bus = EventBus()

        self.llm_provider_registry = LLMProviderRegistry()
        self._register_default_providers()

        self.llm_client_registry = LLMClientRegistry(
            base_dir=self.base_dir,
            provider_registry=self.llm_provider_registry,
        )
        self.llm_client_registry.load()

        self.skill_registry = SkillRegistry(
            skills_dir=self.base_dir / "skills",
        )
        self.skill_registry.load()

        self.repo_registry = RepoRegistry(base_dir=self.base_dir)
        self.repo_registry.load()

        self.mcp_server_registry = McpServerRegistry(
            base_dir=self.base_dir,
            event_bus=self.event_bus,
        )
        self.mcp_server_registry.load()

        self.engineer_manager_registry = EngineerManagerRegistry(
            event_bus=self.event_bus,
            mcp_server_registry=self.mcp_server_registry,
            base_dir=self.base_dir,
        )

        self.project_manager_registry = ProjectManagerRegistry(
            engineer_registry=self.engineer_manager_registry,
            repo_registry=self.repo_registry,
            event_bus=self.event_bus,
            mcp_server_registry=self.mcp_server_registry,
            base_dir=self.base_dir,
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def shutdown(self) -> None:
        """Tear down long-lived resources (call before exit)."""
        self.project_manager_registry.shutdown()
        self.engineer_manager_registry.shutdown_all()
        self.mcp_server_registry.shutdown()
        self.event_bus.shutdown()

    # ------------------------------------------------------------------
    # Provider auto-registration
    # ------------------------------------------------------------------

    def _register_default_providers(self) -> None:
        """Import and register all built-in LLM provider classes."""
        from .LLMClients.claude_on_azure import ClaudeOnAzureClient
        from .LLMClients.gpt51_codex_max_on_azure import GPT51CodexMaxOnAzureClient
        from .LLMClients.gpt53_codex_on_azure import GPT53CodexOnAzureClient
        from .LLMClients.gpt5_codex_on_azure import GPT5CodexOnAzureClient
        from .LLMClients.gpt5_on_azure import GPT5OnAzureClient
        from .LLMClients.gpt54_pro_on_azure import GPT54ProOnAzureClient
        from .LLMClients.kimi_k2_thinking_on_azure import KimiK2ThinkingOnAzureClient

        self.llm_provider_registry.register(ClaudeOnAzureClient)
        self.llm_provider_registry.register(GPT51CodexMaxOnAzureClient)
        self.llm_provider_registry.register(GPT53CodexOnAzureClient)
        self.llm_provider_registry.register(GPT5CodexOnAzureClient)
        self.llm_provider_registry.register(GPT5OnAzureClient)
        self.llm_provider_registry.register(GPT54ProOnAzureClient)
        self.llm_provider_registry.register(KimiK2ThinkingOnAzureClient)
