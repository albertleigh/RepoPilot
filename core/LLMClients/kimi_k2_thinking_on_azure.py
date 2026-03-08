"""
Kimi-K2-Thinking on Azure OpenAI LLM client implementation.

Uses the ``openai`` SDK pointed at an Azure AI Services endpoint.
"""
from __future__ import annotations

import openai

from .base import LLMClient


class KimiK2ThinkingOnAzureClient(LLMClient):
    """Adapter for Kimi-K2-Thinking models hosted on Azure."""

    PROVIDER = "Kimi-K2-Thinking on Azure"
    DEFAULT_MODEL = "Kimi-K2-Thinking"
    MAX_TOKENS = 4096

    FIELDS = [
        {
            "key": "model_id",
            "label": "Deployment Name",
            "placeholder": "Kimi-K2-Thinking",
            "default": "Kimi-K2-Thinking",
            "required": True,
            "secret": False,
        },
        {
            "key": "api_key",
            "label": "Azure API Key",
            "placeholder": "<your-azure-api-key>",
            "default": "",
            "required": True,
            "secret": True,
        },
        {
            "key": "base_url",
            "label": "Azure Endpoint",
            "placeholder": "https://<resource>.services.ai.azure.com/openai/v1/",
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

        self._client = openai.OpenAI(
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
        response = self._client.chat.completions.create(
            model=self._model_id,
            max_tokens=self.MAX_TOKENS,
            messages=messages,
        )
        choice = response.choices[0]
        return choice.message.content or ""

    def is_available(self) -> bool:
        try:
            self._client.chat.completions.create(
                model=self._model_id,
                max_tokens=16,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
