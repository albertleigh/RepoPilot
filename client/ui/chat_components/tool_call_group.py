"""Collapsible group of tool-call / tool-result cards.

When tool calls are actively streaming, the group is shown expanded with
each child :class:`ToolCallWidget` visible.  Once the next assistant text
message arrives, the group collapses into a single summary header that
the user can click to re-expand.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QPushButton, QSizePolicy, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .tool_call_widget import ToolCallWidget


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class ToolCallGroup(QFrame):
    """A collapsible container that holds multiple :class:`ToolCallWidget` items."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded = True
        self._items: list[ToolCallWidget] = []

        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        # Summary header (hidden while group is expanded / being built)
        self._header_btn = QPushButton()
        self._header_btn.setFlat(True)
        self._header_btn.setCursor(Qt.PointingHandCursor)
        self._header_btn.setStyleSheet(
            "text-align: left; padding: 6px 10px; font-size: 12px;"
        )
        self._header_btn.clicked.connect(self._toggle)
        self._header_btn.setVisible(False)
        self._layout.addWidget(self._header_btn)

        # Container for child tool-call widgets
        self._body = QWidget()
        self._body.setStyleSheet("background: transparent;")
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(2)
        self._layout.addWidget(self._body)

        self._apply_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_tool_call(
        self,
        tool_name: str,
        content: str,
        timestamp: str,
    ) -> ToolCallWidget:
        """Add a tool-call card (expanded) and return it."""
        w = ToolCallWidget(tool_name, content, timestamp, is_result=False)
        # Start expanded so user can follow along
        if not w._expanded:
            w._toggle()
        self._items.append(w)
        self._body_layout.addWidget(w)
        self._update_header_text()
        return w

    def add_tool_result(
        self,
        tool_name: str,
        content: str,
        timestamp: str,
    ) -> ToolCallWidget:
        """Add a tool-result card (expanded) and return it."""
        w = ToolCallWidget(tool_name, content, timestamp, is_result=True)
        if not w._expanded:
            w._toggle()
        self._items.append(w)
        self._body_layout.addWidget(w)
        self._update_header_text()
        return w

    def collapse(self) -> None:
        """Collapse the group — show only the summary header."""
        if not self._expanded:
            return
        self._expanded = False
        self._header_btn.setVisible(True)
        self._body.setVisible(False)
        self._update_header_text()

    def expand(self) -> None:
        """Expand the group — show all children."""
        if self._expanded:
            return
        self._expanded = True
        self._body.setVisible(True)
        self._update_header_text()

    @property
    def count(self) -> int:
        return len(self._items)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _toggle(self) -> None:
        if self._expanded:
            self.collapse()
        else:
            self.expand()

    def _update_header_text(self) -> None:
        n_calls = sum(1 for w in self._items if not w._is_result)
        n_results = sum(1 for w in self._items if w._is_result)

        # Collect unique tool names
        names = []
        seen = set()
        for w in self._items:
            if not w._is_result and w._tool_name not in seen:
                seen.add(w._tool_name)
                names.append(w._tool_name)

        if len(names) <= 3:
            names_str = ", ".join(names)
        else:
            names_str = ", ".join(names[:3]) + f" +{len(names) - 3}"

        chevron = "\u25BC" if self._expanded else "\u25B6"
        self._header_btn.setText(
            f"  \U0001F527  {n_calls} tool call{'s' if n_calls != 1 else ''}"
            f"  \u00B7  {names_str}  {chevron}"
        )

    def _apply_style(self) -> None:
        pal = self.palette()
        fg = pal.windowText().color()

        self.setStyleSheet(
            "ToolCallGroup { background: transparent; }"
            f"ToolCallGroup QPushButton {{"
            f"  color: {_rgba(fg, 0.55)};"
            f"  background: transparent;"
            f"}}"
            f"ToolCallGroup QPushButton:hover {{"
            f"  color: {_rgba(fg, 0.85)};"
            f"}}"
        )
