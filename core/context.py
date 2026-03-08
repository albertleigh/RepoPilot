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
from .skills.skill_registry import SkillRegistry


def _default_base_dir() -> Path:
    """Return the platform-appropriate application data directory."""
    if platform.system() == "Windows":
        appdata = os.environ.get("APPDATA", "")
        root = Path(appdata) / "ManagerCode" if appdata else Path.home() / "AppData" / "Roaming" / "ManagerCode"
    else:
        root = Path.home() / ".manager_code"
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

        self.engineer_manager_registry = EngineerManagerRegistry()

    # ------------------------------------------------------------------
    # Provider auto-registration
    # ------------------------------------------------------------------

    def _register_default_providers(self) -> None:
        """Import and register all built-in LLM provider classes."""
        from .LLMClients.claude_on_azure import ClaudeOnAzureClient
        from .LLMClients.gpt5_codex_on_azure import GPT5CodexOnAzureClient
        from .LLMClients.gpt5_on_azure import GPT5OnAzureClient
        from .LLMClients.kimi_k2_thinking_on_azure import KimiK2ThinkingOnAzureClient

        self.llm_provider_registry.register(ClaudeOnAzureClient)
        self.llm_provider_registry.register(GPT5CodexOnAzureClient)
        self.llm_provider_registry.register(GPT5OnAzureClient)
        self.llm_provider_registry.register(KimiK2ThinkingOnAzureClient)
