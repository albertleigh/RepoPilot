"""
Base Chat Tab
Abstract base for all conversation-style tabs.  Assembles a
:class:`ChatDisplay` (message feed) and a :class:`ChatInputBar`
(text input + send button) with an optional header area.

Sub-classes only need to:
1. Call ``_set_header(widget)`` for a custom header.
2. Override ``get_tab_title()`` (required by :class:`BaseTab`).
3. Connect to ``message_sent`` for outgoing messages.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, Signal

from .base_tab import BaseTab
from client.ui.chat_components import ChatDisplay, ChatInputBar


class BaseChatTab(BaseTab):
    """Shared layout and helpers for any chat-based tab."""

    message_sent = Signal(str)
    stop_requested = Signal()  # emitted when the user clicks stop

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._message_history: list[dict] = []
        self._init_chat_layout()

    # ------------------------------------------------------------------
    # Layout assembly
    # ------------------------------------------------------------------

    def _init_chat_layout(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Slot for an optional header (filled by subclasses)
        self._header_slot = QVBoxLayout()
        self._header_slot.setContentsMargins(0, 0, 0, 0)
        self._header_slot.setSpacing(0)
        root.addLayout(self._header_slot)

        # Message display
        self.display = ChatDisplay()
        root.addWidget(self.display, stretch=1)

        # Stop-button row (hidden by default)
        self._stop_row = QWidget()
        self._stop_row.setVisible(False)
        stop_layout = QHBoxLayout(self._stop_row)
        stop_layout.setContentsMargins(12, 4, 12, 4)
        stop_layout.setSpacing(0)
        stop_layout.addStretch()
        self._stop_btn = QPushButton("\u25A0  Stop")
        self._stop_btn.setCursor(Qt.PointingHandCursor)
        self._stop_btn.setFixedHeight(30)
        self._stop_btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._stop_btn.setStyleSheet(
            "QPushButton {"
            "  background-color: #dc2626; color: #fff;"
            "  border: none; border-radius: 6px;"
            "  padding: 4px 16px; font-weight: 600; font-size: 12px;"
            "}"
            "QPushButton:hover { background-color: #b91c1c; }"
            "QPushButton:pressed { background-color: #991b1b; }"
        )
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        stop_layout.addWidget(self._stop_btn)
        stop_layout.addStretch()
        root.addWidget(self._stop_row)

        # Input bar
        self.input_bar = ChatInputBar()
        self.input_bar.message_submitted.connect(self._on_submit)
        root.addWidget(self.input_bar)

    def _set_header(self, widget: QWidget):
        """Insert *widget* into the top header slot."""
        self._header_slot.addWidget(widget)

    # ------------------------------------------------------------------
    # Message flow
    # ------------------------------------------------------------------

    def _on_submit(self, text: str):
        """Called when the user presses Send."""
        self.display.add_user_message(text)
        self._record("user", text)
        self.message_sent.emit(text)

    # ------------------------------------------------------------------
    # Convenience methods (used by subclasses & external callers)
    # ------------------------------------------------------------------

    def add_user_message(self, text: str, **kw):
        self.display.add_user_message(text, **kw)
        self._record("user", text)

    def add_assistant_message(self, text: str, **kw):
        self.display.add_assistant_message(text, **kw)
        self._record("assistant", text)

    def add_status(self, text: str):
        self.display.add_status(text)

    def add_error(self, text: str):
        self.display.add_error(text)

    def show_stop_button(self):
        """Show the stop button (call when a long-running session starts)."""
        self._stop_row.setVisible(True)

    def hide_stop_button(self):
        """Hide the stop button (call when the session ends)."""
        self._stop_row.setVisible(False)

    def clear_chat(self):
        self.display.clear()
        self._message_history.clear()

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def _record(self, role: str, text: str):
        from datetime import datetime
        self._message_history.append({
            "role": role,
            "text": text,
            "timestamp": datetime.now().isoformat(),
        })

    @property
    def message_history(self) -> list[dict]:
        return list(self._message_history)
