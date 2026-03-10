"""Skill-folder synchronisation utilities."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

_log = logging.getLogger(__name__)


def sync_skills_to_repo(source_skills_dir: Path, repo_dir: Path) -> list[str]:
    """Copy missing skill sub-folders from *source_skills_dir* into
    ``<repo_dir>/skills/``.

    Only sub-folders that do **not** already exist under the target are
    copied.  Existing skill folders are never overwritten.

    Returns the list of skill folder names that were copied.
    """
    if not source_skills_dir.is_dir():
        return []

    target_skills_dir = repo_dir / "skills"
    copied: list[str] = []

    for child in sorted(source_skills_dir.iterdir()):
        if not child.is_dir():
            continue
        dest = target_skills_dir / child.name
        if dest.exists():
            _log.debug("Skill '%s' already present in %s, skipping", child.name, target_skills_dir)
            continue
        try:
            target_skills_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(child), str(dest))
            copied.append(child.name)
            _log.info("Copied skill '%s' → %s", child.name, dest)
        except OSError:
            _log.exception("Failed to copy skill '%s' to %s", child.name, dest)

    return copied
