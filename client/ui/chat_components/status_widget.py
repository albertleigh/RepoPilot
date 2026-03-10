"""Inline status / error badge for the chat display.

Shown centered between messages for events like "Engineer started",
"Engineer stopped", or error notices.
"""
from __future__ import annotations

from html import escape

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class StatusWidget(QFrame):
    """A small pill displayed centered in the chat feed."""

    def __init__(
        self,
        text: str,
        timestamp: str = "",
        *,
        is_error: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._is_error = is_error
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self._build(text, timestamp)
        self._apply_style()

    def _build(self, text: str, timestamp: str):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 4, 14, 4)
        layout.setSpacing(6)

        icon = "\u274C" if self._is_error else "\u2022"
        ts_part = f"  {escape(timestamp)}" if timestamp else ""
        lbl = QLabel(f"{icon} {escape(text)}{ts_part}")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet("background:transparent; font-size:12px;")
        layout.addWidget(lbl)

    def _apply_style(self):
        pal = self.palette()
        fg = pal.windowText().color()
        win = pal.window().color()

        if self._is_error:
            bg = "#4c1d1d" if win.lightness() < 128 else "#fde8e8"
            text_c = "#f87171" if win.lightness() < 128 else "#b91c1c"
        else:
            if win.lightness() > 128:
                bg = _rgba(fg, 0.06)
            else:
                bg = _rgba(fg, 0.08)
            text_c = _rgba(fg, 0.50)

        self.setStyleSheet(
            f"StatusWidget {{"
            f"  background-color: {bg};"
            f"  border-radius: 10px;"
            f"}}"
            f"StatusWidget QLabel {{ color: {text_c}; }}"
        )
