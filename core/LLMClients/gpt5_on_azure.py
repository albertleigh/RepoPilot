"""
GPT-5 on Azure OpenAI LLM client implementation.

Uses the ``openai`` SDK's ``AzureOpenAI`` client pointed at an
Azure OpenAI endpoint.
"""
from __future__ import annotations

import openai

from .base import LLMClient


class GPT5OnAzureClient(LLMClient):
    """Adapter for GPT-5 models hosted on Azure OpenAI."""

    PROVIDER = "GPT-5 on Azure"
    DEFAULT_MODEL = "al-gpt-5"
    DEFAULT_API_VERSION = "2024-12-01-preview"
    MAX_TOKENS = 16384

    FIELDS = [
        {
            "key": "model_id",
            "label": "Deployment Name",
            "placeholder": "gpt-5",
            "default": "gpt-5",
            "required": True,
            "secret": False,
        },
        {
            "key": "api_key",
            "label": "Azure OpenAI Key",
            "placeholder": "<your-azure-openai-key>",
            "default": "",
            "required": True,
            "secret": True,
        },
        {
            "key": "azure_endpoint",
            "label": "Azure Endpoint",
            "placeholder": "https://<resource>.cognitiveservices.azure.com/",
            "default": "",
            "required": True,
            "secret": False,
        },
        {
            "key": "api_version",
            "label": "API Version",
            "placeholder": "2024-12-01-preview",
            "default": "2024-12-01-preview",
            "required": True,
            "secret": False,
        },
    ]

    def __init__(self, api_key: str, azure_endpoint: str,
                 model_id: str = DEFAULT_MODEL,
                 api_version: str = DEFAULT_API_VERSION):
        self._api_key = api_key
        self._azure_endpoint = azure_endpoint.rstrip("/")
        self._model_id = model_id
        self._api_version = api_version

        self._client = openai.AzureOpenAI(
            api_key=self._api_key,
            azure_endpoint=self._azure_endpoint,
            api_version=self._api_version,
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
            max_completion_tokens=self.MAX_TOKENS,
            messages=messages,
        )
        choice = response.choices[0]
        return choice.message.content or ""

    def is_available(self) -> bool:
        try:
            self._client.chat.completions.create(
                model=self._model_id,
                max_completion_tokens=16,
                messages=[{"role": "user", "content": "ping"}],
            )
            return True
        except Exception:
            return False
