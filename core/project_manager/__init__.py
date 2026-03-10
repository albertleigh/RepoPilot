"""
Project Manager sub-package.

The ``ProjectManager`` is a high-level orchestration agent that
coordinates multiple ``EngineerManager`` instances across repositories.
It breaks down user requirements into per-repo tasks, dispatches them
to engineer agents, and verifies completion.
"""
from .manager import ProjectManager
from .registry import ProjectManagerRegistry

__all__ = ["ProjectManager", "ProjectManagerRegistry"]
