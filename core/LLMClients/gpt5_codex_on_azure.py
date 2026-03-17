"""
GPT-5-Codex on Azure OpenAI LLM client implementation.

Uses the OpenAI **Responses API** (``client.responses.create``) because
Azure's Chat Completions endpoint does not support this model.  The
``openai.OpenAI`` client is pointed at the ``/openai/v1/`` path of an
Azure Cognitive Services endpoint.

Internally the agent loop speaks the Chat-Completions message format
(``{"role": "assistant", …}``).  This adapter translates back and forth
so the rest of the application doesn't need to know about the Responses
API wire format.
"""
from __future__ import annotations

import json
import logging

import openai

from .base import LLMClient, LLMResponse, ToolCall

_log = logging.getLogger(__name__)


class GPT5CodexOnAzureClient(LLMClient):
    """Adapter for GPT-5-Codex on Azure via the Responses API."""

    PROVIDER = "GPT-5-Codex on Azure"
    DEFAULT_MODEL = "gpt-5-codex"
    MAX_TOKENS = 16384
    MAX_TOOLS = 128

    FIELDS = [
        {
            "key": "model_id",
            "label": "Deployment Name",
            "placeholder": "gpt-5-codex",
            "default": "gpt-5-codex",
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
    ]

    def __init__(self, api_key: str, azure_endpoint: str,
                 model_id: str = DEFAULT_MODEL):
        self._api_key = api_key
        self._azure_endpoint = azure_endpoint.rstrip("/")
        self._model_id = model_id

        base_url = f"{self._azure_endpoint}/openai/v1/"
        self._client = openai.OpenAI(
            base_url=base_url,
            api_key=self._api_key,
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
        resp_input = self._msgs_to_input(messages)
        response = self._call_with_retry(
            self._client.responses.create,
            model=self._model_id,
            max_output_tokens=self.MAX_TOKENS,
            input=resp_input,
        )
        return response.output_text or ""

    def is_available(self) -> bool:
        base_url = self._client.base_url
        _log.info(
            "Testing GPT-5-Codex connection (base_url=%s, deployment=%s)",
            base_url, self._model_id,
        )
        try:
            self._client.responses.create(
                model=self._model_id,
                max_output_tokens=64,
                input="ping",
            )
            return True
        except Exception:
            _log.exception(
                "GPT-5-Codex connection test failed "
                "(base_url=%s, deployment=%s)",
                base_url,
                self._model_id,
            )
            return False

    # -- Tool-use interface --

    @staticmethod
    def _convert_tools(tools: list[dict]) -> list[dict]:
        """Translate Anthropic-style tool defs to Responses API format."""
        return [
            {
                "type": "function",
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get(
                    "input_schema",
                    {"type": "object", "properties": {}},
                ),
            }
            for t in tools
        ]

    # ------------------------------------------------------------------
    # Conversation format translation
    # ------------------------------------------------------------------

    @staticmethod
    def _msgs_to_input(messages: list[dict]) -> list[dict]:
        """Convert Chat-Completions messages to Responses API input items."""
        items: list[dict] = []
        for msg in messages:
            role = msg.get("role", "")

            if role == "system":
                items.append({
                    "role": "developer",
                    "content": msg["content"],
                })
            elif role == "user":
                items.append({
                    "role": "user",
                    "content": msg["content"],
                })
            elif role == "assistant":
                if msg.get("content"):
                    items.append({
                        "role": "assistant",
                        "content": msg["content"],
                    })
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    items.append({
                        "type": "function_call",
                        "name": fn.get("name", ""),
                        "arguments": fn.get("arguments", "{}"),
                        "call_id": tc.get("id", ""),
                    })
            elif role == "tool":
                items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": str(msg.get("content", "")),
                })
        return items

    def send_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        resp_tools = self._convert_tools(tools)
        msgs = list(messages)
        if system:
            msgs.insert(0, {"role": "system", "content": system})

        resp_input = self._msgs_to_input(msgs)

        response = self._call_with_retry(
            self._client.responses.create,
            model=self._model_id,
            max_output_tokens=self.MAX_TOKENS,
            input=resp_input,
            tools=resp_tools,
        )

        # Parse response output items
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        raw_tool_calls: list[dict] = []

        for item in response.output:
            if item.type == "message":
                for part in item.content:
                    if hasattr(part, "text"):
                        text_parts.append(part.text)
            elif item.type == "function_call":
                tool_calls.append(
                    ToolCall(
                        id=item.call_id,
                        name=item.name,
                        input=json.loads(item.arguments),
                    )
                )
                raw_tool_calls.append({
                    "id": item.call_id,
                    "type": "function",
                    "function": {
                        "name": item.name,
                        "arguments": item.arguments,
                    },
                })

        text = "\n".join(text_parts)
        has_tool_calls = len(tool_calls) > 0

        assistant_msg: dict = {
            "role": "assistant",
            "content": text or None,
        }
        if raw_tool_calls:
            assistant_msg["tool_calls"] = raw_tool_calls

        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason="tool_use" if has_tool_calls else "end_turn",
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
