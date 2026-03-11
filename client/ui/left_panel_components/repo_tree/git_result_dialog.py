"""
Modal dialog that displays a git command while it runs, then shows the result.

Usage::

    dialog = GitCommandDialog("git checkout main", parent=self)
    dialog.run(lambda: git_utils.checkout_branch(path, "main"))
    # dialog is modal – blocks interaction, shows spinner, then result
"""
from __future__ import annotations

from typing import Callable

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout,
    QProgressBar,
)
from PySide6.QtCore import Qt, QTimer

from core.git_utils import GitResult


class GitCommandDialog(QDialog):
    """Modal dialog: shows the command being run, executes it, then shows the outcome."""

    def __init__(self, command_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Git")
        self.setMinimumWidth(480)
        self.setModal(True)
        self._build_ui(command_label)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self, command_label: str):
        layout = QVBoxLayout(self)

        # Status (initially "running")
        self._status_label = QLabel("⏳ Running…")
        self._status_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        layout.addWidget(self._status_label)

        # Command echo
        self._cmd_label = QLabel(f"<code>$ {command_label}</code>")
        self._cmd_label.setWordWrap(True)
        self._cmd_label.setTextFormat(Qt.RichText)
        self._cmd_label.setStyleSheet("color: #888;")
        layout.addWidget(self._cmd_label)

        # Progress bar (indeterminate, visible while running)
        self._progress = QProgressBar()
        self._progress.setRange(0, 0)  # indeterminate
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(4)
        layout.addWidget(self._progress)

        # Output area (hidden until result arrives)
        self._output_edit = QTextEdit()
        self._output_edit.setReadOnly(True)
        self._output_edit.setMaximumHeight(200)
        self._output_edit.hide()
        layout.addWidget(self._output_edit)

        # OK button (disabled while running)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setDefault(True)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self._ok_btn)
        layout.addLayout(btn_layout)

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def run(self, fn: Callable[[], GitResult]):
        """Show the dialog, execute *fn* after the event loop paints, then display the result."""
        self._fn = fn
        self.show()
        # Give the event loop enough time to paint the loading state before blocking
        QTimer.singleShot(50, self._execute)
        self.exec()

    def _execute(self):
        result = self._fn()
        self._populate_result(result)

    def _populate_result(self, result: GitResult):
        if result.success:
            self._status_label.setText("✅ Command succeeded")
            self.setWindowTitle("Git — Success")
        else:
            self._status_label.setText("❌ Command failed")
            self.setWindowTitle("Git — Failed")

        self._progress.hide()

        output = result.output
        if output:
            self._output_edit.setPlainText(output)
            self._output_edit.show()

        self._ok_btn.setEnabled(True)
        self._ok_btn.setFocus()
