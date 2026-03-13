"""
Base tools – sandboxed file and shell operations scoped to a workdir.
"""
from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

# Commands that should never be run
_DANGEROUS = ["rm -rf /", "sudo", "shutdown", "reboot", "> /dev/"]

_IS_WINDOWS = sys.platform == "win32"


def safe_path(workdir: Path, p: str) -> Path:
    """Resolve *p* relative to *workdir* and reject escapes."""
    path = (workdir / p).resolve()
    if not path.is_relative_to(workdir.resolve()):
        raise ValueError(f"Path escapes workspace: {p}")
    return path


def run_bash(workdir: Path, command: str, timeout: int = 120) -> str:
    if any(d in command for d in _DANGEROUS):
        return "Error: Dangerous command blocked"
    _log.info("[BASH] Executing (timeout=%ds): %s", timeout, command[:200])
    try:
        if _IS_WINDOWS:
            # Force UTF-8 output so Chinese/emoji/non-ASCII render correctly,
            # then run the user's command.
            wrapped = (
                "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
                "$OutputEncoding = [System.Text.Encoding]::UTF8; "
                + command
            )
            args = ["powershell", "-NoProfile", "-Command", wrapped]
            r = subprocess.run(
                args, cwd=workdir,
                capture_output=True, text=True, timeout=timeout,
                encoding="utf-8", errors="replace",
            )
        else:
            r = subprocess.run(
                command, shell=True, cwd=workdir,
                capture_output=True, text=True, timeout=timeout,
            )
        out = (r.stdout + r.stderr).strip()
        _log.info("[BASH] Completed (rc=%d, output_len=%d): %.120s", r.returncode, len(out), out)
        return out[:50000] if out else "(no output)"
    except subprocess.TimeoutExpired:
        _log.warning("[BASH] Timeout after %ds: %s", timeout, command[:200])
        return f"Error: Timeout ({timeout}s)"


# Maximum characters returned in a single read_file call.
_READ_CHAR_LIMIT = 100_000
# Default window when the caller specifies no range.
_DEFAULT_LINE_WINDOW = 500


def run_read(
    workdir: Path,
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Read file with optional line-range support.

    Parameters
    ----------
    path:
        Relative path inside *workdir*.
    start_line:
        1-based inclusive start line.
    end_line:
        1-based inclusive end line.

    Returns a string with a metadata header and numbered lines, so the
    agent always knows total size and which range it is looking at.  If
    the file is too large for one response, the output includes a hint
    telling the agent to request the next range.
    """
    try:
        fp = safe_path(workdir, path)
        raw = fp.read_text(errors="replace")
        all_lines = raw.splitlines()
        total = len(all_lines)

        # Determine the slice to return
        if start_line is not None or end_line is not None:
            s = max(1, start_line or 1)
            e = min(total, end_line or total)
            selected = all_lines[s - 1 : e]
            range_start, range_end = s, s + len(selected) - 1
        else:
            # No range specified — return up to _DEFAULT_LINE_WINDOW lines
            if total > _DEFAULT_LINE_WINDOW:
                selected = all_lines[:_DEFAULT_LINE_WINDOW]
                range_start, range_end = 1, _DEFAULT_LINE_WINDOW
            else:
                selected = all_lines
                range_start, range_end = 1, total

        # Build numbered output
        width = len(str(range_end))
        numbered = []
        for i, line in enumerate(selected, start=range_start):
            numbered.append(f"{i:>{width}}│ {line}")
        body = "\n".join(numbered)

        # Truncate if body still exceeds char limit
        truncated = False
        if len(body) > _READ_CHAR_LIMIT:
            body = body[:_READ_CHAR_LIMIT]
            truncated = True

        # Metadata header
        header = f"[File: {path} | Lines: {range_start}-{range_end} of {total}]"

        # Continuation hint
        hint = ""
        if range_end < total:
            next_start = range_end + 1
            hint = (
                f"\n[Showing lines {range_start}-{range_end} of {total}. "
                f"Use read_file with start_line={next_start} to see more.]"
            )
        if truncated:
            hint += "\n[Output truncated due to size. Request a smaller line range.]"

        return f"{header}\n{body}{hint}"
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
