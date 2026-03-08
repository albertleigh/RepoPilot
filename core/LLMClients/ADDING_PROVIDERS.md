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
from .base import LLMClient


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
```

> **Important:** The `key` values in `FIELDS` must match the `__init__`
> parameter names — the dialog passes them as keyword arguments.

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
