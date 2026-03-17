# Core Architecture – AppContext & Dependency Injection

## Overview

All shared services live under `core/` and are wired together through a
single **`AppContext`** instance created at application start-up.  
UI components never instantiate or look up services themselves — they receive
the context (or the specific service they need) via their constructor.

## How it works

```
main.py
  ├─ creates  AppContext          ← single source of truth
  ├─ calls    ctx.register_default_providers()
  └─ passes   ctx  →  MainWindow
                         └─ passes ctx  →  CreateLLMDialog, …
```

1. **`AppContext`** (`core/context.py`) owns every service instance.
2. **`main.py`** builds the context once and hands it to the root UI widget.
3. Each widget stores only the reference(s) it needs and never calls a global
   singleton or service locator.

## Adding a new service

### 1. Create the service class

Put it in a module under `core/`, e.g. `core/my_service.py`:

```python
class MyService:
    def __init__(self):
        self._state = {}

    def do_something(self) -> str:
        ...
```

### 2. Register it on `AppContext`

In `core/context.py`, import and instantiate it:

```python
from .my_service import MyService

class AppContext:
    def __init__(self) -> None:
        ...
        self.my_service = MyService()
```

### 3. Consume it in UI code

Accept `AppContext` (or just the service) in the constructor:

```python
class MyWidget(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self._my_service = ctx.my_service
```

### 4. (Optional) Bootstrap step

If the service requires one-time setup (loading config, registering
defaults, etc.), add a method on `AppContext` and call it from `main.py`:

```python
# core/context.py
def setup_my_service(self) -> None:
    self.my_service.load_defaults()

# client/main.py
ctx = AppContext()
ctx.register_default_providers()
ctx.setup_my_service()
```

## Rules to follow

| Do                                          | Don't                                        |
|---------------------------------------------|----------------------------------------------|
| Pass `ctx` through constructors             | Call `SomeRegistry.instance()` or use globals |
| Instantiate services inside `AppContext`     | Create services at module-import time         |
| Keep service classes free of Qt dependencies | Import `PySide6` inside `core/`               |
| Add new services to `AppContext.__init__`    | Scatter singletons across packages            |

## LLM provider adapters

All LLM adapters live in `core/LLMClients/` and implement the
`LLMClient` abstract base class.  Two families of OpenAI-compatible
APIs exist on Azure; choose the right one for your model:

| API Style            | SDK client          | Models                    | Reference implementation        |
|----------------------|---------------------|---------------------------|---------------------------------|
| Chat Completions     | `openai.AzureOpenAI`| GPT-5, GPT-5-Codex, Kimi | `gpt5_on_azure.py`              |
| Responses API        | `openai.OpenAI`     | GPT-5.4-Pro               | `gpt54_pro_on_azure.py`         |

The **Responses API** uses a different wire format.  Adapters that need
it must translate the agent loop's Chat-Completions-shaped `messages`
list into Responses input items and back.  See
`GPT54ProOnAzureClient._msgs_to_input()` for the canonical translator.

Full guide: `core/LLMClients/ADDING_PROVIDERS.md`.

## Current services

| Attribute                    | Type                       | Purpose                                      |
|------------------------------|----------------------------|----------------------------------------------|
| `llm_provider_registry`     | `LLMProviderRegistry`      | Maps provider names → LLMClient subclasses   |
| `llm_client_registry`       | `LLMClientRegistry`        | Tracks live LLM client instances by name     |
| `skill_registry`            | `SkillRegistry`            | Folder-based skill store (`<base_dir>/skills/`) |
| `engineer_manager_registry` | `EngineerManagerRegistry`  | Maps repo paths → live EngineerManager instances |
