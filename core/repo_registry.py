"""
Repository registry – JSON-persisted mapping of display names to git root paths.

Mirrors the pattern used by :class:`LLMClientRegistry`: a flat JSON file
keeps ``{name: path}`` pairs so repositories survive across restarts.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

_log = logging.getLogger(__name__)

_REPOS_FILE = "repos.json"


class RepoRegistry:
    """Persistent repository name → git-root-path mapping.

    Parameters
    ----------
    base_dir:
        Application data directory.  The registry stores ``repos.json`` there.
    """

    def __init__(self, base_dir: Path | None = None) -> None:
        self._repos: dict[str, str] = {}  # display name → absolute path
        self._base_dir = base_dir

    @property
    def _json_path(self) -> Path | None:
        if self._base_dir is None:
            return None
        return self._base_dir / _REPOS_FILE

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, name: str, path: str) -> None:
        """Add or overwrite a repository entry."""
        self._repos[name] = str(Path(path).resolve())
        self._save()

    def unregister(self, name: str) -> None:
        self._repos.pop(name, None)
        self._save()

    def get(self, name: str) -> str | None:
        """Return the git root path for *name*, or ``None``."""
        return self._repos.get(name)

    def all_repos(self) -> dict[str, str]:
        """Return a copy of ``{name: path}``."""
        return dict(self._repos)

    def names(self) -> list[str]:
        return list(self._repos.keys())

    def contains(self, name: str) -> bool:
        return name in self._repos

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        path = self._json_path
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(self._repos, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except OSError:
            _log.exception("Failed to save repos to %s", path)

    def load(self) -> None:
        """Load persisted repo entries from disk."""
        path = self._json_path
        if path is None or not path.exists():
            return
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                self._repos = {k: str(v) for k, v in raw.items()}
        except (OSError, json.JSONDecodeError):
            _log.exception("Failed to read repos from %s", path)
