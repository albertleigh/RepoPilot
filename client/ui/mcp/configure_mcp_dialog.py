"""
Configure MCP Server Dialog – edit an existing server as raw JSON.

Opens the ``JsonEditor`` widget pre-filled with the server's config.
The user can freely edit the JSON and save it back through the registry.
"""
from __future__ import annotations

import json

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout,
    QLabel, QDialogButtonBox, QMessageBox,
)
from PySide6.QtCore import Signal

from core.mcp.registry import McpServerConfig, McpServerRegistry
from .json_editor import JsonEditor


class ConfigureMcpDialog(QDialog):
    """Editable-JSON dialog for an MCP server configuration."""

    mcp_updated = Signal(str)  # emits server name

    def __init__(self, name: str, registry: McpServerRegistry, parent=None):
        super().__init__(parent)
        self._name = name
        self._registry = registry
        self.setWindowTitle(f"Configure – {name}")
        self.setMinimumSize(540, 440)
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)

        header = QLabel(f"Editing configuration for <b>{self._name}</b>")
        layout.addWidget(header)

        self._editor = JsonEditor()
        cfg = self._registry.get_config_dict(self._name)
        self._editor.set_text(
            json.dumps(cfg, indent=2, ensure_ascii=False) if cfg else "{}")
        layout.addWidget(self._editor)

        btn_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    def _on_save(self) -> None:
        data = self._editor.parsed_json()
        if not isinstance(data, dict):
            QMessageBox.warning(self, "Invalid JSON",
                                "Configuration must be a valid JSON object.")
            return

        config = McpServerConfig.from_dict(data)
        self._registry.update(self._name, config)
        self.mcp_updated.emit(self._name)
        self.accept()
