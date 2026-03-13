"""
Project Manager Chat Tab
Renders the conversation between the user and the ProjectManager
orchestration agent.  Displays planning, dispatch, and verification
events.

Follows the same pattern as :class:`EngineerChatTab` — owns its own
:class:`QtEventBridge` and filters PM-specific events.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor

import logging

from core.events import (
    Event, EventBus, EventKind,
)
from core.project_manager.events import (
    PMStartedEvent,
    PMStoppedEvent,
    PMMessageEvent,
    PMToolCallEvent,
    PMToolResultEvent,
    PMErrorEvent,
    PMProgressEvent,
    PMTaskDispatchedEvent,
    PMTaskVerifiedEvent,
)
from client.ui.event_bridge import QtEventBridge
from .base_chat_tab import BaseChatTab

_log = logging.getLogger(__name__)


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class ProjectManagerChatTab(BaseChatTab):
    """Chat tab for the singleton ProjectManager session.

    Subscribes to all ``PM_*`` event kinds via its own
    :class:`QtEventBridge`.
    """

    tab_icon = "\U0001F4CB"  # 📋

    # Extra signal: request full shutdown (not just cancel-current-turn)
    shutdown_requested = Signal()

    def __init__(
        self,
        event_bus: EventBus,
        llm_name: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._llm_name = llm_name

        # Customise input bar
        self.input_bar.set_placeholder("Describe project requirements\u2026")

        # Header
        self._set_header(self._build_header())

        # Own event bridge — subscribes to PM events
        self._bridge = QtEventBridge(event_bus, parent=self)
        self._bridge.on(
            {
                EventKind.PM_STARTED,
                EventKind.PM_STOPPED,
                EventKind.PM_MESSAGE,
                EventKind.PM_TOOL_CALL,
                EventKind.PM_TOOL_RESULT,
                EventKind.PM_ERROR,
                EventKind.PM_PROGRESS,
                EventKind.PM_TASK_DISPATCHED,
                EventKind.PM_TASK_VERIFIED,
            },
            self._on_event,
        )

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("pmHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        self._header_label = QLabel(
            "\U0001F4CB  <b>Project Manager</b>"
        )
        self._header_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._header_label)

        # LLM badge
        self._llm_badge = QLabel()
        self._llm_badge.setTextFormat(Qt.RichText)
        self._update_llm_badge()
        layout.addWidget(self._llm_badge)

        layout.addStretch()

        # Status dot
        self._status_dot = QLabel("\u25CF")
        self._status_dot.setToolTip("Idle")
        layout.addWidget(self._status_dot)

        # Shutdown button (stops PM completely so it can restart with new LLM)
        self._shutdown_btn = QPushButton("\u23F9  Shutdown")
        self._shutdown_btn.setFlat(True)
        self._shutdown_btn.setCursor(Qt.PointingHandCursor)
        self._shutdown_btn.setMaximumHeight(26)
        self._shutdown_btn.setToolTip("Shut down the Project Manager (can restart with a different LLM)")
        self._shutdown_btn.clicked.connect(self.shutdown_requested.emit)
        layout.addWidget(self._shutdown_btn)

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
            f"#pmHeader {{"
            f"  background-color: {bg};"
            f"  border-bottom: 1px solid {_rgba(mid, 0.3)};"
            f"}}"
            f"#pmHeader QLabel {{"
            f"  color: {_rgb(fg)}; font-size: 13px;"
            f"}}"
        )
        self._status_dot.setStyleSheet("color: #71717a; font-size: 9px;")
        btn_style = (
            f"color: {_rgba(fg, 0.5)}; font-size: 12px; padding: 2px 8px;"
            f"border: 1px solid {_rgba(mid, 0.3)}; border-radius: 4px;"
        )
        clear_btn.setStyleSheet(btn_style)
        self._shutdown_btn.setStyleSheet(btn_style)
        self._llm_badge.setStyleSheet(
            f"color: {_rgba(fg, 0.45)}; font-size: 11px;"
            f"border: 1px solid {_rgba(mid, 0.25)}; border-radius: 3px;"
            f"padding: 1px 6px;"
        )

    def _update_llm_badge(self):
        name = self._llm_name or "no LLM"
        self._llm_badge.setText(f"\u2699\ufe0f {name}")
        self._llm_badge.setToolTip(f"Current LLM: {name}")

    def set_llm_name(self, name: str):
        """Update the displayed LLM name (e.g. after a restart)."""
        self._llm_name = name
        self._update_llm_badge()

    # ------------------------------------------------------------------
    # Event handling
    # ------------------------------------------------------------------

    def _on_event(self, event: Event):
        self._dispatch(event)

    def _dispatch(self, event: Event):
        # Progress events only update the thinking indicator
        if isinstance(event, PMProgressEvent):
            self.display.show_thinking(event.detail or event.phase)
            return

        self.display.hide_thinking()

        if isinstance(event, PMMessageEvent):
            self.add_assistant_message(
                event.text, sender="Project Manager", avatar="\U0001F4CB",
            )
        elif isinstance(event, PMToolCallEvent):
            self.add_tool_call(event.tool_name, str(event.tool_input))
        elif isinstance(event, PMToolResultEvent):
            self.add_tool_result(event.tool_name, event.output)
        elif isinstance(event, PMErrorEvent):
            self.add_error(event.error)
        elif isinstance(event, PMStartedEvent):
            self._set_running(True)
            self.add_status("Project Manager started.")
        elif isinstance(event, PMStoppedEvent):
            self._set_running(False)
            self.add_status("Project Manager stopped.")
        elif isinstance(event, PMTaskDispatchedEvent):
            self.add_status(
                f"\u2709\ufe0f Task dispatched to {event.repo} [{event.dispatch_id}]"
            )
        elif isinstance(event, PMTaskVerifiedEvent):
            self.add_status(
                f"\u2705 Verification requested for {event.repo}"
            )

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
        self._bridge.close()

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------

    def get_tab_title(self) -> str:
        return "Project Manager"
