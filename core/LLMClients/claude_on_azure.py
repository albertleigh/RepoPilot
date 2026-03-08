"""
Claude on Azure (Anthropic Foundry) LLM client implementation.

Uses the ``anthropic`` SDK pointed at an Azure AI Foundry endpoint.
"""
from __future__ import annotations

import anthropic

from .base import LLMClient


class ClaudeOnAzureClient(LLMClient):
    """Adapter for Claude models hosted on Azure via Anthropic Foundry."""

    PROVIDER = "Claude on Azure"
    DEFAULT_MODEL = "claude-sonnet-4-5"
    MAX_TOKENS = 4096

    FIELDS = [
        {
            "key": "model_id",
            "label": "Model ID",
            "placeholder": "claude-sonnet-4-5",
            "default": "claude-sonnet-4-5",
            "required": True,
            "secret": False,
        },
        {
            "key": "api_key",
            "label": "Azure Anthropic Key",
            "placeholder": "<your-azure-anthropic-key>",
            "default": "",
            "required": True,
            "secret": True,
        },
        {
            "key": "base_url",
            "label": "Azure Anthropic Base URL",
            "placeholder": "https://<cluster-name>.services.ai.azure.com/anthropic",
            "default": "",
            "required": True,
            "secret": False,
        },
    ]

    def __init__(self, api_key: str, base_url: str,
                 model_id: str = DEFAULT_MODEL):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._model_id = model_id

        self._client = anthropic.Anthropic(
            api_key=self._api_key,
            base_url=self._base_url,
        )

    # -- LLMClient interface --

    def provider_name(self) -> str:
        return self.PROVIDER

    def model_id(self) -> str:
        return self._model_id

    def send_message(self, message: str,
                     history: list[dict] | None = None) -> str:
        messages = list(history) if history else []
        messages.append({"role": "user", "content": message})
        return self.send_messages(messages)

    def send_messages(self, messages: list[dict]) -> str:
        response = self._client.messages.create(
            model=self._model_id,
            max_tokens=self.MAX_TOKENS,
            messages=messages,
        )
        # Extract assistant text from the first content block
        for block in response.content:
            if block.type == "text":
                return block.text
        return ""

    def is_available(self) -> bool:
        try:
            self._client.messages.create(
                model=self._model_id,
                max_tokens=16,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
