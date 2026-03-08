"""
Skill loader – reads SKILL.md files from a skills directory.

Re-uses the robust parser from :mod:`core.skills.skill_registry`.
"""
from __future__ import annotations

from pathlib import Path

from core.skills.skill_registry import SkillRegistry


class SkillLoader:
    """Loads skills from ``<workdir>/skills/`` into memory."""

    def __init__(self, skills_dir: Path) -> None:
        self._skills: dict[str, dict] = {}
        if not skills_dir.exists():
            return
        for f in sorted(skills_dir.rglob("SKILL.md")):
            text = f.read_text(encoding="utf-8")
            meta, body = SkillRegistry.parse_skill_md(text)
            name = meta.get("name", f.parent.name)
            self._skills[name] = {"meta": meta, "body": body}

    def descriptions(self) -> str:
        if not self._skills:
            return "(no skills)"
        return "\n".join(
            f"  - {n}: {s['meta'].get('description', '-')}"
            for n, s in self._skills.items()
        )

    def load(self, name: str) -> str:
        s = self._skills.get(name)
        if not s:
            return (f"Error: Unknown skill '{name}'. "
                    f"Available: {', '.join(self._skills.keys())}")
        return f"<skill name=\"{name}\">\n{s['body']}\n</skill>"
