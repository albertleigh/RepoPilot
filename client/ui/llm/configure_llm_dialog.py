"""
Configure LLM Client Dialog
Qt dialog for viewing / editing an existing LLM client's configuration.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QMessageBox, QGroupBox,
)
from PySide6.QtCore import Signal

from core.context import AppContext


class ConfigureLLMDialog(QDialog):
    """Dialog for editing an existing LLM client configuration.

    The provider type is shown but cannot be changed.
    """

    llm_updated = Signal(str)  # display_name

    def __init__(self, ctx: AppContext, llm_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Configure – {llm_name}")
        self.setMinimumWidth(520)

        self._llm_name = llm_name
        self._field_widgets: dict[str, QLineEdit] = {}
        self._provider_reg = ctx.llm_provider_registry
        self._client_reg = ctx.llm_client_registry

        self._config = self._client_reg.get_config(llm_name) or {}
        self._provider = self._config.get("provider", "")
        self._fields_data = self._config.get("fields", {})

        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # -- Display name (read-only) --
        name_group = QGroupBox("Client Name")
        name_layout = QFormLayout(name_group)
        self.name_label = QLabel(self._llm_name)
        name_layout.addRow("Display Name:", self.name_label)
        layout.addWidget(name_group)

        # -- Provider (read-only combo) --
        provider_group = QGroupBox("Provider")
        provider_layout = QFormLayout(provider_group)
        self.provider_combo = QComboBox()
        self.provider_combo.addItem(self._provider)
        self.provider_combo.setEnabled(False)
        provider_layout.addRow("Provider:", self.provider_combo)
        layout.addWidget(provider_group)

        # -- Dynamic form area --
        self.form_group = QGroupBox("Configuration")
        self.form_layout = QFormLayout(self.form_group)
        layout.addWidget(self.form_group)
        self._build_fields()

        # -- Buttons --
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._on_test)
        btn_layout.addWidget(self.test_button)

        self.save_button = QPushButton("Save")
        self.save_button.setDefault(True)
        self.save_button.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_button)

        layout.addLayout(btn_layout)

    def _build_fields(self):
        """Populate the form with current field values."""
        cls = self._provider_reg.get(self._provider)
        fields = cls.FIELDS if cls else []
        for field in fields:
            key = field["key"]
            edit = QLineEdit()
            edit.setPlaceholderText(field.get("placeholder", ""))
            edit.setText(self._fields_data.get(key, field.get("default", "")))
            if field.get("secret"):
                edit.setEchoMode(QLineEdit.Password)
            label_text = field["label"]
            if field.get("required"):
                label_text += " *"
            self.form_layout.addRow(label_text + ":", edit)
            self._field_widgets[key] = edit

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _collect_values(self) -> dict[str, str] | None:
        cls = self._provider_reg.get(self._provider)
        fields = cls.FIELDS if cls else []
        values: dict[str, str] = {}
        missing = []
        for field in fields:
            key = field["key"]
            val = self._field_widgets[key].text().strip()
            if field.get("required") and not val:
                missing.append(field["label"])
            values[key] = val
        if missing:
            QMessageBox.warning(
                self, "Missing Fields",
                "Please fill in the following required fields:\n\n• "
                + "\n• ".join(missing),
            )
            return None
        return values

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------

    def _build_client(self, values: dict):
        cls = self._provider_reg.get(self._provider)
        if cls is None:
            return None
        kwargs = {f["key"]: values[f["key"]] for f in cls.FIELDS}
        return cls(**kwargs)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_test(self):
        values = self._collect_values()
        if values is None:
            return
        client = self._build_client(values)
        if client is None:
            QMessageBox.critical(self, "Error",
                                 f"Unknown provider: {self._provider}")
            return
        self.test_button.setEnabled(False)
        self.test_button.setText("Testing…")
        try:
            if client.is_available():
                QMessageBox.information(self, "Success",
                                        "Connection test passed!")
            else:
                QMessageBox.warning(self, "Failed",
                                    "Connection test failed. "
                                    "Check your credentials and URL.")
        except Exception as exc:
            QMessageBox.critical(self, "Error",
                                 f"Connection error:\n{exc}")
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("Test Connection")

    def _on_save(self):
        values = self._collect_values()
        if values is None:
            return
        client = self._build_client(values)
        if client is None:
            QMessageBox.critical(self, "Error",
                                 f"Unknown provider: {self._provider}")
            return

        cls = self._provider_reg.get(self._provider)
        self._client_reg.update(self._llm_name, client, config={
            "provider": self._provider,
            "fields": {f["key"]: values[f["key"]] for f in cls.FIELDS},
        })
        self.llm_updated.emit(self._llm_name)
        self.accept()
