"""
repo_tree – Git-aware repository tree widget package.

Re-exports :class:`RepoTree` so that existing imports
(``from .repo_tree import RepoTree``) keep working.
"""
from .widget import RepoTree

__all__ = ["RepoTree"]
