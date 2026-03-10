"""
Engineer Chat Tab
Renders the accumulated conversation between a user and an EngineerManager
agent, including tool calls and results.  Allows sending new messages.

Uses the shared :class:`BaseChatTab` layout (display + input bar) and
adds event-bridge integration for live tool-call / result streaming.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

import logging

from core.events import (
    Event, EventBus, EventKind,
    EngineerMessageEvent,
    EngineerProgressEvent,
    EngineerToolCallEvent,
    EngineerToolResultEvent,
    EngineerErrorEvent,
    EngineerStartedEvent,
    EngineerStoppedEvent,
)
from client.ui.event_bridge import QtEventBridge
from .base_chat_tab import BaseChatTab

_log = logging.getLogger(__name__)


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class EngineerChatTab(BaseChatTab):
    """Chat tab for a single EngineerManager session.

    Each tab creates its own :class:`QtEventBridge`, subscribes only to
    the engineer event kinds it cares about, and filters by *workdir* so
    it never receives events from a different repo.  The bridge is
    automatically cleaned up when the tab is destroyed.
    """

    tab_icon = "\U0001F916"  # 🤖

    def __init__(
        self,
        repo_name: str,
        event_bus: EventBus,
        workdir: str,
        parent=None,
    ):
        super().__init__(parent)
        self.repo_name = repo_name
        self._workdir = str(Path(workdir).resolve())

        # Customise input bar
        self.input_bar.set_placeholder("Type instructions for the agent\u2026")

        # Header
        self._set_header(self._build_header())

        # Own event bridge — subscribes to engineer events for this workdir
        self._bridge = QtEventBridge(event_bus, parent=self)
        self._bridge.on(
            {
                EventKind.ENGINEER_STARTED,
                EventKind.ENGINEER_STOPPED,
                EventKind.ENGINEER_MESSAGE,
                EventKind.ENGINEER_TOOL_CALL,
                EventKind.ENGINEER_TOOL_RESULT,
                EventKind.ENGINEER_ERROR,
                EventKind.ENGINEER_PROGRESS,
            },
            self._on_event,
        )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("engineerHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        self._header_label = QLabel(
            f"\U0001F916  <b>Engineer</b> \u2014 {self.repo_name}"
        )
        self._header_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._header_label)

        layout.addStretch()

        # Status dot
        self._status_dot = QLabel("\u25CF")
        self._status_dot.setToolTip("Idle")
        layout.addWidget(self._status_dot)

        # Clear button
        clear_btn = QPushButton("Clear")
        clear_btn.setFlat(True)
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.setMaximumHeight(26)
        clear_btn.clicked.connect(self.clear_chat)
        layout.addWidget(clear_btn)

        self._style_header(header, clear_btn)
        return header

    def _style_header(self, header: QFrame, clear_btn: QPushButton):
        pal = self.palette()
        win = pal.window().color()
        fg = pal.windowText().color()
        mid = pal.mid().color()

        if win.lightness() > 128:
            bg = _rgb(win.darker(105))
        else:
            bg = _rgb(win.lighter(112))

        header.setStyleSheet(
            f"#engineerHeader {{"
            f"  background-color: {bg};"
            f"  border-bottom: 1px solid {_rgba(mid, 0.3)};"
            f"}}"
            f"#engineerHeader QLabel {{"
            f"  color: {_rgb(fg)}; font-size: 13px;"
            f"}}"
        )
        self._status_dot.setStyleSheet("color: #71717a; font-size: 9px;")
        clear_btn.setStyleSheet(
            f"color: {_rgba(fg, 0.5)}; font-size: 12px; padding: 2px 8px;"
            f"border: 1px solid {_rgba(mid, 0.3)}; border-radius: 4px;"
        )

    # ------------------------------------------------------------------
    # Event handling — self-subscribed via own QtEventBridge
    # ------------------------------------------------------------------

    def _on_event(self, event: Event):
        """Filter by workdir and dispatch to the appropriate renderer."""
        workdir: str = getattr(event, "workdir", "")
        resolved = str(Path(workdir).resolve()) if workdir else ""
        _log.debug("[DIAG] EngineerChatTab._on_event: kind=%s, event_workdir=%s, my_workdir=%s, match=%s",
                   event.kind, resolved, self._workdir, resolved == self._workdir)
        if resolved != self._workdir:
            return
        self._dispatch(event)

    def _dispatch(self, event: Event):
        """Render a single event."""
        _log.debug("[DIAG] EngineerChatTab._dispatch: rendering %s", event.kind)

        # Progress events only update the thinking indicator
        if isinstance(event, EngineerProgressEvent):
            self.display.show_thinking(event.detail or event.phase)
            return

        # Any concrete event replaces the thinking indicator
        self.display.hide_thinking()

        if isinstance(event, EngineerMessageEvent):
            self.display.add_assistant_message(
                event.text, sender="Engineer", avatar="\U0001F916",
            )
        elif isinstance(event, EngineerToolCallEvent):
            self.display.add_tool_call(event.tool_name, str(event.tool_input))
        elif isinstance(event, EngineerToolResultEvent):
            self.display.add_tool_result(event.tool_name, event.output)
        elif isinstance(event, EngineerErrorEvent):
            self.display.add_error(event.error)
        elif isinstance(event, EngineerStartedEvent):
            self._set_running(True)
            self.display.add_status("Engineer started.")
        elif isinstance(event, EngineerStoppedEvent):
            self._set_running(False)
            self.display.add_status("Engineer stopped.")

    def _set_running(self, running: bool):
        if running:
            self._status_dot.setStyleSheet("color: #4ade80; font-size: 9px;")
            self._status_dot.setToolTip("Running")
            self.show_stop_button()
        else:
            self._status_dot.setStyleSheet("color: #71717a; font-size: 9px;")
            self._status_dot.setToolTip("Idle")
            self.hide_stop_button()

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def close_bridge(self):
        """Explicitly tear down the event subscription."""
        self._bridge.close()

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------

    def get_tab_title(self) -> str:
        return f"{self.repo_name[:20]}"
