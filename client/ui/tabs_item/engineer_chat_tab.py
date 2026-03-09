"""
Engineer Chat Tab
Renders the accumulated conversation between a user and an EngineerManager
agent, including tool calls and results.  Allows sending new messages.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QWidget, QMenu, QToolButton,
)
from PySide6.QtCore import Signal, Qt, QEvent
from PySide6.QtGui import QTextCursor, QTextBlockFormat

from core.events import (
    Event, EventBus, EventKind,
    EngineerMessageEvent,
    EngineerToolCallEvent,
    EngineerToolResultEvent,
    EngineerErrorEvent,
    EngineerStartedEvent,
    EngineerStoppedEvent,
)
from client.ui.event_bridge import QtEventBridge
from .base_tab import BaseTab


class EngineerChatTab(BaseTab):
    """Chat tab for a single EngineerManager session.

    Each tab creates its own :class:`QtEventBridge`, subscribes only to
    the engineer event kinds it cares about, and filters by *workdir* so
    it never receives events from a different repo.  The bridge is
    automatically cleaned up when the tab is destroyed.
    """

    message_sent = Signal(str)  # user text → wired to manager.send_message

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
            },
            self._on_event,
        )

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)

        # Header
        header = QHBoxLayout()
        self._header_label = QLabel(f"\U0001F916 Engineer — {self.repo_name}")
        self._header_label.setStyleSheet(
            "font-weight: bold; padding: 5px; "
            "background-color: palette(midlight); color: palette(window-text);"
        )
        header.addWidget(self._header_label)
        layout.addLayout(header)

        # Chat display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Engineer conversation will appear here…")
        layout.addWidget(self.chat_display, stretch=3)

        # Input area — text on left, buttons stacked on right
        input_row = QHBoxLayout()
        input_row.setContentsMargins(0, 5, 0, 0)

        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Type instructions for the agent…")
        self.message_input.setMaximumHeight(100)
        self.message_input.installEventFilter(self)
        input_row.addWidget(self.message_input, stretch=1)

        # Right-side button column
        btn_col = QVBoxLayout()
        btn_col.setSpacing(4)

        # Send dropdown button
        self._send_on_enter = True
        self.send_button = QToolButton()
        self.send_button.setText("Send ⏎")
        self.send_button.setMinimumHeight(35)
        self.send_button.setMinimumWidth(100)
        self.send_button.setPopupMode(QToolButton.MenuButtonPopup)
        self.send_button.clicked.connect(self._on_send)

        send_menu = QMenu(self.send_button)
        self._act_enter = send_menu.addAction("Send on Enter")
        self._act_enter.setCheckable(True)
        self._act_enter.setChecked(True)
        self._act_click = send_menu.addAction("Send on Click")
        self._act_click.setCheckable(True)
        self._act_enter.triggered.connect(lambda: self._set_send_mode(True))
        self._act_click.triggered.connect(lambda: self._set_send_mode(False))
        self.send_button.setMenu(send_menu)

        btn_col.addWidget(self.send_button)

        self.clear_button = QPushButton("Clear Display")
        self.clear_button.clicked.connect(self.chat_display.clear)
        btn_col.addWidget(self.clear_button)

        btn_col.addStretch()
        input_row.addLayout(btn_col)

        layout.addLayout(input_row)

    # ------------------------------------------------------------------
    # Send-mode switching
    # ------------------------------------------------------------------

    def _set_send_mode(self, on_enter: bool):
        self._send_on_enter = on_enter
        self._act_enter.setChecked(on_enter)
        self._act_click.setChecked(not on_enter)
        self.send_button.setText("Send ⏎" if on_enter else "Send")

    def eventFilter(self, obj, event):
        """Intercept Enter in the message input when send-on-enter is active."""
        if (
            obj is self.message_input
            and event.type() == QEvent.KeyPress
            and self._send_on_enter
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and not event.modifiers() & Qt.ShiftModifier
        ):
            self._on_send()
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Sending
    # ------------------------------------------------------------------

    def _on_send(self):
        text = self.message_input.toPlainText().strip()
        if not text:
            return
        self._append_user(text)
        self.message_input.clear()
        self.message_sent.emit(text)

    # ------------------------------------------------------------------
    # Rendering helpers (palette-aware)
    # ------------------------------------------------------------------

    def _ts(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _color(self, role: str) -> str:
        """Return an ``rgb(…)`` CSS string derived from the palette."""
        pal = self.palette()
        if role == "user":
            c = pal.link().color()
        elif role == "error":
            c = pal.highlight().color().darker(130)
        else:
            c = pal.highlight().color().lighter(130) if pal.highlight().color().lightness() < 128 \
                else pal.highlight().color().darker(130)
        return f"rgb({c.red()}, {c.green()}, {c.blue()})"

    def _fg(self) -> str:
        c = self.palette().windowText().color()
        return f"rgb({c.red()}, {c.green()}, {c.blue()})"

    def _append_html(self, html: str, align: Qt.AlignmentFlag = Qt.AlignLeft):
        cursor = self.chat_display.textCursor()
        cursor.movePosition(QTextCursor.End)
        # Insert a new block with the desired alignment
        fmt = QTextBlockFormat()
        fmt.setAlignment(align)
        fmt.setBottomMargin(6)
        cursor.insertBlock(fmt)
        # Only inline HTML here — no <div>/<p> — so block format sticks
        cursor.insertHtml(html)
        self.chat_display.setTextCursor(cursor)
        sb = self.chat_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    # ------------------------------------------------------------------
    # Public: append different message types
    # ------------------------------------------------------------------

    def _append_user(self, text: str):
        self._append_html(
            f'<b style="color:{self._color("user")};">[{self._ts()}] User:</b><br>'
            f'<span style="color:{self._fg()};">{escape(text)}</span>',
            align=Qt.AlignRight,
        )

    def append_assistant(self, text: str):
        self._append_html(
            f'<b style="color:{self._color("assistant")};">[{self._ts()}] Engineer:</b><br>'
            f'<span style="color:{self._fg()};">{escape(text)}</span>'
        )

    def append_tool_call(self, tool_name: str, tool_input: str):
        self._append_html(
            f'<i style="color:{self._color("assistant")};">'
            f'[{self._ts()}] \U0001F527 {escape(tool_name)}</i><br>'
            f'<code style="color:{self._fg()};">{escape(tool_input[:500])}</code>'
        )

    def append_tool_result(self, tool_name: str, output: str):
        self._append_html(
            f'<i style="color:{self._color("assistant")};">'
            f'[{self._ts()}] \u2705 {escape(tool_name)}</i><br>'
            f'<code style="color:{self._fg()};">{escape(output[:500])}</code>'
        )

    def append_error(self, error: str):
        self._append_html(
            f'<b style="color:{self._color("error")};">[{self._ts()}] \u274C Error:</b><br>'
            f'<span style="color:{self._fg()};">{escape(error)}</span>'
        )

    def append_status(self, text: str):
        self._append_html(
            f'<span style="font-style:italic; color:{self._fg()};">'
            f'[{self._ts()}] {escape(text)}</span>'
        )

    # ------------------------------------------------------------------
    # Event handling — self-subscribed via own QtEventBridge
    # ------------------------------------------------------------------

    def _on_event(self, event: Event):
        """Filter by workdir and dispatch to the appropriate renderer."""
        workdir: str = getattr(event, "workdir", "")
        if str(Path(workdir).resolve()) != self._workdir:
            return
        self._dispatch(event)

    def _dispatch(self, event: Event):
        """Render a single event."""
        if isinstance(event, EngineerMessageEvent):
            self.append_assistant(event.text)
        elif isinstance(event, EngineerToolCallEvent):
            self.append_tool_call(event.tool_name, str(event.tool_input))
        elif isinstance(event, EngineerToolResultEvent):
            self.append_tool_result(event.tool_name, event.output)
        elif isinstance(event, EngineerErrorEvent):
            self.append_error(event.error)
        elif isinstance(event, EngineerStartedEvent):
            self.append_status("Engineer started.")
        elif isinstance(event, EngineerStoppedEvent):
            self.append_status("Engineer stopped.")

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
