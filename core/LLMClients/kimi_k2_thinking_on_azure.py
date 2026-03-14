"""
Kimi-K2-Thinking on Azure OpenAI LLM client implementation.

Uses the ``openai`` SDK pointed at an Azure AI Services endpoint.
"""
from __future__ import annotations

import json

import openai

from .base import LLMClient, LLMResponse, ToolCall


class KimiK2ThinkingOnAzureClient(LLMClient):
    """Adapter for Kimi-K2-Thinking models hosted on Azure."""

    PROVIDER = "Kimi-K2-Thinking on Azure"
    DEFAULT_MODEL = "Kimi-K2-Thinking"
    MAX_TOKENS = 4096
    MAX_TOOLS = 256

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
        response = self._call_with_retry(
            self._client.chat.completions.create,
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

    # -- Tool-use interface --

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Translate Anthropic-style tool defs to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get(
                        "input_schema",
                        {"type": "object", "properties": {}},
                    ),
                },
            }
            for t in tools
        ]

    def send_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        oai_tools = self._convert_tools(tools)
        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        response = self._call_with_retry(
            self._client.chat.completions.create,
            model=self._model_id,
            max_tokens=self.MAX_TOKENS,
            messages=msgs,
            tools=oai_tools,
        )
        choice = response.choices[0]

        tool_calls: list[ToolCall] = []
        assistant_msg: dict = {
            "role": "assistant",
            "content": choice.message.content,
        }

        if choice.message.tool_calls:
            raw_tool_calls = []
            for tc in choice.message.tool_calls:
                tool_calls.append(
                    ToolCall(
                        id=tc.id,
                        name=tc.function.name,
                        input=json.loads(tc.function.arguments),
                    )
                )
                raw_tool_calls.append(
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                )
            assistant_msg["tool_calls"] = raw_tool_calls

        return LLMResponse(
            text=choice.message.content or "",
            tool_calls=tool_calls,
            stop_reason=(
                "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"
            ),
            assistant_message=assistant_msg,
        )

    def make_tool_results(self, results: list[dict]) -> list[dict]:
        return [
            {
                "role": "tool",
                "tool_call_id": r["tool_use_id"],
                "content": str(r["output"]),
            }
            for r in results
        ]
