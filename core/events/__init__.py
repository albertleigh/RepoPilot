"""
core.events – typed, global event system.

Public API::

    from core.events import EventBus, EventKind, Event
    from core.events import LLMSelectedEvent, EngineerMessageEvent  # etc.
"""

from .event_bus import EventBus
from .event_types import (
    Event,
    EventKind,
    # Engineer
    EngineerErrorEvent,
    EngineerMessageEvent,
    EngineerProgressEvent,
    EngineerStartedEvent,
    EngineerStoppedEvent,
    EngineerToolCallEvent,
    EngineerToolResultEvent,
    # Todos
    TodoUpdatedEvent,
    # Tasks
    TaskCreatedEvent,
    TaskUpdatedEvent,
    # Teammates
    TeammateMessageEvent,
    TeammateSpawnedEvent,
    TeammateStoppedEvent,
    # Skills
    SkillRegisteredEvent,
    SkillUnregisteredEvent,
)

__all__ = [
    "EventBus",
    "Event",
    "EventKind",
    # Engineer
    "EngineerErrorEvent",
    "EngineerMessageEvent",
    "EngineerProgressEvent",
    "EngineerStartedEvent",
    "EngineerStoppedEvent",
    "EngineerToolCallEvent",
    "EngineerToolResultEvent",
    # Todos
    "TodoUpdatedEvent",
    # Tasks
    "TaskCreatedEvent",
    "TaskUpdatedEvent",
    # Teammates
    "TeammateMessageEvent",
    "TeammateSpawnedEvent",
    "TeammateStoppedEvent",
    # Skills
    "SkillRegisteredEvent",
    "SkillUnregisteredEvent",
]
