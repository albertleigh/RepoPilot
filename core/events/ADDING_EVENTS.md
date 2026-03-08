# Adding a New Event

This guide walks through the steps for adding a new event kind to the
`core/events` system.

---

## 1. Define the kind

Open `core/events/event_types.py` and add an entry to the `EventKind`
enum under the appropriate section comment:

```python
class EventKind(Enum):
    ...
    # -- My Feature ---------------------------------------------------
    MY_FEATURE_HAPPENED = auto()
```

## 2. Create the event dataclass

In the same file, add a frozen-kind dataclass below the relevant
section:

```python
@dataclass
class MyFeatureHappenedEvent(Event):
    """Emitted when my feature does its thing."""
    relevant_id: str = ""
    detail: str = ""
    kind: EventKind = field(default=EventKind.MY_FEATURE_HAPPENED, init=False)
```

> **Rules**
> - The `kind` field must have `init=False` and default to the matching
>   enum member so it is set automatically.
> - Keep payload fields simple (str, int, float, bool, list, dict).
>   Avoid putting live objects into events — they cross thread
>   boundaries.

## 3. Re-export from `__init__.py`

Open `core/events/__init__.py` and add the new class to both the
import block and the `__all__` list:

```python
from .event_types import (
    ...
    MyFeatureHappenedEvent,
)

__all__ = [
    ...
    "MyFeatureHappenedEvent",
]
```

## 4. Emit the event from a service

Anywhere you hold a reference to the `EventBus` (typically via
`AppContext.event_bus`):

```python
from core.events import MyFeatureHappenedEvent

self._event_bus.emit(MyFeatureHappenedEvent(
    relevant_id="abc",
    detail="something interesting",
))
```

## 5. Subscribe on the Qt side

In the client layer, use the `QtEventBridge`:

```python
from core.events import EventKind

# Option A – filter by kind with the convenience helper
self.bridge.on(EventKind.MY_FEATURE_HAPPENED, self._handle_my_feature)

# Option B – connect to the raw signal and filter manually
self.bridge.event_received.connect(self._on_any_event)
```

Slots connected via the bridge always run on the **Qt main thread**,
regardless of which thread emitted the event.

---

## Checklist

| # | Step | File |
|---|------|------|
| 1 | Add enum member | `core/events/event_types.py` |
| 2 | Add dataclass | `core/events/event_types.py` |
| 3 | Re-export | `core/events/__init__.py` |
| 4 | Emit from service | your service file |
| 5 | Subscribe in UI | your widget / bridge setup |
