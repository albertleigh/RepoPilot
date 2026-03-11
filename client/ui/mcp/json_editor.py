"""
JsonEditor – a self-contained JSON code-editor widget built on PySide6.

Features
--------
* Syntax highlighting (keys, strings, numbers, booleans, null, braces)
* Line-number gutter
* Live bracket / brace / bracket matching highlight
* Auto-indent on Enter
* Tab → 2-space indent
* Format-JSON action
* Live validation status bar
"""
from __future__ import annotations

import json
import re

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QSyntaxHighlighter,
    QTextCharFormat, QTextCursor, QTextDocument, QKeyEvent,
    QPalette, QPen, QTextFormat,
)
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QPushButton,
    QTextEdit as _QTextEdit, QVBoxLayout, QWidget,
)


# ------------------------------------------------------------------
# Colour palette (works on both light and dark themes)
# ------------------------------------------------------------------

_CLR_KEY = QColor("#0451a5")       # dict keys
_CLR_STRING = QColor("#a31515")    # string values
_CLR_NUMBER = QColor("#098658")    # numbers
_CLR_BOOL = QColor("#0000ff")      # true / false
_CLR_NULL = QColor("#808080")      # null
_CLR_BRACE = QColor("#000000")     # { } [ ]
_CLR_MATCH_BG = QColor("#b4d7ff")  # bracket-match highlight


# ------------------------------------------------------------------
# Syntax highlighter
# ------------------------------------------------------------------

class _JsonHighlighter(QSyntaxHighlighter):
    """Regex-based JSON syntax highlighter."""

    def __init__(self, document: QTextDocument):
        super().__init__(document)

        self._rules: list[tuple[re.Pattern, QTextCharFormat]] = []

        def _fmt(color: QColor, bold: bool = False) -> QTextCharFormat:
            f = QTextCharFormat()
            f.setForeground(color)
            if bold:
                f.setFontWeight(QFont.Bold)
            return f

        # Order matters – first match wins per character range.
        # 1. Strings (including keys) — we distinguish keys later
        self._string_fmt = _fmt(_CLR_STRING)
        self._key_fmt = _fmt(_CLR_KEY, bold=True)
        self._string_re = re.compile(r'"(?:[^"\\]|\\.)*"')

        # 2. Numbers
        self._rules.append((
            re.compile(r'\b-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?\b'),
            _fmt(_CLR_NUMBER),
        ))

        # 3. Booleans
        self._rules.append((
            re.compile(r'\b(?:true|false)\b'),
            _fmt(_CLR_BOOL, bold=True),
        ))

        # 4. Null
        self._rules.append((
            re.compile(r'\bnull\b'),
            _fmt(_CLR_NULL, bold=True),
        ))

        # 5. Braces / brackets
        self._rules.append((
            re.compile(r'[{}\[\]]'),
            _fmt(_CLR_BRACE, bold=True),
        ))

    def highlightBlock(self, text: str) -> None:  # noqa: N802
        # Strings first (keys vs. values)
        for m in self._string_re.finditer(text):
            start, end = m.start(), m.end()
            # A string is a *key* if it is followed (ignoring whitespace)
            # by a colon.
            rest = text[end:].lstrip()
            fmt = self._key_fmt if rest.startswith(":") else self._string_fmt
            self.setFormat(start, end - start, fmt)

        # Other tokens — skip regions already formatted as strings
        for pattern, fmt in self._rules:
            for m in pattern.finditer(text):
                start, length = m.start(), m.end() - m.start()
                # Only apply if not inside a string
                if self.format(start) not in (self._string_fmt, self._key_fmt):
                    self.setFormat(start, length, fmt)


# ------------------------------------------------------------------
# Line-number area
# ------------------------------------------------------------------

class _LineNumberArea(QWidget):
    """Thin widget that draws line numbers in the gutter."""

    def __init__(self, editor: "_JsonTextEdit"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event) -> None:  # noqa: N802
        self._editor.paint_line_numbers(event)


# ------------------------------------------------------------------
# Core text-edit with line numbers & bracket matching
# ------------------------------------------------------------------

_BRACKETS = {"{": "}", "[": "]"}
_CLOSE_TO_OPEN = {v: k for k, v in _BRACKETS.items()}


class _JsonTextEdit(QPlainTextEdit):
    """QPlainTextEdit subclass with line numbers, bracket matching,
    auto-indent, and 2-space soft-tabs."""

    def __init__(self, parent=None):
        super().__init__(parent)
        mono = QFont("Consolas", 10)
        mono.setStyleHint(QFont.Monospace)
        self.setFont(mono)
        self.setTabStopDistance(
            QFontMetrics(mono).horizontalAdvance(" ") * 2)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)

        self._line_area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_line_area_width)
        self.updateRequest.connect(self._update_line_area)
        self.cursorPositionChanged.connect(self._highlight_matching_bracket)
        self._update_line_area_width(0)

    # -- line numbers --------------------------------------------------

    def line_number_area_width(self) -> int:
        digits = max(1, len(str(self.blockCount())))
        return 10 + self.fontMetrics().horizontalAdvance("9") * digits

    def _update_line_area_width(self, _new_count: int) -> None:
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_line_area(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_area.scroll(0, dy)
        else:
            self._line_area.update(0, rect.y(),
                                   self._line_area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_line_area_width(0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        cr = self.contentsRect()
        self._line_area.setGeometry(
            QRect(cr.left(), cr.top(),
                  self.line_number_area_width(), cr.height()))

    def paint_line_numbers(self, event) -> None:
        painter = QPainter(self._line_area)
        painter.fillRect(event.rect(),
                         self.palette().color(QPalette.Window))
        block = self.firstVisibleBlock()
        num = block.blockNumber()
        top = round(self.blockBoundingGeometry(block)
                    .translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())

        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.setPen(self.palette().color(QPalette.PlaceholderText))
                painter.drawText(
                    0, top,
                    self._line_area.width() - 4,
                    self.fontMetrics().height(),
                    Qt.AlignRight, str(num + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + round(self.blockBoundingRect(block).height())
            num += 1
        painter.end()

    # -- bracket matching -----------------------------------------------

    def _highlight_matching_bracket(self) -> None:
        extras: list = []
        cursor = self.textCursor()
        doc = self.document()
        pos = cursor.position()
        if pos <= 0:
            self.setExtraSelections(extras)
            return

        # Check character before and at cursor
        for check_pos in (pos - 1, pos):
            if check_pos < 0 or check_pos >= doc.characterCount():
                continue
            c = doc.characterAt(check_pos)
            match_pos = -1
            if c in _BRACKETS:
                match_pos = self._find_forward(check_pos, c, _BRACKETS[c])
            elif c in _CLOSE_TO_OPEN:
                match_pos = self._find_backward(check_pos, c,
                                                _CLOSE_TO_OPEN[c])
            if match_pos >= 0:
                for p in (check_pos, match_pos):
                    sel = _QTextEdit.ExtraSelection()
                    sel.format.setBackground(_CLR_MATCH_BG)
                    sel.format.setProperty(QTextFormat.FullWidthSelection,
                                           False)
                    tc = QTextCursor(doc)
                    tc.setPosition(p)
                    tc.movePosition(QTextCursor.Right, QTextCursor.KeepAnchor)
                    sel.cursor = tc
                    extras.append(sel)
                break

        self.setExtraSelections(extras)

    def _find_forward(self, pos: int, open_c: str, close_c: str) -> int:
        doc = self.document()
        depth = 0
        for i in range(pos, doc.characterCount()):
            ch = doc.characterAt(i)
            if ch == open_c:
                depth += 1
            elif ch == close_c:
                depth -= 1
                if depth == 0:
                    return i
        return -1

    def _find_backward(self, pos: int, close_c: str, open_c: str) -> int:
        doc = self.document()
        depth = 0
        for i in range(pos, -1, -1):
            ch = doc.characterAt(i)
            if ch == close_c:
                depth += 1
            elif ch == open_c:
                depth -= 1
                if depth == 0:
                    return i
        return -1

    # -- auto-indent & soft-tab -----------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()

        # Tab → 2 spaces
        if key == Qt.Key_Tab and not event.modifiers():
            self.insertPlainText("  ")
            return

        # Enter → auto-indent
        if key in (Qt.Key_Return, Qt.Key_Enter):
            cursor = self.textCursor()
            line = cursor.block().text()
            indent = len(line) - len(line.lstrip())
            base = " " * indent

            # If line ends with { or [ → add extra indent
            stripped = line.rstrip()
            if stripped and stripped[-1] in ("{", "["):
                self.insertPlainText("\n" + base + "  ")
            else:
                self.insertPlainText("\n" + base)
            return

        # Auto-close braces / brackets
        if event.text() in ("{", "["):
            close = _BRACKETS[event.text()]
            cursor = self.textCursor()
            cursor.insertText(event.text() + close)
            cursor.movePosition(QTextCursor.Left)
            self.setTextCursor(cursor)
            return

        # Auto-close string quotes
        if event.text() == '"':
            cursor = self.textCursor()
            # If next char is already a quote, just move past it
            doc = self.document()
            pos = cursor.position()
            if pos < doc.characterCount() and doc.characterAt(pos) == '"':
                cursor.movePosition(QTextCursor.Right)
                self.setTextCursor(cursor)
                return
            cursor.insertText('""')
            cursor.movePosition(QTextCursor.Left)
            self.setTextCursor(cursor)
            return

        # Skip over auto-inserted closing chars
        if event.text() in ("}", "]"):
            cursor = self.textCursor()
            doc = self.document()
            pos = cursor.position()
            if pos < doc.characterCount() and doc.characterAt(pos) == event.text():
                cursor.movePosition(QTextCursor.Right)
                self.setTextCursor(cursor)
                return

        super().keyPressEvent(event)


# ------------------------------------------------------------------
# Public composite widget
# ------------------------------------------------------------------

class JsonEditor(QWidget):
    """Composite JSON editor with toolbar and validation status.

    Signals
    -------
    text_changed:
        Forwarded from the inner text editor.
    """

    text_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        # Toolbar
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(0, 0, 0, 0)

        fmt_btn = QPushButton("Format")
        fmt_btn.setToolTip("Re-indent JSON (Ctrl+Shift+F)")
        fmt_btn.clicked.connect(self.format_json)
        toolbar.addWidget(fmt_btn)

        toolbar.addStretch()

        self._status = QLabel("")
        self._status.setStyleSheet("font-size: 11px;")
        toolbar.addWidget(self._status)
        layout.addLayout(toolbar)

        # Editor
        self._editor = _JsonTextEdit()
        self._highlighter = _JsonHighlighter(self._editor.document())
        self._editor.textChanged.connect(self._on_text_changed)
        layout.addWidget(self._editor)

    # -- public API -----------------------------------------------------

    def text(self) -> str:
        return self._editor.toPlainText()

    def set_text(self, text: str) -> None:
        self._editor.setPlainText(text)

    def parsed_json(self) -> dict | list | None:
        """Parse current text and return the result, or None on error."""
        try:
            return json.loads(self._editor.toPlainText())
        except (json.JSONDecodeError, ValueError):
            return None

    def is_valid(self) -> bool:
        return self.parsed_json() is not None

    def format_json(self) -> None:
        """Re-indent the editor contents."""
        try:
            data = json.loads(self._editor.toPlainText())
            self._editor.setPlainText(
                json.dumps(data, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            pass

    def set_read_only(self, ro: bool) -> None:
        self._editor.setReadOnly(ro)

    # -- internal -------------------------------------------------------

    def _on_text_changed(self) -> None:
        text = self._editor.toPlainText().strip()
        if not text:
            self._status.setText("")
            self._status.setStyleSheet("font-size: 11px;")
        else:
            try:
                json.loads(text)
                self._status.setText("✓ Valid JSON")
                self._status.setStyleSheet(
                    "font-size: 11px; color: green; font-weight: bold;")
            except json.JSONDecodeError as exc:
                self._status.setText(f"✗ {exc.args[0]}")
                self._status.setStyleSheet(
                    "font-size: 11px; color: red;")
        self.text_changed.emit()
