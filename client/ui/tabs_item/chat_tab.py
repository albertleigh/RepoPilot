"""
Chat Tab Component
Individual LLM chat conversation tab with message history and input.
Built on :class:`BaseChatTab` for a consistent look across all chat UIs.
"""
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .base_chat_tab import BaseChatTab


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class ChatTab(BaseChatTab):
    """Individual LLM chat conversation tab."""

    tab_icon = "\U0001F4AC"  # 💬

    def __init__(
        self,
        repo_name: str = "Unknown",
        llm_name: str = "Default LLM",
        parent=None,
    ):
        super().__init__(parent)
        self.repo_name = repo_name
        self.llm_name = llm_name

        self.input_bar.set_placeholder(
            "Type your question about the repository here\u2026"
        )
        self._set_header(self._build_header())

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------

    def _build_header(self) -> QFrame:
        header = QFrame()
        header.setObjectName("chatHeader")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        self._header_label = QLabel(
            f"\U0001F4AC  <b>Chat</b> \u2014 {self.repo_name}"
            f'  <span style="font-weight:normal; font-size:12px;'
            f' opacity:0.7;">{self.llm_name}</span>'
        )
        self._header_label.setTextFormat(Qt.RichText)
        layout.addWidget(self._header_label)

        layout.addStretch()

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
            f"#chatHeader {{"
            f"  background-color: {bg};"
            f"  border-bottom: 1px solid {_rgba(mid, 0.3)};"
            f"}}"
            f"#chatHeader QLabel {{"
            f"  color: {_rgb(fg)}; font-size: 13px;"
            f"}}"
        )
        clear_btn.setStyleSheet(
            f"color: {_rgba(fg, 0.5)}; font-size: 12px; padding: 2px 8px;"
            f"border: 1px solid {_rgba(mid, 0.3)}; border-radius: 4px;"
        )

    # ------------------------------------------------------------------
    # Override: also generate a dummy response (placeholder)
    # ------------------------------------------------------------------

    def _on_submit(self, text: str):
        super()._on_submit(text)
        self._add_dummy_response(text)

    def _add_dummy_response(self, user_message: str):
        """Placeholder until real LLM integration is wired up."""
        snippet = user_message[:50]
        self.add_assistant_message(
            f"*Simulated response to:* `{snippet}\u2026`\n\n"
            f"Integration with **{self.llm_name}** pending.",
            sender=self.llm_name,
            avatar="\U0001F4AC",
        )

    # ------------------------------------------------------------------
    # Public API (backward-compatible)
    # ------------------------------------------------------------------

    def add_assistant_message(self, message: str, **kw):
        kw.setdefault("sender", self.llm_name)
        kw.setdefault("avatar", "\U0001F4AC")
        super().add_assistant_message(message, **kw)

    # ------------------------------------------------------------------
    # Title
    # ------------------------------------------------------------------

    def get_tab_title(self) -> str:
        return f"{self.repo_name[:20]}"
