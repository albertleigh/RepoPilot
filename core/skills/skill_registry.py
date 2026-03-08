"""
Skill registry – folder-based management of AI skills.

Each skill lives in its own sub-folder under ``<base_dir>/skills/``.
A valid skill folder must contain a ``SKILL.md`` file with optional
YAML-style frontmatter (delimited by ``---``) followed by the body.

On ``load()`` the registry scans every immediate sub-directory for a
``SKILL.md``, parses it, and stores ``{"meta": dict, "body": str}``
in an in-memory dict keyed by skill name.

To **add** a skill the caller supplies the path to a ``SKILL.md``;
the registry copies the entire containing folder into ``skills_dir``.
"""
from __future__ import annotations

import logging
import re
import shutil
from pathlib import Path

_log = logging.getLogger(__name__)
_SKILL_FILE = "SKILL.md"


class SkillRegistry:
    """Folder-based registry for AI skills.

    Parameters
    ----------
    skills_dir:
        Root directory (e.g. ``<base_dir>/skills``) that contains one
        sub-folder per skill.
    """

    def __init__(self, skills_dir: Path) -> None:
        self._skills_dir = skills_dir
        # name → {"meta": {str: str}, "body": str, "path": Path}
        self._skills: dict[str, dict] = {}

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    @staticmethod
    def parse_skill_md(text: str) -> tuple[dict[str, str], str]:
        """Parse a ``SKILL.md`` and return ``(meta, body)``.

        *meta* is a flat ``{key: value}`` dict from the YAML-ish
        frontmatter.  Supports multi-line values (``|`` / ``>`` block
        scalars and plain indented continuation lines).
        *body* is everything after the closing ``---``.
        """
        meta: dict[str, str] = {}
        body = text
        match = re.match(r"^---\n(.*?)\n---\n(.*)", text, re.DOTALL)
        if match:
            raw_lines = match.group(1).splitlines()
            current_key: str | None = None
            current_lines: list[str] = []

            def _flush():
                if current_key is not None:
                    meta[current_key] = "\n".join(current_lines)

            for line in raw_lines:
                # A new key: starts at column 0 and contains ':'
                if line and not line[0].isspace() and ":" in line:
                    _flush()
                    k, v = line.split(":", 1)
                    current_key = k.strip()
                    v = v.strip()
                    # Drop YAML block-scalar indicators (| or >)
                    if v in ("|", ">", "|+", "|-", ">+", ">-"):
                        current_lines = []
                    else:
                        current_lines = [v]
                else:
                    # Continuation line – strip common leading indent
                    current_lines.append(line.strip())
            _flush()

            body = match.group(2).strip()
        return meta, body

    @staticmethod
    def validate_skill_md(path: Path) -> tuple[bool, str]:
        """Return ``(ok, reason)`` for a candidate ``SKILL.md``."""
        if not path.exists():
            return False, f"File does not exist: {path}"
        if path.name != _SKILL_FILE:
            return False, f"File must be named {_SKILL_FILE}"
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            return False, f"Cannot read file: {exc}"
        meta, _ = SkillRegistry.parse_skill_md(text)
        if not meta.get("name"):
            return False, "SKILL.md is missing a 'name' field in its frontmatter"
        return True, ""

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, skill_md_path: Path) -> tuple[bool, str]:
        """Validate *skill_md_path*, copy its parent folder into
        ``skills_dir/<name>/``, and load it into the in-memory dict.

        Returns ``(success, message)``.
        """
        ok, reason = self.validate_skill_md(skill_md_path)
        if not ok:
            return False, reason

        text = skill_md_path.read_text(encoding="utf-8")
        meta, body = self.parse_skill_md(text)
        name = meta["name"]

        dest = self._skills_dir / name
        if dest.exists():
            return False, f"Skill '{name}' already exists"

        src_folder = skill_md_path.parent
        try:
            self._skills_dir.mkdir(parents=True, exist_ok=True)
            shutil.copytree(str(src_folder), str(dest))
        except OSError as exc:
            return False, f"Failed to copy skill folder: {exc}"

        self._skills[name] = {
            "meta": meta,
            "body": body,
            "path": dest,
        }
        return True, name

    def unregister(self, name: str) -> None:
        """Remove a skill folder and its in-memory entry."""
        info = self._skills.pop(name, None)
        if info is None:
            return
        folder = info.get("path") or (self._skills_dir / name)
        if folder.exists():
            shutil.rmtree(folder, ignore_errors=True)

    def get(self, name: str) -> dict | None:
        """Return ``{"meta": …, "body": …, "path": …}`` or ``None``."""
        return self._skills.get(name)

    def all_skills(self) -> dict[str, dict]:
        """Shallow copy of every loaded skill."""
        return dict(self._skills)

    def names(self) -> list[str]:
        return list(self._skills.keys())

    def count(self) -> int:
        return len(self._skills)

    # ------------------------------------------------------------------
    # Loading (scan folders)
    # ------------------------------------------------------------------

    def load(self) -> None:
        """Scan ``skills_dir`` sub-folders and load every valid
        ``SKILL.md`` into memory."""
        self._skills.clear()
        if not self._skills_dir.exists():
            return
        for child in sorted(self._skills_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / _SKILL_FILE
            if not skill_file.exists():
                _log.debug("Skipping %s – no %s", child.name, _SKILL_FILE)
                continue
            try:
                text = skill_file.read_text(encoding="utf-8")
            except OSError:
                _log.exception("Cannot read %s", skill_file)
                continue
            meta, body = self.parse_skill_md(text)
            name = meta.get("name", child.name)
            self._skills[name] = {
                "meta": meta,
                "body": body,
                "path": child,
            }
