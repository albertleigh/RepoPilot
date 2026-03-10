"""Chat input bar with auto-growing text field and send controls.

Provides a styled text-input + send button with a dropdown to toggle
between *Send on Enter* and *Send on Click* modes.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QVBoxLayout, QTextEdit,
    QToolButton, QMenu, QSizePolicy,
)
from PySide6.QtCore import Signal, Qt, QEvent
from PySide6.QtGui import QColor


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class ChatInputBar(QFrame):
    """Text input + send button, suitable for embedding in any chat tab."""

    message_submitted = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._send_on_enter = True
        self.setFrameShape(QFrame.NoFrame)
        self._build_ui()
        self._apply_style()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(12, 8, 12, 10)
        outer.setSpacing(8)

        # ── Text input ──
        self._input = QTextEdit()
        self._input.setPlaceholderText("Type a message\u2026")
        self._input.setAcceptRichText(False)
        self._input.installEventFilter(self)
        self._input.document().documentLayout().documentSizeChanged.connect(
            self._auto_grow,
        )
        self._input.setMinimumHeight(38)
        self._input.setMaximumHeight(120)
        self._input.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        outer.addWidget(self._input, stretch=1)

        # ── Button column ──
        col = QVBoxLayout()
        col.setSpacing(4)

        self._send_btn = QToolButton()
        self._send_btn.setText("Send \u23CE")
        self._send_btn.setMinimumSize(80, 34)
        self._send_btn.setCursor(Qt.PointingHandCursor)
        self._send_btn.setPopupMode(QToolButton.MenuButtonPopup)
        self._send_btn.clicked.connect(self._submit)

        menu = QMenu(self._send_btn)
        self._act_enter = menu.addAction("Send on Enter")
        self._act_enter.setCheckable(True)
        self._act_enter.setChecked(True)
        self._act_click = menu.addAction("Send on Click only")
        self._act_click.setCheckable(True)
        self._act_enter.triggered.connect(lambda: self._set_mode(True))
        self._act_click.triggered.connect(lambda: self._set_mode(False))
        self._send_btn.setMenu(menu)

        col.addWidget(self._send_btn)
        col.addStretch()
        outer.addLayout(col)

    # ------------------------------------------------------------------
    # Auto-grow input height
    # ------------------------------------------------------------------

    def _auto_grow(self):
        doc_h = int(self._input.document().size().height())
        new_h = max(min(doc_h + 16, 120), 38)
        self._input.setFixedHeight(new_h)

    # ------------------------------------------------------------------
    # Send mode toggle
    # ------------------------------------------------------------------

    def _set_mode(self, on_enter: bool):
        self._send_on_enter = on_enter
        self._act_enter.setChecked(on_enter)
        self._act_click.setChecked(not on_enter)
        self._send_btn.setText("Send \u23CE" if on_enter else "Send")

    def set_send_on_enter(self, on_enter: bool):
        """Programmatically switch send mode."""
        self._set_mode(on_enter)

    # ------------------------------------------------------------------
    # Event filter — Enter key
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if (
            obj is self._input
            and event.type() == QEvent.KeyPress
            and self._send_on_enter
            and event.key() in (Qt.Key_Return, Qt.Key_Enter)
            and not event.modifiers() & Qt.ShiftModifier
        ):
            self._submit()
            return True
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------

    def _submit(self):
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self.message_submitted.emit(text)

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def set_placeholder(self, text: str):
        self._input.setPlaceholderText(text)

    def clear(self):
        self._input.clear()

    def set_enabled(self, enabled: bool):
        self._input.setEnabled(enabled)
        self._send_btn.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Theming
    # ------------------------------------------------------------------

    def _apply_style(self):
        pal = self.palette()
        base = pal.base().color()
        mid = pal.mid().color()
        fg = pal.windowText().color()
        highlight = pal.highlight().color()
        hl_text = pal.highlightedText().color()
        win = pal.window().color()

        if win.lightness() > 128:
            bar_bg = _rgb(win.darker(103))
        else:
            bar_bg = _rgb(win.lighter(108))

        self.setStyleSheet(
            f"ChatInputBar {{"
            f"  background-color: {bar_bg};"
            f"  border-top: 1px solid {_rgba(mid, 0.3)};"
            f"}}"
            # Input field
            f"ChatInputBar QTextEdit {{"
            f"  background-color: {_rgb(base)};"
            f"  color: {_rgb(fg)};"
            f"  border: 1px solid {_rgba(mid, 0.4)};"
            f"  border-radius: 8px;"
            f"  padding: 6px 10px;"
            f"  font-size: 13px;"
            f"  selection-background-color: {_rgb(highlight)};"
            f"  selection-color: {_rgb(hl_text)};"
            f"}}"
            f"ChatInputBar QTextEdit:focus {{"
            f"  border: 1px solid {_rgba(highlight, 0.6)};"
            f"}}"
            # Send button
            f"ChatInputBar QToolButton {{"
            f"  background-color: {_rgb(highlight)};"
            f"  color: {_rgb(hl_text)};"
            f"  border: none;"
            f"  border-radius: 8px;"
            f"  padding: 6px 12px;"
            f"  font-weight: 600;"
            f"  font-size: 12px;"
            f"}}"
            f"ChatInputBar QToolButton:hover {{"
            f"  background-color: {_rgb(highlight.lighter(115))};"
            f"}}"
            f"ChatInputBar QToolButton:pressed {{"
            f"  background-color: {_rgb(highlight.darker(110))};"
            f"}}"
            # Dropdown arrow area
            f"ChatInputBar QToolButton::menu-button {{"
            f"  border-left: 1px solid {_rgba(hl_text, 0.25)};"
            f"  border-top-right-radius: 8px;"
            f"  border-bottom-right-radius: 8px;"
            f"  width: 18px;"
            f"}}"
        )
