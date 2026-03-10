"""Animated "thinking" indicator shown in the chat feed.

Displays a pulsing dot and a short status text (e.g. "Thinking…",
"Running bash…").  The widget is designed to be *replaced* in-place:
call :meth:`update_text` to change the label without adding a new
widget to the feed.
"""
from __future__ import annotations

from html import escape

from PySide6.QtCore import (
    QPropertyAnimation, QEasingCurve, Qt, Property, QTimer,
)
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSizePolicy, QWidget,
)


def _rgb(c: QColor) -> str:
    return f"rgb({c.red()}, {c.green()}, {c.blue()})"


def _rgba(c: QColor, a: float) -> str:
    return f"rgba({c.red()}, {c.green()}, {c.blue()}, {a})"


class _PulsingDot(QWidget):
    """A small circle that fades in and out."""

    def __init__(self, color: QColor, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = color
        self._opacity = 1.0

        self._anim = QPropertyAnimation(self, b"opacity")
        self._anim.setDuration(900)
        self._anim.setStartValue(0.25)
        self._anim.setEndValue(1.0)
        self._anim.setEasingCurve(QEasingCurve.InOutSine)
        self._anim.setLoopCount(-1)  # infinite
        self._anim.start()

    # -- animated property --
    def _get_opacity(self) -> float:
        return self._opacity

    def _set_opacity(self, v: float) -> None:
        self._opacity = v
        self.update()

    opacity = Property(float, _get_opacity, _set_opacity)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QColor(self._color)
        c.setAlphaF(self._opacity)
        p.setPen(Qt.NoPen)
        p.setBrush(c)
        p.drawEllipse(1, 1, 8, 8)
        p.end()


class ThinkingIndicator(QFrame):
    """Inline progress pill for the chat feed.

    Call :meth:`update_text` to change the displayed message without
    adding a new widget.
    """

    def __init__(self, text: str = "Thinking\u2026", parent=None):
        super().__init__(parent)
        self.setFrameShape(QFrame.NoFrame)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(8)

        # Pulsing dot (accent color)
        pal = self.palette()
        accent = pal.highlight().color()
        self._dot = _PulsingDot(accent, self)
        layout.addWidget(self._dot)

        # Label
        self._label = QLabel(escape(text))
        self._label.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        layout.addWidget(self._label)

        self._apply_style()

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def update_text(self, text: str) -> None:
        """Replace the visible text."""
        self._label.setText(escape(text))

    # ------------------------------------------------------------------
    # Styling
    # ------------------------------------------------------------------

    def _apply_style(self):
        pal = self.palette()
        fg = pal.windowText().color()
        win = pal.window().color()

        if win.lightness() > 128:
            bg = _rgba(fg, 0.05)
        else:
            bg = _rgba(fg, 0.08)

        text_c = _rgba(fg, 0.55)

        self.setStyleSheet(
            f"ThinkingIndicator {{"
            f"  background-color: {bg};"
            f"  border-radius: 12px;"
            f"}}"
        )
        self._label.setStyleSheet(
            f"color: {text_c}; font-size: 12px; font-style: italic;"
            f" background: transparent;"
        )
