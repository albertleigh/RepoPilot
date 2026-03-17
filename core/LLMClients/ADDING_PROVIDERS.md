# Adding New LLM Client Providers

This guide explains how to add support for a new LLM provider to RepoCode.

The creation dialog is **data-driven** — it reads the `FIELDS` list defined
on each `LLMClient` subclass to render the form automatically.  You never
need to touch the dialog code.

## Steps

### 1. Create a new client class in `core/LLMClients/`

Create a new file, e.g. `my_provider.py`, implementing `LLMClient`.
Define `PROVIDER` (human-readable name) and `FIELDS` (list of field
descriptors) as class-level attributes:

```python
from .base import LLMClient, LLMResponse, ToolCall


class MyProviderClient(LLMClient):

    PROVIDER = "My Provider"

    FIELDS = [
        {
            "key": "api_key",
            "label": "API Key",
            "placeholder": "<your-api-key>",
            "default": "",
            "required": True,
            "secret": True,        # renders as a password field
        },
        {
            "key": "base_url",
            "label": "Base URL",
            "placeholder": "https://api.myprovider.com/v1",
            "default": "",
            "required": True,
            "secret": False,
        },
        {
            "key": "model_id",
            "label": "Model ID",
            "placeholder": "default-model",
            "default": "default-model",
            "required": True,
            "secret": False,
        },
    ]

    def __init__(self, api_key: str, base_url: str, model_id: str = "default-model"):
        # Initialize your SDK client here
        ...

    def provider_name(self) -> str:
        return self.PROVIDER

    def model_id(self) -> str:
        return self._model_id

    def send_message(self, message: str, history: list[dict] | None = None) -> str:
        messages = list(history) if history else []
        messages.append({"role": "user", "content": message})
        return self.send_messages(messages)

    def send_messages(self, messages: list[dict]) -> str:
        # Call your provider's API and return the assistant text
        ...

    def is_available(self) -> bool:
        # Quick check that credentials and endpoint work
        ...

    def send_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        system: str = "",
    ) -> LLMResponse:
        # Call your provider with tool definitions.
        # Parse the response into an LLMResponse with:
        #   - text: any text content
        #   - tool_calls: list of ToolCall(id, name, input)
        #   - stop_reason: "tool_use" or "end_turn"
        #   - assistant_message: provider-native assistant dict
        #     to append to the conversation
        ...

    def make_tool_results(self, results: list[dict]) -> list[dict]:
        # Convert [{"tool_use_id": str, "output": str}, ...] into
        # provider-native message(s) to append to the conversation.
        #
        # Anthropic format: one user message with a list of tool_result parts
        # OpenAI format:    one {"role": "tool"} message per result
        ...
```

> **Important:** The `key` values in `FIELDS` must match the `__init__`
> parameter names — the dialog passes them as keyword arguments.

#### Tool-use contract

The `send_with_tools` / `make_tool_results` pair enables the
`EngineerManager` agent loop to perform multi-step tool calling with
any provider.  The tool definitions use the **Anthropic schema shape**
(`{name, description, input_schema}`) as the canonical format.  If your
provider uses a different wire format (e.g. OpenAI function-calling),
translate inside `send_with_tools` — see `GPT5OnAzureClient._convert_tools`
for an example.

Return values:

| Field               | Type              | Description |
|---------------------|-------------------|-------------|
| `text`              | `str`             | Assistant's text output (may be empty during tool calls) |
| `tool_calls`        | `list[ToolCall]`  | Zero or more `ToolCall(id, name, input)` objects |
| `stop_reason`       | `str`             | `"tool_use"` if the model wants tools executed, otherwise `"end_turn"` |
| `assistant_message` | `dict`            | Provider-native message dict to append to history as-is |

#### Chat Completions vs Responses API

Some Azure models (e.g. GPT-5, GPT-5-Codex) work with the **Chat
Completions API** (`client.chat.completions.create` via `openai.AzureOpenAI`).
Other models (e.g. GPT-5.4-Pro) only support the newer **Responses API**
(`client.responses.create` via `openai.OpenAI` with a `base_url`).

The agent loop always builds a `messages` list in Chat-Completions
format.  If your model requires the Responses API you must:

1. **Use `openai.OpenAI`** with `base_url="{azure_endpoint}/openai/v1/"`
   instead of `openai.AzureOpenAI`.
2. **Translate messages → Responses API input** before each call.
   The mapping is:

   | Chat Completions message              | Responses API input item                  |
   |---------------------------------------|-------------------------------------------|
   | `{"role": "system", …}`               | `{"role": "developer", …}`                |
   | `{"role": "user", …}`                 | `{"role": "user", …}`                     |
   | `{"role": "assistant", "content": …}`  | `{"role": "assistant", "content": …}`      |
   | `{"role": "assistant", "tool_calls": [{"id", "function": {"name", "arguments"}}]}` | `{"type": "function_call", "call_id", "name", "arguments"}` (one per call) |
   | `{"role": "tool", "tool_call_id", "content"}` | `{"type": "function_call_output", "call_id", "output"}` |

3. **Translate Responses API output → `LLMResponse`** with an
   `assistant_message` in Chat-Completions format so the agent loop
   can append it to its messages list as usual.
4. **Translate tool definitions** to the flat Responses format:
   `{"type": "function", "name": …, "parameters": …}` (not nested
   under a `"function"` key).

See `GPT54ProOnAzureClient` in `gpt54_pro_on_azure.py` for a complete
working example with the `_msgs_to_input()` translator.

### 2. Register it in `AppContext`

In `core/context.py`, import your class in `register_default_providers()`
and register it:

```python
def register_default_providers(self) -> None:
    from .LLMClients.my_provider import MyProviderClient
    ...
    self.llm_provider_registry.register(MyProviderClient)
```

Also add the import to `core/LLMClients/__init__.py` for convenience:

```python
from .my_provider import MyProviderClient
```

That's it — the dialog will automatically discover the new provider,
show its fields, and construct instances via `cls(**kwargs)`.

### 3. Add dependencies

Add any required Python packages to `requirements-client.txt`.

That's it! The new provider will appear in the dropdown automatically.
