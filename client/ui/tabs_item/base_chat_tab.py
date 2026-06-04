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

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QSpinBox, QVBoxLayout, QWidget,
)
from PySide6.QtCore import Qt, QTimer, Signal

from .base_tab import BaseTab
from client.ui.chat_components import ChatDisplay, ChatInputBar
from client.ui.chat_components.chat_history import ChatHistory, ChatHistoryEntry


class BaseChatTab(BaseTab):
    """Shared layout and helpers for any chat-based tab."""

    message_sent = Signal(str)
    stop_requested = Signal()  # emitted when the user clicks stop
    chat_cleared = Signal()    # emitted when the user clicks clear

    # Subclasses set True to show the auto-prompt timer row.
    show_auto_prompt: bool = False

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        base_dir: Path | None = None,
        session_id: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._history = ChatHistory(session_id=session_id, base_dir=base_dir)
        self._agent_running = False
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
        self.display.reached_top.connect(self._on_reached_top)
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

        # Auto-prompt timer row (hidden unless subclass opts in)
        self._auto_prompt_row = QWidget()
        self._auto_prompt_row.setVisible(self.show_auto_prompt)
        ap_layout = QHBoxLayout(self._auto_prompt_row)
        ap_layout.setContentsMargins(12, 4, 12, 4)
        ap_layout.setSpacing(6)
        self._auto_prompt_cb = QCheckBox("Auto-prompt")
        self._auto_prompt_cb.setToolTip(
            "When enabled, automatically sends the prompt below\n"
            "whenever the agent becomes idle."
        )
        self._auto_prompt_cb.toggled.connect(self._on_auto_prompt_toggled)
        ap_layout.addWidget(self._auto_prompt_cb)
        self._auto_prompt_input = QLineEdit(
            "Are there any pending tasks? Maybe we should continue."
        )
        self._auto_prompt_input.setPlaceholderText(
            "Auto-prompt text\u2026"
        )
        self._auto_prompt_input.setEnabled(False)
        self._auto_prompt_input.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Fixed,
        )
        ap_layout.addWidget(self._auto_prompt_input, stretch=1)

        # Interval spinbox
        interval_label = QLabel("every")
        interval_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        ap_layout.addWidget(interval_label)
        self._auto_prompt_interval = QSpinBox()
        self._auto_prompt_interval.setRange(5, 600)
        self._auto_prompt_interval.setValue(10)
        self._auto_prompt_interval.setSuffix("s")
        self._auto_prompt_interval.setToolTip("Seconds between auto-prompt checks")
        self._auto_prompt_interval.setFixedWidth(70)
        self._auto_prompt_interval.valueChanged.connect(self._on_interval_changed)
        ap_layout.addWidget(self._auto_prompt_interval)

        root.addWidget(self._auto_prompt_row)

        # QTimer for auto-prompt (non-blocking, lives on the GUI thread)
        self._auto_prompt_timer = QTimer(self)
        self._auto_prompt_timer.setInterval(10_000)  # 10 seconds
        self._auto_prompt_timer.timeout.connect(self._on_auto_prompt_tick)
        self._last_auto_prompt_was_auto = False

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
        self._last_auto_prompt_was_auto = False
        self.display.add_user_message(text)
        self._record_entry(ChatHistoryEntry("message", role="user", text=text))
        self.message_sent.emit(text)

    # ------------------------------------------------------------------
    # Convenience methods (used by subclasses & external callers)
    # ------------------------------------------------------------------

    def add_user_message(self, text: str, **kw):
        self.display.add_user_message(text, **kw)
        self._record_entry(ChatHistoryEntry("message", role="user", text=text))

    def add_assistant_message(self, text: str, **kw):
        self.display.add_assistant_message(text, **kw)
        self._record_entry(ChatHistoryEntry("message", role="assistant", text=text))

    def add_tool_call(self, tool_name: str, tool_input: str, **kw):
        self.display.add_tool_call(tool_name, tool_input, **kw)
        self._record_entry(ChatHistoryEntry(
            "tool_call", text=tool_input, extra={"tool_name": tool_name},
        ))

    def add_tool_result(self, tool_name: str, output: str, **kw):
        self.display.add_tool_result(tool_name, output, **kw)
        self._record_entry(ChatHistoryEntry(
            "tool_result", text=output, extra={"tool_name": tool_name},
        ))

    def add_status(self, text: str):
        self.display.add_status(text)
        self._record_entry(ChatHistoryEntry("status", text=text))

    def add_error(self, text: str):
        self.display.add_error(text)
        self._record_entry(ChatHistoryEntry("error", text=text))

    def show_stop_button(self):
        """Show the stop button (call when a long-running session starts)."""
        self._agent_running = True
        self._last_auto_prompt_was_auto = False
        self._stop_row.setVisible(True)

    def hide_stop_button(self):
        """Hide the stop button (call when the session ends)."""
        self._agent_running = False
        self._stop_row.setVisible(False)

    def clear_chat(self):
        self.display.clear()
        self._history = ChatHistory(base_dir=self._history._base_dir)
        self._auto_prompt_cb.setChecked(False)
        self._last_auto_prompt_was_auto = False
        self.chat_cleared.emit()

    # ------------------------------------------------------------------
    # Auto-prompt timer
    # ------------------------------------------------------------------

    def _on_auto_prompt_toggled(self, checked: bool):
        self._auto_prompt_input.setEnabled(checked)
        self._auto_prompt_interval.setEnabled(checked)
        if checked:
            self._last_auto_prompt_was_auto = False
            self._auto_prompt_timer.start()
        else:
            self._auto_prompt_timer.stop()

    def _on_interval_changed(self, value: int):
        self._auto_prompt_timer.setInterval(value * 1000)

    def _on_auto_prompt_tick(self):
        """Timer callback — send the auto-prompt if the agent is idle."""
        if self._agent_running:
            return
        if self._last_auto_prompt_was_auto:
            # Already sent once while idle — wait for agent activity first
            return
        text = self._auto_prompt_input.text().strip()
        if not text:
            return
        self._last_auto_prompt_was_auto = True
        self._on_submit(text)
        # Keep the flag set so _on_submit's reset is overridden
        self._last_auto_prompt_was_auto = True

    # ------------------------------------------------------------------
    # Replay persisted LLM messages into the display
    # ------------------------------------------------------------------

    def replay_history(self, messages: list[dict], **kw) -> None:
        """Render a list of LLM-format messages into the chat display.

        Supports both Anthropic and OpenAI message formats.
        Keyword arguments (e.g. ``sender``, ``avatar``) are forwarded to
        the display helpers for assistant messages.
        """
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "user":
                if isinstance(content, str):
                    self.display.add_user_message(content)
                continue

            if role == "assistant":
                # Text content (both formats)
                if isinstance(content, str) and content:
                    self.display.add_assistant_message(content, **kw)
                elif isinstance(content, list):
                    # Anthropic format: content is a list of blocks
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        btype = block.get("type", "")
                        if btype == "text" and block.get("text"):
                            self.display.add_assistant_message(
                                block["text"], **kw,
                            )
                        elif btype == "tool_use":
                            self.display.add_tool_call(
                                block.get("name", "?"),
                                str(block.get("input", "")),
                            )
                # OpenAI format: tool_calls as a separate field
                for tc in msg.get("tool_calls", []):
                    fn = tc.get("function", {})
                    self.display.add_tool_call(
                        fn.get("name", "?"),
                        fn.get("arguments", ""),
                    )
                continue

            if role == "tool":
                # OpenAI tool result format
                if isinstance(content, str) and content:
                    tool_call_id = msg.get("tool_call_id", "")
                    self.display.add_tool_result(
                        tool_call_id, content[:2000],
                    )

    # ------------------------------------------------------------------
    # Windowed history — scroll-up loading
    # ------------------------------------------------------------------

    def _on_reached_top(self) -> None:
        """User scrolled near the top — prepend older entries if available."""
        if not self._history.has_older():
            self.display.finish_prepend()
            return
        older = self._history.load_older()
        if not older:
            self.display.finish_prepend()
            return
        wrappers = self._render_entries(older)
        self.display.prepend_widgets(wrappers)

    def _render_entries(self, entries: list[ChatHistoryEntry]) -> list[QWidget]:
        """Create wrapped widgets for a list of history entries.

        Used when prepending older entries that were loaded from disk.
        Returned wrappers are NOT added to the display's item list here —
        that is handled by :meth:`ChatDisplay.prepend_widgets`.
        """
        from client.ui.chat_components import (
            MessageBubble, MessageRole, ToolCallWidget,
            StatusWidget, ToolCallGroup,
        )

        wrappers: list[QWidget] = []
        # Group consecutive tool_call / tool_result entries
        pending_tools: list[ChatHistoryEntry] = []

        def _flush_tools():
            nonlocal pending_tools
            if not pending_tools:
                return
            group = ToolCallGroup()
            for te in pending_tools:
                ts_short = _short_ts(te.timestamp)
                name = te.extra.get("tool_name", "tool")
                if te.kind == "tool_call":
                    group.add_tool_call(name, te.text, ts_short)
                else:
                    group.add_tool_result(name, te.text, ts_short)
            group.collapse()
            wrappers.append(_wrap(group, Qt.AlignLeft))
            pending_tools = []

        for entry in entries:
            if entry.kind in ("tool_call", "tool_result"):
                pending_tools.append(entry)
                continue

            _flush_tools()

            ts_short = _short_ts(entry.timestamp)
            if entry.kind == "message":
                if entry.role == "user":
                    bubble = MessageBubble(
                        MessageRole.USER, "You", entry.text, ts_short,
                    )
                    wrappers.append(_wrap(bubble, Qt.AlignRight))
                else:
                    bubble = MessageBubble(
                        MessageRole.ASSISTANT, "Assistant", entry.text, ts_short,
                        avatar="\U0001F916",
                    )
                    wrappers.append(_wrap(bubble, Qt.AlignLeft))
            elif entry.kind == "status":
                wrappers.append(_wrap(StatusWidget(entry.text, ts_short), Qt.AlignHCenter))
            elif entry.kind == "error":
                wrappers.append(_wrap(StatusWidget(entry.text, ts_short, is_error=True), Qt.AlignHCenter))

        _flush_tools()
        return wrappers

    # ------------------------------------------------------------------
    # History access
    # ------------------------------------------------------------------

    def _record_entry(self, entry: ChatHistoryEntry) -> None:
        self._history.append(entry)

    @property
    def message_history(self) -> list[dict]:
        """Backward-compatible accessor — returns dicts for all entries."""
        return [e.to_dict() for e in self._history.all_entries()]


# ======================================================================
# Module-level helpers
# ======================================================================

def _short_ts(iso: str) -> str:
    """Extract HH:MM from an ISO timestamp string."""
    try:
        return iso[11:16]  # "2026-03-14T09:42:17.123" → "09:42"
    except Exception:
        return ""


def _wrap(widget: QWidget, align: Qt.AlignmentFlag) -> QWidget:
    """Wrap *widget* in an aligned row — mirrors ChatDisplay._insert logic."""
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
    return wrapper
