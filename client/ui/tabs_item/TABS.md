# Tab Items — Developer Guide

Every widget displayed inside the `TabsManager` grid must extend
`BaseTab`.  This document describes the contract and the steps for
adding new tab types.

---

## BaseTab contract

| Member | Kind | Required | Description |
|---|---|---|---|
| `get_tab_title()` | method | **yes** | Return a short string for the tab‐bar label. |
| `tab_icon` | class attr | no | Emoji/icon prefix (e.g. `"\U0001F4AC"`). Defaults to `""`. |
| `tab_label()` | method | inherited | Returns `"{icon} {title}"`. Used by `TabsManager.add_tab()`. |
| `tab_close_requested` | Signal | inherited | Emitted when the tab wants to close itself. |

`BaseTab` inherits from `QWidget`, so all Qt lifecycle rules apply.

---

## Existing tab types

### WelcomeTab
Landing page shown on startup and when all tabs are closed.
No user input.

### ChatTab
Basic LLM chat conversation.  Signals:
- `message_sent(str)` — fired when the user submits a message.

### EngineerChatTab
Autonomous agent session bound to a git repository.

Constructor requires `event_bus: EventBus` and `workdir: str`.
On creation, the tab spins up its **own** `QtEventBridge`
(parented to `self`) and subscribes to the engineer event kinds it
needs.  Events are filtered by `workdir` so only messages for this
repo are rendered.  When the tab widget is destroyed the bridge
auto-unsubscribes from the bus — no manual cleanup needed.

Signals:
- `message_sent(str)` — fired when the user submits a message
  (caller wires this to `EngineerManager.send_message`).

---

## Adding a new tab type

1. **Create** `client/ui/tabs_item/my_tab.py`
   ```python
   from .base_tab import BaseTab

   class MyTab(BaseTab):
       tab_icon = "🔧"

       def __init__(self, ...):
           super().__init__(parent)
           ...

       def get_tab_title(self) -> str:
           return "My Tab"
   ```

2. **Export** from `client/ui/tabs_item/__init__.py`:
   ```python
   from .my_tab import MyTab
   ```

3. **Open** from whatever handler needs it (e.g. `MainWindow`):
   ```python
   from .tabs_item import MyTab

   tab = MyTab(...)
   self.chat_tabs.add_tab(tab)
   ```

4. **Find / focus** an existing instance:
   ```python
   tab = self.chat_tabs.find_tab(MyTab, lambda t: t.some_field == value)
   if tab:
       self.chat_tabs.focus_tab(tab)
   ```

`TabsManager` never imports or knows about concrete tab classes
(except `WelcomeTab` for the empty-state fallback).  All tab-specific
logic stays in the tab itself and in the code that creates it.

---

## TabsManager generic API

| Method | Description |
|---|---|
| `add_tab(tab)` | Insert a `BaseTab` into the active container. |
| `find_tab(type, predicate?)` | First open tab matching type + optional filter. |
| `focus_tab(tab)` | Bring an existing tab into focus. |
| `close_current_tab()` | Close whichever tab is active. |
| `get_current_tab()` | Return the active `BaseTab` or `None`. |
| `get_all_tabs(type?)` | List all open tabs, optionally filtered by type. |
