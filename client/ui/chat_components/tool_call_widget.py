"""Collapsible tool-call / tool-result card.

Displays an expandable card that shows the tool name and a brief preview
when collapsed, and the full content when expanded.
"""
from __future__ import annotations

from html import escape

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


_MAX_PREVIEW = 120
_MAX_BODY = 3000


class ToolCallWidget(QFrame):
    """A collapsible card showing a tool invocation or result."""

    def __init__(
        self,
        tool_name: str,
        content: str,
        timestamp: str,
        *,
        is_result: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self._expanded = False
        self._content = content[:_MAX_BODY]
        self._is_result = is_result
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._build(tool_name, timestamp)
        self._apply_style()

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def _build(self, tool_name: str, timestamp: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── Header (clickable) ──
        icon = "\u2705" if self._is_result else "\U0001F527"
        self._chevron = "\u25B6"

        self._header_btn = QPushButton(
            f"  {icon}  {tool_name}  \u00B7  {timestamp}  {self._chevron}"
        )
        self._header_btn.setFlat(True)
        self._header_btn.setCursor(Qt.PointingHandCursor)
        self._header_btn.setStyleSheet(
            "text-align: left; padding: 6px 10px; font-size: 12px;"
        )
        self._header_btn.clicked.connect(self._toggle)
        layout.addWidget(self._header_btn)

        # ── Body (hidden by default) ──
        mono = "'Consolas','Courier New',monospace"
        self._body = QLabel(
            f'<pre style="font-family:{mono}; font-size:12px; '
            f'white-space:pre-wrap; word-wrap:break-word; margin:0;">'
            f"{escape(self._content)}</pre>"
        )
        self._body.setWordWrap(True)
        self._body.setTextFormat(Qt.RichText)
        self._body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        self._body.setContentsMargins(12, 4, 12, 8)
        self._body.setVisible(False)
        self._body.setStyleSheet("background:transparent;")
        layout.addWidget(self._body)

        self._tool_name = tool_name
        self._timestamp = timestamp

    # ------------------------------------------------------------------
    # Toggle
    # ------------------------------------------------------------------

    def _toggle(self):
        self._expanded = not self._expanded
        self._body.setVisible(self._expanded)
        icon = "\u2705" if self._is_result else "\U0001F527"
        chevron = "\u25BC" if self._expanded else "\u25B6"
        self._header_btn.setText(
            f"  {icon}  {self._tool_name}  \u00B7  {self._timestamp}  {chevron}"
        )

    # ------------------------------------------------------------------
    # Style
    # ------------------------------------------------------------------

    def _apply_style(self):
        pal = self.palette()
        win = pal.window().color()
        mid = pal.mid().color()
        fg = pal.windowText().color()

        if win.lightness() > 128:
            bg = win.darker(104)
        else:
            bg = win.lighter(112)

        accent = "#4ade80" if self._is_result else _rgba(fg, 0.25)

        self.setStyleSheet(
            f"ToolCallWidget {{"
            f"  background-color: {_rgb(bg)};"
            f"  border-left: 3px solid {accent};"
            f"  border-radius: 6px;"
            f"  margin-left: 24px;"
            f"}}"
            f"ToolCallWidget QPushButton {{"
            f"  color: {_rgba(fg, 0.7)};"
            f"  background: transparent;"
            f"}}"
            f"ToolCallWidget QPushButton:hover {{"
            f"  color: {_rgb(fg)};"
            f"}}"
            f"ToolCallWidget QLabel {{"
            f"  color: {_rgba(fg, 0.8)};"
            f"}}"
        )
