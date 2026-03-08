"""
Engineer Manager sub-package.

Each ``EngineerManager`` is an autonomous agent loop bound to a
specific git repository.  It owns its own sub-services (todo, tasks,
skills, messaging, background, teammates) and runs in a dedicated
daemon thread, receiving user messages through a thread-safe queue.
"""
from .manager import EngineerManager
from .registry import EngineerManagerRegistry

__all__ = ["EngineerManager", "EngineerManagerRegistry"]
