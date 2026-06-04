"""
Create LLM Client Dialog
Qt dialog for configuring and registering a new LLM client.
"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QPushButton,
    QMessageBox, QGroupBox,
)
from PySide6.QtCore import Signal, Qt

from core.context import AppContext


class CreateLLMDialog(QDialog):
    """Dialog for creating a new LLM client configuration."""

    llm_created = Signal(str, str)  # (display_name, provider_name)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add LLM Client")
        self.setMinimumWidth(520)
        self._field_widgets: dict[str, QLineEdit | QComboBox] = {}
        self._provider_reg = ctx.llm_provider_registry
        self._client_reg = ctx.llm_client_registry
        self._setup_ui()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # -- Display name --
        name_group = QGroupBox("Client Name")
        name_layout = QFormLayout(name_group)
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("e.g. My Claude on Azure")
        name_layout.addRow("Display Name:", self.name_edit)
        layout.addWidget(name_group)

        # -- Provider selector --
        provider_group = QGroupBox("Provider")
        provider_layout = QFormLayout(provider_group)
        self.provider_combo = QComboBox()
        self.provider_combo.addItems(self._provider_reg.provider_names())
        self.provider_combo.currentTextChanged.connect(self._on_provider_changed)
        provider_layout.addRow("Provider:", self.provider_combo)
        layout.addWidget(provider_group)

        # -- Dynamic form area --
        self.form_group = QGroupBox("Configuration")
        self.form_layout = QFormLayout(self.form_group)
        layout.addWidget(self.form_group)

        # -- Buttons --
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self.test_button = QPushButton("Test Connection")
        self.test_button.clicked.connect(self._on_test)
        btn_layout.addWidget(self.test_button)

        self.create_button = QPushButton("Create")
        self.create_button.setDefault(True)
        self.create_button.clicked.connect(self._on_create)
        btn_layout.addWidget(self.create_button)

        cancel_button = QPushButton("Cancel")
        cancel_button.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_button)

        layout.addLayout(btn_layout)

        # Build initial form
        self._on_provider_changed(self.provider_combo.currentText())

    # ------------------------------------------------------------------
    # Dynamic form
    # ------------------------------------------------------------------

    def _on_provider_changed(self, provider: str):
        """Rebuild the configuration form for the selected provider."""
        # Auto-populate display name
        self.name_edit.setText(self._client_reg.next_display_name(provider))

        # Clear existing fields
        self._field_widgets.clear()
        while self.form_layout.rowCount():
            self.form_layout.removeRow(0)

        cls = self._provider_reg.get(provider)
        fields = cls.FIELDS if cls else []
        for field in fields:
            if field.get("type") == "action":
                btn = QPushButton(field.get("label", field["key"]))
                btn.clicked.connect(
                    lambda _checked, p=provider, k=field["key"]: self._on_field_action(p, k)
                )
                self.form_layout.addRow("", btn)
                continue
            label_text = field["label"]
            if field.get("required"):
                label_text += " *"
            if field.get("type") == "choices":
                combo = QComboBox()
                combo.setEditable(True)
                choices = cls.get_field_choices(field["key"])
                if choices:
                    combo.addItems(choices)
                default = field.get("default", "")
                if default:
                    idx = combo.findText(default)
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        combo.setCurrentText(default)
                combo.lineEdit().setPlaceholderText(field.get("placeholder", ""))
                self.form_layout.addRow(label_text + ":", combo)
                self._field_widgets[field["key"]] = combo
                continue
            edit = QLineEdit()
            edit.setPlaceholderText(field.get("placeholder", ""))
            edit.setText(field.get("default", ""))
            if field.get("secret"):
                edit.setEchoMode(QLineEdit.Password)
            self.form_layout.addRow(label_text + ":", edit)
            self._field_widgets[field["key"]] = edit

    def _on_field_action(self, provider: str, key: str):
        """Dispatch action-type field button click to the provider class."""
        cls = self._provider_reg.get(provider)
        if cls is None:
            return
        result = cls.on_field_action(key)
        status = result.get("status", "")
        message = result.get("message", "")
        if status == "error":
            QMessageBox.critical(self, "Error", message)
        elif message:
            QMessageBox.information(self, "GitHub Login", message)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _collect_values(self) -> dict[str, str] | None:
        """Validate required fields and return a dict of values,
        or None on validation failure."""
        provider = self.provider_combo.currentText()
        cls = self._provider_reg.get(provider)
        fields = cls.FIELDS if cls else []
        values: dict[str, str] = {}

        missing = []
        for field in fields:
            if field.get("type") == "action":
                continue
            key = field["key"]
            widget = self._field_widgets[key]
            if isinstance(widget, QComboBox):
                val = widget.currentText().strip()
            else:
                val = widget.text().strip()
            if field.get("required") and not val:
                missing.append(field["label"])
            values[key] = val

        display_name = self.name_edit.text().strip()
        if not display_name:
            missing.append("Display Name")

        if missing:
            QMessageBox.warning(
                self, "Missing Fields",
                "Please fill in the following required fields:\n\n• "
                + "\n• ".join(missing),
            )
            return None

        values["_display_name"] = display_name
        values["_provider"] = provider
        return values

    # ------------------------------------------------------------------
    # Client factory
    # ------------------------------------------------------------------

    def _build_client(self, provider: str, values: dict):
        """Instantiate the correct LLMClient for *provider*."""
        cls = self._provider_reg.get(provider)
        if cls is None:
            return None
        kwargs = {
            f["key"]: values[f["key"]]
            for f in cls.FIELDS
            if f.get("type") != "action"
        }
        return cls(**kwargs)

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def _on_test(self):
        values = self._collect_values()
        if values is None:
            return

        provider = values["_provider"]
        client = self._build_client(provider, values)
        if client is None:
            QMessageBox.critical(self, "Error", f"Unknown provider: {provider}")
            return

        self.test_button.setEnabled(False)
        self.test_button.setText("Testing…")
        try:
            if client.is_available():
                QMessageBox.information(self, "Success", "Connection test passed!")
            else:
                QMessageBox.warning(self, "Failed",
                                    "Connection test failed. Check your credentials and URL.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Connection error:\n{exc}")
        finally:
            self.test_button.setEnabled(True)
            self.test_button.setText("Test Connection")

    def _on_create(self):
        values = self._collect_values()
        if values is None:
            return

        provider = values["_provider"]
        display_name = values["_display_name"]
        client = self._build_client(provider, values)
        if client is None:
            QMessageBox.critical(self, "Error", f"Unknown provider: {provider}")
            return

        # Register with the client registry
        registry = self._client_reg

        if registry.get(display_name) is not None:
            QMessageBox.warning(
                self, "Duplicate",
                f"An LLM client named '{display_name}' already exists.\n"
                "Please choose a different name.",
            )
            return

        cls = self._provider_reg.get(provider)
        registry.register(display_name, client, config={
            "provider": provider,
            "fields": {
                f["key"]: values[f["key"]]
                for f in cls.FIELDS
                if f.get("type") != "action"
            },
        })
        self.llm_created.emit(display_name, provider)
        self.accept()
