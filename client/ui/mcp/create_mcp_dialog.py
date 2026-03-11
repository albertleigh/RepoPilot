"""
Create MCP Server Dialog – add a new MCP server configuration.

Presents a full JSON editor pre-filled with a template.  The user edits
the JSON directly and clicks OK to register the server.
"""
from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QDialogButtonBox, QMessageBox,
)
from PySide6.QtCore import Signal

from core.mcp.registry import McpServerConfig, McpServerRegistry
from .json_editor import JsonEditor

_TEMPLATE = {
    "command": "npx",
    "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
    "env": {},
    "enabled": True,
}


class CreateMcpDialog(QDialog):
    """Dialog to create a new MCP server entry."""

    mcp_created = Signal(str)  # emits server name

    def __init__(self, registry: McpServerRegistry, parent=None):
        super().__init__(parent)
        self._registry = registry
        self.setWindowTitle("Add MCP Server")
        self.setMinimumSize(540, 440)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Server name (the only field outside the JSON)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        self._name_edit.setPlaceholderText("e.g. Filesystem Server")
        name_row.addWidget(self._name_edit)
        layout.addLayout(name_row)

        # JSON editor
        layout.addWidget(QLabel("Server configuration:"))
        self._editor = JsonEditor()
        self._editor.set_text(
            json.dumps(_TEMPLATE, indent=2, ensure_ascii=False))
        layout.addWidget(self._editor)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_accept)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_accept(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            QMessageBox.warning(self, "Validation", "Name is required.")
            return
        if name in self._registry.names():
            QMessageBox.warning(self, "Duplicate",
                                f"A server named '{name}' already exists.")
            return

        data = self._editor.parsed_json()
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid JSON",
                                "Configuration must be a valid JSON object.")
            return

        config = McpServerConfig.from_dict(data)
        if not config.command:
            QMessageBox.warning(self, "Validation",
                                '"command" field is required.')
            return

        self._registry.register(name, config)
        self.mcp_created.emit(name)
        self.accept()
