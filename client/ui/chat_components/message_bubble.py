"""Chat message bubble widget.

Renders a single message as a rounded, palette-aware card aligned left
(assistant) or right (user).
"""
from __future__ import annotations

from enum import Enum, auto
from html import escape

from PySide6.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy, QMenu, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from .markdown_renderer import render_markdown


class MessageRole(Enum):
    USER = auto()
    ASSISTANT = auto()


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class MessageBubble(QFrame):
    """A single chat message rendered as a styled bubble.

    The *role* controls alignment, colours, and shape.
    """

    def __init__(
        self,
        role: MessageRole,
        sender: str,
        text: str,
        timestamp: str,
        *,
        avatar: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.role = role
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        self._build(sender, text, timestamp, avatar)
        self._apply_style()

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def _build(self, sender: str, text: str, timestamp: str, avatar: str):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        # ── Header: avatar · sender · timestamp ──
        header = QHBoxLayout()
        header.setSpacing(6)
        if avatar:
            icon = QLabel(avatar)
            icon.setFixedWidth(18)
            icon.setStyleSheet("background:transparent;")
            header.addWidget(icon)

        sender_lbl = QLabel(f"<b>{escape(sender)}</b>")
        sender_lbl.setStyleSheet("background:transparent;")
        header.addWidget(sender_lbl)
        header.addStretch()

        ts_lbl = QLabel(timestamp)
        ts_lbl.setStyleSheet("background:transparent;")
        ts_lbl.setProperty("role", "timestamp")
        header.addWidget(ts_lbl)
        layout.addLayout(header)

        # ── Body ──
        code_bg, code_fg = self._code_colors()
        body_html = render_markdown(text, code_bg=code_bg, code_fg=code_fg)

        body = QLabel(body_html)
        body.setWordWrap(True)
        body.setTextFormat(Qt.RichText)
        body.setTextInteractionFlags(Qt.TextBrowserInteraction)
        body.setOpenExternalLinks(True)
        body.setStyleSheet("background:transparent;")
        body.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        body.setContextMenuPolicy(Qt.CustomContextMenu)
        body.customContextMenuRequested.connect(
            lambda pos, lbl=body: self._show_body_menu(lbl, pos)
        )
        layout.addWidget(body)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_body_menu(self, label: QLabel, pos):
        menu = QMenu(self)
        pal = self.palette()
        win = pal.window().color()
        fg = pal.windowText().color()
        mid = pal.mid().color()
        highlight = pal.highlight().color()
        hl_text = pal.highlightedText().color()
        menu.setStyleSheet(
            f"QMenu {{"
            f"  background-color: {_rgb(win)};"
            f"  color: {_rgb(fg)};"
            f"  border: 1px solid {_rgba(mid, 0.4)};"
            f"  border-radius: 6px;"
            f"  padding: 4px 0;"
            f"}}"
            f"QMenu::item {{"
            f"  padding: 5px 24px;"
            f"}}"
            f"QMenu::item:selected {{"
            f"  background-color: {_rgb(highlight)};"
            f"  color: {_rgb(hl_text)};"
            f"}}"
        )
        copy_act = menu.addAction("Copy")
        select_all_act = menu.addAction("Select All")
        copy_all_act = menu.addAction("Copy All")
        chosen = menu.exec_(label.mapToGlobal(pos))
        if chosen == copy_act:
            selected = label.selectedText()
            if selected:
                QApplication.clipboard().setText(selected)
            else:
                QApplication.clipboard().setText(label.text())
        elif chosen == select_all_act:
            label.setSelection(0, len(label.text()))
        elif chosen == copy_all_act:
            label.setSelection(0, len(label.text()))
            QApplication.clipboard().setText(label.text())

    # ------------------------------------------------------------------
    # Palette-derived styling
    # ------------------------------------------------------------------

    def _code_colors(self) -> tuple[str, str]:
        """Return (code_bg, code_fg) suitable for code blocks."""
        pal = self.palette()
        if self.role == MessageRole.USER:
            bg = pal.highlight().color()
            if bg.lightness() > 128:
                return "#00000018", _rgb(pal.highlightedText().color())
            return "#ffffff15", _rgb(pal.highlightedText().color())
        base = pal.window().color()
        if base.lightness() > 128:
            return "#e8e8ee", "#1e1e2e"
        return "#16161e", "#cdd6f4"

    def _apply_style(self):
        pal = self.palette()
        if self.role == MessageRole.USER:
            bg = pal.highlight().color()
            fg = pal.highlightedText().color()
            self.setStyleSheet(
                f"MessageBubble {{"
                f"  background-color: {_rgb(bg)};"
                f"  border-radius: 14px;"
                f"  border-bottom-right-radius: 4px;"
                f"}}"
                f"MessageBubble QLabel {{ color: {_rgb(fg)}; }}"
                f"MessageBubble QLabel[role='timestamp'] {{"
                f"  color: {_rgba(fg, 0.55)}; font-size: 11px;"
                f"}}"
            )
        else:
            win = pal.window().color()
            if win.lightness() > 128:
                card_bg = win.darker(107)
            else:
                card_bg = win.lighter(125)
            border = pal.mid().color()
            fg = pal.windowText().color()
            self.setStyleSheet(
                f"MessageBubble {{"
                f"  background-color: {_rgb(card_bg)};"
                f"  border: 1px solid {_rgba(border, 0.35)};"
                f"  border-radius: 14px;"
                f"  border-bottom-left-radius: 4px;"
                f"}}"
                f"MessageBubble QLabel {{ color: {_rgb(fg)}; }}"
                f"MessageBubble QLabel[role='timestamp'] {{"
                f"  color: {_rgba(fg, 0.45)}; font-size: 11px;"
                f"}}"
            )
