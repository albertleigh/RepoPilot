# RepoPilot — Copilot Instructions

## What This Project Is

RepoPilot is a native desktop app (PySide6 / Qt) that pairs autonomous AI coding agents with local git repositories. No backend server — `core/` is pure Python business logic imported directly by the Qt frontend.

## Project Layout

```
client/            # PySide6 Qt frontend (never imported by core/)
  main.py          # Entry point: python -m client.main
  ui/              # Widgets, dialogs, tabs, event bridge
core/              # Business logic — NO PySide6 imports allowed
  context.py       # AppContext — single DI container for all registries
  events/          # Thread-safe EventBus + typed Event dataclasses
  engineer_manager/# Autonomous per-repo coding agent (daemon thread)
  project_manager/ # Multi-repo orchestration agent (singleton)
  LLMClients/      # LLM provider adapters (Azure OpenAI, Claude, Kimi)
  mcp/             # MCP JSON-RPC client + server registry
  skills/          # SKILL.md registry & loader
  repo_registry.py # Name → repo-path persistence
scripts/           # PyInstaller build helpers
config.json        # (Unused) — real config lives in %APPDATA%/RepoPilot
```

## Key Architecture Rules

1. **One `AppContext`, passed everywhere.** Created in `main()`, holds all registries. No globals, no singletons, no service locators.
2. **`core/` must never import PySide6.** All Qt ↔ core communication goes through `EventBus` → `QtEventBridge`.
3. **Registries follow a common pattern:** in-memory dict + JSON file in `base_dir`. CRUD operations, `_save()` on every mutation, `load()` on startup.
4. **Agents run in daemon threads.** `EngineerManager` (one per repo) and `ProjectManager` (singleton) each own a thread with a tool-use loop, wake/cancel via `threading.Event`, messages via `Queue`.
5. **Events are typed dataclasses.** Each `EventKind` enum member maps to a dataclass with `kind` field auto-set. Emit with `event_bus.emit()` (sync) or `emit_async()` (async worker).
6. **Tab system is generic.** `BaseTab` → `BaseChatTab` → concrete tabs. `TabsManager` arranges `GridItemContainer`s in nested `QSplitter`s for VS Code-style split views.

## Running & Building

```bash
# Run
python -m client.main

# Dev mode (Ctrl+R hot reload, DEBUG console logging)
REPOPILOT_DEV=1 python -m client.main

# Build single executable
python scripts/build.py
```

**Python 3.11+** required. Dependencies: `PySide6`, `anthropic`, `openai`, `markdown`.

## How to Add Things

| Task | Guide |
|---|---|
| New LLM provider | See `core/LLMClients/ADDING_PROVIDERS.md` |
| New event kind | See `core/events/ADDING_EVENTS.md` |
| New tab type | See `client/ui/tabs_item/TABS.md` |
| New core service | See `core/ARCHITECTURE.md` |

## Conventions

- Emit events from `core/`, subscribe in `client/ui/` via `QtEventBridge.on()`.
- Dangerous shell commands are blocked in `base_tools.py` — respect the deny-list when adding new tools.
- All file paths from agents are validated with `safe_path()` to prevent workspace escapes.
- LLM provider dialogs are auto-generated from the `FIELDS` class attribute on each `LLMClient` subclass.
- Persist user data under `AppContext.base_dir` (`%APPDATA%/RepoPilot` on Windows, `~/.repo_pilot` elsewhere).
