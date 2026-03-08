"""
Base tools – sandboxed file and shell operations scoped to a workdir.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

# Commands that should never be run
_DANGEROUS = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]


def safe_path(workdir: Path, p: str) -> Path:
    """Resolve *p* relative to *workdir* and reject escapes."""
    path = (workdir / p).resolve()
    if not path.is_relative_to(workdir.resolve()):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(workdir: Path, command: str, timeout: int = 120) -> str:
    if any(d in command for d in _DANGEROUS):
        return "Error: Dangerous command blocked"
    try:
        r = subprocess.run(
            command, shell=True, cwd=workdir,
            capture_output=True, text=True, timeout=timeout,
        )
        out = (r.stdout + r.stderr).strip()
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        return f"Error: Timeout ({timeout}s)"


def run_read(workdir: Path, path: str, limit: int | None = None) -> str:
    try:
        lines = safe_path(workdir, path).read_text().splitlines()
        if limit and limit < len(lines):
            lines = lines[:limit] + [f"... ({len(lines) - limit} more)"]
        return "\n".join(lines)[:50000]
    except Exception as e:
        return f"Error: {e}"


def run_write(workdir: Path, path: str, content: str) -> str:
    try:
        fp = safe_path(workdir, path)
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(content)
        return f"Wrote {len(content)} bytes to {path}"
    except Exception as e:
        return f"Error: {e}"


def run_edit(workdir: Path, path: str, old_text: str, new_text: str) -> str:
    try:
        fp = safe_path(workdir, path)
        c = fp.read_text()
        if old_text not in c:
            return f"Error: Text not found in {path}"
        fp.write_text(c.replace(old_text, new_text, 1))
        return f"Edited {path}"
    except Exception as e:
        return f"Error: {e}"
