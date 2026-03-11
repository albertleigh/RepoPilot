"""
Claude on Azure (Anthropic Foundry) LLM client implementation.

Uses the ``anthropic`` SDK pointed at an Azure AI Foundry endpoint.
"""
from __future__ import annotations

import anthropic

from .base import LLMClient, LLMResponse, ToolCall


class ClaudeOnAzureClient(LLMClient):
    """Adapter for Claude models hosted on Azure via Anthropic Foundry."""

    PROVIDER = "Claude on Azure"
    DEFAULT_MODEL = "claude-sonnet-4-5"
    MAX_TOKENS = 4096
    MAX_TOOLS = 256

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

    # -- Tool-use interface --

    def send_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        kwargs: dict = {
            "model": self._model_id,
            "max_tokens": self.MAX_TOKENS,
            "messages": messages,
            "tools": tools,
        }
        if system:
            kwargs["system"] = system
        response = self._client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=block.input)
                )

        return LLMResponse(
            text="\n".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=(
                "tool_use" if response.stop_reason == "tool_use" else "end_turn"
            ),
            assistant_message={"role": "assistant", "content": response.content},
        )

    def make_tool_results(self, results: list[dict]) -> list[dict]:
        return [
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": r["tool_use_id"],
                        "content": str(r["output"]),
                    }
                    for r in results
                ],
            }
        ]
