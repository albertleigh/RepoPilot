"""
Typed event definitions for the application event bus.

Every event flowing through the ``EventBus`` **must** be one of the
dataclasses defined here so that both emitters and subscribers share a
single, well-known schema.  See ``ADDING_EVENTS.md`` for instructions
on adding new event kinds.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


# ------------------------------------------------------------------
# Event kind enumeration
# ------------------------------------------------------------------

class EventKind(Enum):
    """Exhaustive catalogue of all event kinds in the application."""

    # -- Engineer manager ----------------------------------------------
    ENGINEER_STARTED = auto()
    ENGINEER_STOPPED = auto()
    ENGINEER_MESSAGE = auto()
    ENGINEER_TOOL_CALL = auto()
    ENGINEER_TOOL_RESULT = auto()
    ENGINEER_ERROR = auto()

    # -- Todos ---------------------------------------------------------
    TODO_UPDATED = auto()

    # -- Tasks ---------------------------------------------------------
    TASK_CREATED = auto()
    TASK_UPDATED = auto()

    # -- Teammates -----------------------------------------------------
    TEAMMATE_SPAWNED = auto()
    TEAMMATE_STOPPED = auto()
    TEAMMATE_MESSAGE = auto()

    # -- Skills --------------------------------------------------------
    SKILL_REGISTERED = auto()
    SKILL_UNREGISTERED = auto()


# ------------------------------------------------------------------
# Base event
# ------------------------------------------------------------------

@dataclass
class Event:
    """Base class for every event.  All events carry at least a *kind*."""
    kind: EventKind


# ------------------------------------------------------------------
# Engineer manager events
# ------------------------------------------------------------------

@dataclass
class EngineerStartedEvent(Event):
    """Emitted when an engineer loop starts for a repository."""
    workdir: str = ""
    kind: EventKind = field(default=EventKind.ENGINEER_STARTED, init=False)


@dataclass
class EngineerStoppedEvent(Event):
    """Emitted when an engineer loop ends."""
    workdir: str = ""
    kind: EventKind = field(default=EventKind.ENGINEER_STOPPED, init=False)


@dataclass
class EngineerMessageEvent(Event):
    """Emitted when the engineer produces a text response."""
    workdir: str = ""
    text: str = ""
    kind: EventKind = field(default=EventKind.ENGINEER_MESSAGE, init=False)


@dataclass
class EngineerToolCallEvent(Event):
    """Emitted when the engineer invokes a tool."""
    workdir: str = ""
    tool_name: str = ""
    tool_input: dict = field(default_factory=dict)
    kind: EventKind = field(default=EventKind.ENGINEER_TOOL_CALL, init=False)


@dataclass
class EngineerToolResultEvent(Event):
    """Emitted when a tool execution completes."""
    workdir: str = ""
    tool_name: str = ""
    output: str = ""
    kind: EventKind = field(default=EventKind.ENGINEER_TOOL_RESULT, init=False)


@dataclass
class EngineerErrorEvent(Event):
    """Emitted when the engineer loop encounters an error."""
    workdir: str = ""
    error: str = ""
    kind: EventKind = field(default=EventKind.ENGINEER_ERROR, init=False)


# ------------------------------------------------------------------
# Todo events
# ------------------------------------------------------------------

@dataclass
class TodoUpdatedEvent(Event):
    """Emitted when the todo list changes."""
    workdir: str = ""
    items: list[dict] = field(default_factory=list)
    kind: EventKind = field(default=EventKind.TODO_UPDATED, init=False)


# ------------------------------------------------------------------
# Task events
# ------------------------------------------------------------------

@dataclass
class TaskCreatedEvent(Event):
    """Emitted when a new task is created."""
    workdir: str = ""
    task_id: str = ""
    title: str = ""
    kind: EventKind = field(default=EventKind.TASK_CREATED, init=False)


@dataclass
class TaskUpdatedEvent(Event):
    """Emitted when a task is updated."""
    workdir: str = ""
    task_id: str = ""
    status: str = ""
    kind: EventKind = field(default=EventKind.TASK_UPDATED, init=False)


# ------------------------------------------------------------------
# Teammate events
# ------------------------------------------------------------------

@dataclass
class TeammateSpawnedEvent(Event):
    """Emitted when a teammate thread is created."""
    workdir: str = ""
    teammate_id: str = ""
    kind: EventKind = field(default=EventKind.TEAMMATE_SPAWNED, init=False)


@dataclass
class TeammateStoppedEvent(Event):
    """Emitted when a teammate thread finishes."""
    workdir: str = ""
    teammate_id: str = ""
    kind: EventKind = field(default=EventKind.TEAMMATE_STOPPED, init=False)


@dataclass
class TeammateMessageEvent(Event):
    """Emitted when a teammate produces a text response."""
    workdir: str = ""
    teammate_id: str = ""
    text: str = ""
    kind: EventKind = field(default=EventKind.TEAMMATE_MESSAGE, init=False)


# ------------------------------------------------------------------
# Skill events
# ------------------------------------------------------------------

@dataclass
class SkillRegisteredEvent(Event):
    """Emitted when a skill is added."""
    name: str = ""
    kind: EventKind = field(default=EventKind.SKILL_REGISTERED, init=False)


@dataclass
class SkillUnregisteredEvent(Event):
    """Emitted when a skill is removed."""
    name: str = ""
    kind: EventKind = field(default=EventKind.SKILL_UNREGISTERED, init=False)
