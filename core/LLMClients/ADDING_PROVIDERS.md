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

Some Azure models (e.g. GPT-5) work with the **Chat Completions API**
(`client.chat.completions.create` via `openai.AzureOpenAI`).
Other models only support the newer **Responses API**
(`client.responses.create`).  Two variants exist:

| Variant                         | SDK client            | Example models           | Reference implementation       |
|---------------------------------|-----------------------|--------------------------|--------------------------------|
| Responses via `OpenAI`          | `openai.OpenAI`       | GPT-5.4-Pro, GPT-5-Codex | `gpt54_pro_on_azure.py`        |
| Responses via `AzureOpenAI`     | `openai.AzureOpenAI`  | GPT-5.3-Codex            | `gpt53_codex_on_azure.py`      |

Use `openai.OpenAI` with `base_url="{endpoint}/openai/v1/"` when the
model's endpoint follows that path.  Use `openai.AzureOpenAI` with an
`api_version` when the endpoint requires
`/openai/responses?api-version=...`.

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

---

## Agentic SDK Providers (e.g. Copilot SDK)

Some providers ship an **agentic SDK** that manages its own tool-calling
loop internally (JSON-RPC to a CLI subprocess, built-in file/shell
tools, etc.).  These require a fundamentally different integration
pattern compared to simple REST-based API providers.

Reference implementation: `copilot_sdk.py` (GitHub Copilot SDK).

### How agentic SDKs differ

| Concern | REST API provider | Agentic SDK provider |
|---|---|---|
| Tool dispatch | RepoPilot's loop calls tools, feeds results back | SDK runs its own loop; returns final text |
| `send_with_tools` | Returns `tool_use` stop reason + `ToolCall` list | Always returns `end_turn` (SDK handles tools internally) |
| `make_tool_results` | Translates results to provider format | No-op (returns `[]`) |
| Lifecycle | Stateless HTTP calls | Long-lived subprocess with sessions |
| Concurrency | Naturally thread-safe (independent HTTP requests) | Must isolate state per calling thread |

### Challenge 1: Async ↔ sync bridge

RepoPilot's agent threads are synchronous (`threading.Thread`), but
agentic SDKs are typically async-only.  Bridge with a dedicated asyncio
event loop:

```python
def _run(self, coro, *, timeout=300):
    ctx = self._get_caller_ctx()
    self._ensure_loop(ctx)
    fut = asyncio.run_coroutine_threadsafe(coro, ctx.loop)
    return fut.result(timeout=timeout)
```

### Challenge 2: Per-caller isolation

A single `LLMClient` instance is shared across the Project Manager,
multiple Engineer Managers (one per repo), teammate threads, and
subagent threads.  If any mutable state (session, tool handlers,
event loop) is shared, callers will interfere with each other.

**Solution:** A `_CallerContext` dataclass keyed by `threading.get_ident()`.
Each caller thread gets its own fully isolated set of resources:

```python
@dataclass
class _CallerContext:
    loop: Any = None           # dedicated asyncio event loop
    loop_thread: Any = None    # thread running the event loop
    client: Any = None         # SDK client (own subprocess)
    session: Any = None        # active session
    tool_handlers: dict = ...  # registered tool dispatch map
    mcp_registry: Any = None   # MCP server registry
```

Key lessons learned during implementation:

1. **Separate event loops** — Sharing one asyncio event loop across
   multiple SDK client instances causes internal event routing to break
   (e.g. `session.idle` fires immediately with 0 messages collected).
   Each caller must get its own `asyncio.new_event_loop()`.

2. **Separate SDK client instances** — Sharing one SDK client (CLI
   subprocess) across multiple sessions causes the same event confusion.
   Each caller must get its own client with its own subprocess.

3. **Thread-safe registration** — `register_tool_handlers()` is called
   from the caller's own thread, so it must store handlers in the
   per-thread context, not in shared instance state.

### Challenge 3: Tool name conflicts

Agentic SDKs have their own built-in tools.  If any RepoPilot tool name
collides with a built-in, the SDK will error:

```
External tool "task" conflicts with a built-in tool of the same name.
```

**Solution:** Maintain a skip set of names to exclude when bridging
tools to the SDK.  Include:

- **SDK built-ins** that overlap (`bash`, `read_file`, `write_file`,
  `edit_file`)
- **Names that conflict** with SDK built-ins (`task`)
- **Internal control signals** that don't make sense inside the SDK
  agent (`compress`, `idle`)

The SDK `Tool` class may offer an `overrides_built_in_tool` parameter
if you intentionally want to override a built-in, but in most cases
skipping is safer.

### Challenge 4: Event collection

Agentic SDKs use event-driven communication instead of request/response.
You must subscribe to events and wait for a termination signal:

```python
def _on_event(event):
    etype = event.type.value
    if etype == "assistant.message":
        collected.append(event.data.content)
    elif etype == "session.idle":
        done.set()
    elif etype == "session.error":
        log_error(event.data.message)
        done.set()

unsub = session.on(_on_event)
await session.send(message)
await asyncio.wait_for(done.wait(), timeout=300)
```

Always handle `session.error` — tool conflicts and auth failures
surface here, not as exceptions from `session.send()`.

### Challenge 5: FIELDS extensions

The standard `FIELDS` system supports `"type": "text"` (default).
Agentic SDKs may need:

- `"type": "action"` — A button (e.g. "Login with GitHub") that calls
  `cls.on_field_action(key)` and shows the result in a message box.
- `"type": "choices"` — An editable combo-box populated by
  `cls.get_field_choices(key)` (e.g. dynamic model list from the SDK).

### Challenge 6: Resource cleanup

Override `close()` to tear down all per-caller resources.  This is
called by the registry when the client is replaced or unregistered:

```python
def close(self):
    with self._callers_lock:
        callers = list(self._callers.items())
        self._callers.clear()
    for tid, ctx in callers:
        # async cleanup on the caller's own event loop
        fut = asyncio.run_coroutine_threadsafe(
            self._cleanup_ctx(ctx), ctx.loop,
        )
        fut.result(timeout=10)
        ctx.loop.call_soon_threadsafe(ctx.loop.stop)
```

### Wiring tool handlers

For the SDK to invoke RepoPilot's custom tools (TodoWrite, MCP tools,
skills, etc.), each call site that uses `send_with_tools` must call
`register_tool_handlers()` beforehand.  This is done via duck-typing:

```python
# In the manager's _run_tool_loop:
_register = getattr(self._llm, "register_tool_handlers", None)
if callable(_register):
    _register(self._handlers, self._mcp)
```

This must be added in **every** place that calls `send_with_tools`:

- `EngineerManager._run_tool_loop` (main agent loop)
- `EngineerManager._run_subagent` (subagent loop)
- `TeammateManager._loop` (teammate loop)
- `ProjectManager._run_tool_loop` (PM loop)

For non-SDK providers, the `getattr` check is a no-op.
