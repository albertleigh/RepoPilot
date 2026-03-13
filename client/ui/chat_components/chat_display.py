"""Scrollable chat message display.

A ``QScrollArea`` that hosts a vertical list of :class:`MessageBubble`,
:class:`ToolCallGroup`, and :class:`StatusWidget` instances.  Provides a
simple API for adding different message types and auto-scrolls to the
latest entry.
"""
from __future__ import annotations

from datetime import datetime

from PySide6.QtWidgets import (
    QScrollArea, QWidget, QVBoxLayout, QHBoxLayout,
    QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, QTimer

from .message_bubble import MessageBubble, MessageRole
from .tool_call_group import ToolCallGroup
from .status_widget import StatusWidget
from .thinking_indicator import ThinkingIndicator


class ChatDisplay(QScrollArea):
    """Chat message feed with auto-scroll and themed background."""

    def __init__(self, parent=None):
        super().__init__(parent)

        # Scrollbar policy
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)

        # Container
        self._container = QWidget()
        self._container.setObjectName("chatContainer")
        self._layout = QVBoxLayout(self._container)
        self._layout.setContentsMargins(12, 12, 12, 12)
        self._layout.setSpacing(6)
        self._layout.addStretch()  # keeps items pinned to top
        self.setWidget(self._container)

        # Track items for resize & clear
        self._items: list[QWidget] = []
        self._thinking: QWidget | None = None      # current thinking row
        self._thinking_indicator: ThinkingIndicator | None = None

        # Active tool-call group (expanded while streaming)
        self._pending_group: ToolCallGroup | None = None
        self._pending_group_wrapper: QWidget | None = None

        self._apply_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_user_message(
        self,
        text: str,
        sender: str = "You",
        *,
        avatar: str = "",
        timestamp: str | None = None,
    ):
        ts = timestamp or self._ts()
        bubble = MessageBubble(MessageRole.USER, sender, text, ts, avatar=avatar)
        self._insert(bubble, align=Qt.AlignRight)

    def add_assistant_message(
        self,
        text: str,
        sender: str = "Assistant",
        *,
        avatar: str = "\U0001F916",
        timestamp: str | None = None,
    ):
        self._collapse_pending_group()
        ts = timestamp or self._ts()
        bubble = MessageBubble(MessageRole.ASSISTANT, sender, text, ts, avatar=avatar)
        self._insert(bubble, align=Qt.AlignLeft)

    def add_tool_call(
        self,
        tool_name: str,
        tool_input: str,
        *,
        timestamp: str | None = None,
    ):
        ts = timestamp or self._ts()
        group = self._ensure_pending_group()
        group.add_tool_call(tool_name, tool_input, ts)
        QTimer.singleShot(20, self._scroll_to_bottom)

    def add_tool_result(
        self,
        tool_name: str,
        output: str,
        *,
        timestamp: str | None = None,
    ):
        ts = timestamp or self._ts()
        group = self._ensure_pending_group()
        group.add_tool_result(tool_name, output, ts)
        QTimer.singleShot(20, self._scroll_to_bottom)

    def add_status(self, text: str, *, timestamp: str | None = None):
        ts = timestamp or self._ts()
        widget = StatusWidget(text, ts)
        self._insert(widget, align=Qt.AlignHCenter)

    def add_error(self, text: str, *, timestamp: str | None = None):
        ts = timestamp or self._ts()
        widget = StatusWidget(text, ts, is_error=True)
        self._insert(widget, align=Qt.AlignHCenter)

    def show_thinking(self, text: str = "Thinking\u2026") -> None:
        """Show or update the thinking indicator at the bottom of the feed."""
        if self._thinking_indicator is not None:
            self._thinking_indicator.update_text(text)
            QTimer.singleShot(20, self._scroll_to_bottom)
            return
        indicator = ThinkingIndicator(text)
        self._thinking_indicator = indicator
        # Insert like a centered status
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addStretch(1)
        row.addWidget(indicator)
        row.addStretch(1)
        wrapper = QWidget()
        wrapper.setStyleSheet("background:transparent;")
        wrapper.setLayout(row)
        idx = max(self._layout.count() - 1, 0)
        self._layout.insertWidget(idx, wrapper)
        self._thinking = wrapper
        QTimer.singleShot(20, self._scroll_to_bottom)

    def hide_thinking(self) -> None:
        """Remove the thinking indicator if visible."""
        if self._thinking is not None:
            self._thinking.setParent(None)
            self._thinking.deleteLater()
            self._thinking = None
            self._thinking_indicator = None

    def clear(self):
        for w in self._items:
            w.setParent(None)
            w.deleteLater()
        self._items.clear()
        self._pending_group = None
        self._pending_group_wrapper = None
        self.hide_thinking()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _ts() -> str:
        return datetime.now().strftime("%H:%M")

    def _ensure_pending_group(self) -> ToolCallGroup:
        """Return the current open tool-call group, creating one if needed."""
        if self._pending_group is None:
            group = ToolCallGroup()
            self._pending_group = group
            # Wrap in a left-aligned row like other items
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(0)
            row.addWidget(group)
            row.addStretch(1)
            wrapper = QWidget()
            wrapper.setStyleSheet("background:transparent;")
            wrapper.setLayout(row)
            idx = max(self._layout.count() - 1, 0)
            self._layout.insertWidget(idx, wrapper)
            self._items.append(wrapper)
            self._pending_group_wrapper = wrapper
        return self._pending_group

    def _collapse_pending_group(self) -> None:
        """Collapse the active tool-call group (called when a text message arrives)."""
        if self._pending_group is not None:
            self._pending_group.collapse()
            self._pending_group = None
            self._pending_group_wrapper = None

    def _insert(self, widget: QWidget, align: Qt.AlignmentFlag):
        """Wrap *widget* in a row with the desired alignment and add it."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)

        if align == Qt.AlignRight:
            row.addStretch(1)
            row.addWidget(widget)
        elif align == Qt.AlignHCenter:
            row.addStretch(1)
            row.addWidget(widget)
            row.addStretch(1)
        else:
            row.addWidget(widget)
            row.addStretch(1)

        wrapper = QWidget()
        wrapper.setStyleSheet("background:transparent;")
        wrapper.setLayout(row)

        # Insert before the terminal stretch
        idx = max(self._layout.count() - 1, 0)
        self._layout.insertWidget(idx, wrapper)
        self._items.append(wrapper)

        # Update bubble max-width
        if isinstance(widget, MessageBubble):
            self._constrain_bubble(widget)

        QTimer.singleShot(20, self._scroll_to_bottom)

    def _scroll_to_bottom(self):
        sb = self.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _constrain_bubble(self, bubble: MessageBubble):
        vp = self.viewport().width()
        bubble.setMaximumWidth(max(int(vp * 0.78), 280))

    # ------------------------------------------------------------------
    # Resize handling — keep bubbles proportional
    # ------------------------------------------------------------------

    def resizeEvent(self, event):
        super().resizeEvent(event)
        vp = self.viewport().width()
        max_w = max(int(vp * 0.78), 280)
        for wrapper in self._items:
            lay = wrapper.layout()
            if lay is None:
                continue
            for i in range(lay.count()):
                w = lay.itemAt(i).widget()
                if isinstance(w, MessageBubble):
                    w.setMaximumWidth(max_w)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        self.setStyleSheet(
            "QScrollArea { background: transparent; border: none; }"
            "QScrollBar:vertical {"
            "  background: transparent; width: 8px;"
            "}"
            "QScrollBar::handle:vertical {"
            "  background: rgba(128,128,128,0.25); border-radius: 4px;"
            "  min-height: 24px;"
            "}"
            "QScrollBar::handle:vertical:hover {"
            "  background: rgba(128,128,128,0.45);"
            "}"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {"
            "  height: 0px;"
            "}"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {"
            "  background: transparent;"
            "}"
        )
        self._container.setStyleSheet("#chatContainer { background: transparent; }")
