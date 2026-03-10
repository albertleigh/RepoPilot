"""
Event dataclasses specific to the ProjectManager agent.

These follow the same pattern as the engineer events in
``core.events.event_types`` but are scoped to PM operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from core.events.event_types import Event, EventKind


# ------------------------------------------------------------------
# PM event dataclasses
# ------------------------------------------------------------------

@dataclass
class PMStartedEvent(Event):
    """Emitted when the PM agent loop begins processing."""
    kind: EventKind = field(default=EventKind.PM_STARTED, init=False)


@dataclass
class PMStoppedEvent(Event):
    """Emitted when the PM agent loop finishes processing."""
    kind: EventKind = field(default=EventKind.PM_STOPPED, init=False)


@dataclass
class PMMessageEvent(Event):
    """Emitted when the PM produces a text response."""
    text: str = ""
    kind: EventKind = field(default=EventKind.PM_MESSAGE, init=False)


@dataclass
class PMToolCallEvent(Event):
    """Emitted when the PM invokes a tool."""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    kind: EventKind = field(default=EventKind.PM_TOOL_CALL, init=False)


@dataclass
class PMToolResultEvent(Event):
    """Emitted when a PM tool execution completes."""
    tool_name: str = ""
    output: str = ""
    kind: EventKind = field(default=EventKind.PM_TOOL_RESULT, init=False)


@dataclass
class PMErrorEvent(Event):
    """Emitted on PM agent error."""
    error: str = ""
    kind: EventKind = field(default=EventKind.PM_ERROR, init=False)


@dataclass
class PMProgressEvent(Event):
    """Progress indicator for the PM loop."""
    phase: str = ""
    detail: str = ""
    kind: EventKind = field(default=EventKind.PM_PROGRESS, init=False)


@dataclass
class PMTaskDispatchedEvent(Event):
    """Emitted when the PM dispatches a task to an engineer."""
    repo: str = ""
    dispatch_id: str = ""
    prompt: str = ""
    kind: EventKind = field(default=EventKind.PM_TASK_DISPATCHED, init=False)


@dataclass
class PMTaskVerifiedEvent(Event):
    """Emitted when the PM initiates verification of a task."""
    repo: str = ""
    criteria: str = ""
    kind: EventKind = field(default=EventKind.PM_TASK_VERIFIED, init=False)
