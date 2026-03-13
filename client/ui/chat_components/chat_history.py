"""Persistent chat-history store with windowed access.

Keeps a short conversation entirely in memory.  Once the number of
recorded entries exceeds a configurable threshold the history is flushed
to a JSONL file on disk and further access goes through a sliding
window that loads only a slice of the file at a time.

Each history file lives at ``<base_dir>/chat_history/<session_id>.jsonl``.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Sequence

# -- tunables --
MEMORY_LIMIT = 200     # max entries kept purely in-memory
WINDOW_SIZE = 80       # how many entries to materialise at once
LOAD_MORE_SIZE = 40    # how many older entries to prepend on scroll-up


class ChatHistoryEntry:
    """A single serialisable chat-feed item."""

    __slots__ = ("kind", "role", "text", "extra", "timestamp")

    def __init__(
        self,
        kind: str,
        *,
        role: str = "",
        text: str = "",
        extra: dict | None = None,
        timestamp: str = "",
    ) -> None:
        self.kind = kind          # "message" | "tool_call" | "tool_result" | "status" | "error"
        self.role = role          # "user" | "assistant" (for messages)
        self.text = text
        self.extra = extra or {}  # tool_name, sender, avatar, …
        self.timestamp = timestamp or datetime.now().isoformat()

    # -- serialisation -------------------------------------------------

    def to_dict(self) -> dict:
        d: dict = {"kind": self.kind, "timestamp": self.timestamp}
        if self.role:
            d["role"] = self.role
        if self.text:
            d["text"] = self.text
        if self.extra:
            d["extra"] = self.extra
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "ChatHistoryEntry":
        return cls(
            kind=d["kind"],
            role=d.get("role", ""),
            text=d.get("text", ""),
            extra=d.get("extra"),
            timestamp=d.get("timestamp", ""),
        )


class ChatHistory:
    """Append-only history with memory → disk promotion and windowed reads.

    Lifecycle
    ---------
    1.  Created with an optional *base_dir*.  If ``None``, the history
        never persists (useful for throw-away tabs or tests).
    2.  ``append()`` adds entries.  While ``len <= MEMORY_LIMIT`` they
        stay in RAM.
    3.  The first ``append()`` that exceeds the limit flushes everything
        to ``<base_dir>/chat_history/<session_id>.jsonl`` and switches to
        *disk mode*.  Subsequent appends write directly to the file.
    4.  ``window()`` returns the current visible slice.
        ``load_older()`` / ``load_newer()`` shift the window.
    """

    def __init__(
        self,
        session_id: str | None = None,
        base_dir: Path | None = None,
    ) -> None:
        self.session_id = session_id or uuid.uuid4().hex
        self._base_dir = base_dir

        # In-memory buffer (used when total count <= MEMORY_LIMIT)
        self._mem: list[ChatHistoryEntry] = []

        # Disk state
        self._on_disk = False
        self._disk_path: Path | None = None
        self._total_on_disk: int = 0  # number of lines written

        # Sliding window (indices into the logical list, 0-based)
        self._win_start: int = 0
        self._win_end: int = 0

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def total_count(self) -> int:
        return self._total_on_disk if self._on_disk else len(self._mem)

    @property
    def is_on_disk(self) -> bool:
        return self._on_disk

    @property
    def window_start(self) -> int:
        return self._win_start

    @property
    def window_end(self) -> int:
        return self._win_end

    # ------------------------------------------------------------------
    # Append
    # ------------------------------------------------------------------

    def append(self, entry: ChatHistoryEntry) -> None:
        if not self._on_disk:
            self._mem.append(entry)
            if len(self._mem) > MEMORY_LIMIT and self._base_dir is not None:
                self._flush_to_disk()
            else:
                # Keep window covering all in-memory entries
                self._win_start = 0
                self._win_end = len(self._mem)
        else:
            self._append_to_file(entry)
            self._total_on_disk += 1
            # Advance window end to include the new entry (stay at tail)
            if self._win_end == self._total_on_disk - 1:
                self._win_end = self._total_on_disk
                if self._win_end - self._win_start > WINDOW_SIZE:
                    self._win_start = self._win_end - WINDOW_SIZE

    # ------------------------------------------------------------------
    # Windowed access
    # ------------------------------------------------------------------

    def window(self) -> list[ChatHistoryEntry]:
        """Return the entries currently in the visible window."""
        if not self._on_disk:
            return list(self._mem[self._win_start:self._win_end])
        return self._read_range(self._win_start, self._win_end)

    def load_older(self) -> list[ChatHistoryEntry]:
        """Shift the window upward by ``LOAD_MORE_SIZE``.

        Returns the *newly loaded* entries (prepended to the window) so
        the caller can insert widgets without a full rebuild.  Returns an
        empty list if already at the beginning.
        """
        if self._win_start == 0:
            return []
        old_start = self._win_start
        self._win_start = max(0, self._win_start - LOAD_MORE_SIZE)
        loaded = self._read_range(self._win_start, old_start) if self._on_disk else list(self._mem[self._win_start:old_start])
        return loaded

    def has_older(self) -> bool:
        return self._win_start > 0

    def all_entries(self) -> list[ChatHistoryEntry]:
        """Return *every* entry (for export / search). Potentially large."""
        if not self._on_disk:
            return list(self._mem)
        return self._read_range(0, self._total_on_disk)

    # ------------------------------------------------------------------
    # Disk I/O
    # ------------------------------------------------------------------

    def _ensure_dir(self) -> Path:
        d = self._base_dir / "chat_history"  # type: ignore[union-attr]
        d.mkdir(parents=True, exist_ok=True)
        return d

    def _flush_to_disk(self) -> None:
        """Promote the entire in-memory list to a JSONL file."""
        d = self._ensure_dir()
        self._disk_path = d / f"{self.session_id}.jsonl"
        with open(self._disk_path, "w", encoding="utf-8") as f:
            for entry in self._mem:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
        self._total_on_disk = len(self._mem)
        self._mem.clear()
        self._on_disk = True
        # Window: show latest WINDOW_SIZE entries
        self._win_end = self._total_on_disk
        self._win_start = max(0, self._win_end - WINDOW_SIZE)

    def _append_to_file(self, entry: ChatHistoryEntry) -> None:
        assert self._disk_path is not None
        with open(self._disk_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")

    def _read_range(self, start: int, end: int) -> list[ChatHistoryEntry]:
        """Read lines ``[start, end)`` from the JSONL file."""
        assert self._disk_path is not None
        entries: list[ChatHistoryEntry] = []
        with open(self._disk_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx >= end:
                    break
                if idx >= start:
                    entries.append(ChatHistoryEntry.from_dict(json.loads(line)))
        return entries
