"""
Debug Panel — browser-dev-tools-style inspector for the running app.

Toggle with **F12**.  Docked at the bottom of the main window as a
slide-up panel with four tabs:

* **Event Log** — live stream of EventBus activity
* **Widget Tree** — Qt widget hierarchy inspector
* **Services** — registered LLMs, repos, engineers, skills
* **Log Tail** — last N lines of the rotating log file
"""
from __future__ import annotations

import logging
from collections import deque
from datetime import datetime
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QTextEdit, QTreeWidget, QTreeWidgetItem, QPushButton,
    QLabel, QSpinBox, QComboBox, QSplitter,
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from core.context import AppContext
from core.events import Event, EventKind
from .event_bridge import QtEventBridge

_MAX_EVENT_LOG = 500
_LOG_TAIL_LINES = 200
_LOG_POLL_MS = 2000


class DebugPanel(QWidget):
    """Bottom-docked debug panel, toggled by the parent window."""

    dock_requested = Signal()    # ask main window to re-dock
    undock_requested = Signal()  # ask main window to pop out

    def __init__(self, ctx: AppContext, main_window: QWidget, parent=None):
        super().__init__(parent)
        self._ctx = ctx
        self._main_window = main_window
        self._events: deque[str] = deque(maxlen=_MAX_EVENT_LOG)

        # Event bridge — listens to ALL events
        self._bridge = QtEventBridge(ctx.event_bus, parent=self)
        self._bridge.event_received.connect(self._on_event)

        self._setup_ui()

        # Log tail timer
        self._log_path = ctx.base_dir / "logs" / "repocode.log"
        self._log_timer = QTimer(self)
        self._log_timer.timeout.connect(self._refresh_log_tail)
        self._log_timer.start(_LOG_POLL_MS)

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 4)

        # Title bar
        title_bar = QHBoxLayout()
        title = QLabel("🛠️ Debug Tools")
        title.setStyleSheet("font-weight:bold; font-size:13px;")
        title_bar.addWidget(title)
        title_bar.addStretch()

        self._popout_btn = QPushButton("⬈")
        self._popout_btn.setFixedSize(24, 24)
        self._popout_btn.setFlat(True)
        self._popout_btn.setToolTip("Pop out / Dock back")
        self._popout_btn.clicked.connect(self._toggle_dock)
        title_bar.addWidget(self._popout_btn)

        self._close_btn = QPushButton("✕")
        self._close_btn.setFixedSize(24, 24)
        self._close_btn.setFlat(True)
        self._close_btn.clicked.connect(self._request_close)
        title_bar.addWidget(self._close_btn)
        layout.addLayout(title_bar)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setTabPosition(QTabWidget.South)
        layout.addWidget(self._tabs)

        self._tabs.addTab(self._build_event_log_tab(), "📡 Event Log")
        self._tabs.addTab(self._build_widget_tree_tab(), "🌳 Widget Tree")
        self._tabs.addTab(self._build_services_tab(), "⚙️ Services")
        self._tabs.addTab(self._build_log_tail_tab(), "📄 Log Tail")
        self._tabs.addTab(self._build_mcp_log_tab(), "🔌 MCP Output")

    # ------------------------------------------------------------------
    # Tab 1: Event Log
    # ------------------------------------------------------------------

    def _build_event_log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        self._event_filter = QComboBox()
        self._event_filter.addItem("All events")
        from core.events import EventKind
        for kind in EventKind:
            self._event_filter.addItem(kind.name, kind)
        self._event_filter.currentIndexChanged.connect(self._apply_event_filter)
        toolbar.addWidget(QLabel("Filter:"))
        toolbar.addWidget(self._event_filter)
        toolbar.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_events)
        toolbar.addWidget(clear_btn)
        lay.addLayout(toolbar)

        self._event_display = QTextEdit()
        self._event_display.setReadOnly(True)
        self._event_display.setFont(QFont("Consolas", 9))
        self._event_display.setLineWrapMode(QTextEdit.NoWrap)
        lay.addWidget(self._event_display)
        return w

    def _on_event(self, event: Event):
        ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
        kind = event.kind.name
        detail = _event_summary(event)
        line = f"[{ts}]  {kind:30s}  {detail}"
        self._events.append(line)
        self._apply_event_filter()

    def _apply_event_filter(self):
        idx = self._event_filter.currentIndex()
        if idx == 0:
            lines = list(self._events)
        else:
            kind_name = self._event_filter.currentText()
            lines = [l for l in self._events if kind_name in l]
        self._event_display.setPlainText("\n".join(lines))
        sb = self._event_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_events(self):
        self._events.clear()
        self._event_display.clear()

    # ------------------------------------------------------------------
    # Tab 2: Widget Tree
    # ------------------------------------------------------------------

    def _build_widget_tree_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh_widget_tree)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        self._widget_count_label = QLabel()
        toolbar.addWidget(self._widget_count_label)
        lay.addLayout(toolbar)

        self._widget_tree = QTreeWidget()
        self._widget_tree.setHeaderLabels(["Widget", "Class", "Visible", "Size"])
        self._widget_tree.setColumnWidth(0, 250)
        self._widget_tree.setColumnWidth(1, 200)
        lay.addWidget(self._widget_tree)
        return w

    def _refresh_widget_tree(self):
        self._widget_tree.clear()
        count = [0]

        def _add(parent_item, widget):
            count[0] += 1
            name = widget.objectName() or "(unnamed)"
            cls = type(widget).__name__
            vis = "✓" if widget.isVisible() else "—"
            sz = f"{widget.width()}×{widget.height()}"
            item = QTreeWidgetItem(parent_item, [name, cls, vis, sz])
            for child in widget.findChildren(QWidget, options=Qt.FindDirectChildrenOnly):
                _add(item, child)

        root = QTreeWidgetItem(self._widget_tree, [
            self._main_window.objectName() or "MainWindow",
            type(self._main_window).__name__,
            "✓",
            f"{self._main_window.width()}×{self._main_window.height()}",
        ])
        for child in self._main_window.findChildren(
            QWidget, options=Qt.FindDirectChildrenOnly
        ):
            _add(root, child)

        self._widget_tree.expandToDepth(1)
        self._widget_count_label.setText(f"{count[0]} widgets")

    # ------------------------------------------------------------------
    # Tab 3: Services
    # ------------------------------------------------------------------

    def _build_services_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Refresh")
        refresh_btn.clicked.connect(self._refresh_services)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()
        lay.addLayout(toolbar)

        self._services_display = QTextEdit()
        self._services_display.setReadOnly(True)
        self._services_display.setFont(QFont("Consolas", 9))
        lay.addWidget(self._services_display)
        return w

    def _refresh_services(self):
        ctx = self._ctx
        lines: list[str] = []

        # LLM Providers
        lines.append("═══ LLM Providers ═══")
        for name in ctx.llm_provider_registry.provider_names():
            lines.append(f"  • {name}")

        # LLM Clients
        lines.append("\n═══ LLM Clients ═══")
        selected = ctx.llm_client_registry.selected_name()
        for name in ctx.llm_client_registry.names():
            marker = " ◀ selected" if name == selected else ""
            lines.append(f"  • {name}{marker}")

        # Repos
        lines.append("\n═══ Repositories ═══")
        for name in ctx.repo_registry.names():
            path = ctx.repo_registry.get(name)
            lines.append(f"  • {name}  →  {path}")

        # Engineers
        lines.append("\n═══ Running Engineers ═══")
        for path, mgr in ctx.engineer_manager_registry.all_managers().items():
            status = "running" if mgr.is_running else "stopped"
            lines.append(f"  • {path}  [{status}]")
        if not ctx.engineer_manager_registry.all_managers():
            lines.append("  (none)")

        # Skills
        lines.append("\n═══ Skills ═══")
        for name in ctx.skill_registry.names():
            lines.append(f"  • {name}")
        if not ctx.skill_registry.names():
            lines.append("  (none)")

        # MCP Servers
        lines.append("\n═══ MCP Servers ═══")
        for name, cfg in ctx.mcp_server_registry.all_servers().items():
            running = ctx.mcp_server_registry.is_running(name)
            status = "running" if running else "stopped"
            lines.append(f"  • {name}  [{status}]  cmd={cfg.command}")
        if not ctx.mcp_server_registry.names():
            lines.append("  (none)")

        self._services_display.setPlainText("\n".join(lines))

    # ------------------------------------------------------------------
    # Tab 4: Log Tail
    # ------------------------------------------------------------------

    def _build_log_tail_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Lines:"))
        self._log_lines_spin = QSpinBox()
        self._log_lines_spin.setRange(50, 2000)
        self._log_lines_spin.setValue(_LOG_TAIL_LINES)
        self._log_lines_spin.setSingleStep(50)
        toolbar.addWidget(self._log_lines_spin)

        refresh_btn = QPushButton("🔄 Refresh Now")
        refresh_btn.clicked.connect(self._refresh_log_tail)
        toolbar.addWidget(refresh_btn)
        toolbar.addStretch()

        self._log_auto = QPushButton("⏸ Pause Auto")
        self._log_auto.setCheckable(True)
        self._log_auto.toggled.connect(self._toggle_log_auto)
        toolbar.addWidget(self._log_auto)
        lay.addLayout(toolbar)

        self._log_display = QTextEdit()
        self._log_display.setReadOnly(True)
        self._log_display.setFont(QFont("Consolas", 9))
        self._log_display.setLineWrapMode(QTextEdit.NoWrap)
        lay.addWidget(self._log_display)
        return w

    def _refresh_log_tail(self):
        if not self.isVisible():
            return
        n = self._log_lines_spin.value()
        try:
            text = self._log_path.read_text(encoding="utf-8", errors="replace")
            lines = text.splitlines()[-n:]
            self._log_display.setPlainText("\n".join(lines))
            sb = self._log_display.verticalScrollBar()
            sb.setValue(sb.maximum())
        except FileNotFoundError:
            self._log_display.setPlainText("(log file not found)")

    def _toggle_log_auto(self, paused: bool):
        if paused:
            self._log_timer.stop()
            self._log_auto.setText("▶ Resume Auto")
        else:
            self._log_timer.start(_LOG_POLL_MS)
            self._log_auto.setText("⏸ Pause Auto")

    # ------------------------------------------------------------------
    # Tab 5: MCP Output
    # ------------------------------------------------------------------

    def _build_mcp_log_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(2, 2, 2, 2)

        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("Server:"))

        self._mcp_server_combo = QComboBox()
        self._mcp_server_combo.setMinimumWidth(180)
        self._mcp_server_combo.currentTextChanged.connect(
            self._on_mcp_server_changed)
        toolbar.addWidget(self._mcp_server_combo)

        refresh_btn = QPushButton("🔄")
        refresh_btn.setToolTip("Refresh server list")
        refresh_btn.clicked.connect(self._refresh_mcp_server_list)
        toolbar.addWidget(refresh_btn)

        toolbar.addStretch()

        clear_btn = QPushButton("Clear")
        clear_btn.clicked.connect(self._clear_mcp_log)
        toolbar.addWidget(clear_btn)
        lay.addLayout(toolbar)

        self._mcp_log_display = QTextEdit()
        self._mcp_log_display.setReadOnly(True)
        self._mcp_log_display.setFont(QFont("Consolas", 9))
        self._mcp_log_display.setLineWrapMode(QTextEdit.NoWrap)
        lay.addWidget(self._mcp_log_display)

        # Subscribe to MCP output events
        self._bridge.on(
            {EventKind.MCP_SERVER_OUTPUT, EventKind.MCP_SERVER_ERROR,
             EventKind.MCP_SERVER_STARTED, EventKind.MCP_SERVER_STOPPED},
            self._on_mcp_event)

        # Initial population
        self._refresh_mcp_server_list()
        return w

    def _refresh_mcp_server_list(self):
        """Rebuild the server dropdown from the registry."""
        registry = self._ctx.mcp_server_registry
        current = self._mcp_server_combo.currentText()
        self._mcp_server_combo.blockSignals(True)
        self._mcp_server_combo.clear()
        self._mcp_server_combo.addItem("(all)")
        for name in registry.names():
            running = registry.is_running(name)
            label = f"🟢 {name}" if running else f"⚪ {name}"
            self._mcp_server_combo.addItem(label, name)
        # Restore previous selection if still present
        idx = self._mcp_server_combo.findText(current)
        if idx >= 0:
            self._mcp_server_combo.setCurrentIndex(idx)
        self._mcp_server_combo.blockSignals(False)
        self._on_mcp_server_changed()

    def _on_mcp_server_changed(self):
        """Populate the display with buffered output for the selected server."""
        registry = self._ctx.mcp_server_registry
        name = self._mcp_server_combo.currentData()
        if name:
            lines = registry.get_output(name)
        else:
            # "(all)" — aggregate all servers
            lines = []
            for sname in registry.names():
                for line in registry.get_output(sname):
                    lines.append(f"[{sname}] {line}")
        self._mcp_log_display.setPlainText("\n".join(lines))
        sb = self._mcp_log_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_mcp_event(self, event: Event):
        """Handle live MCP events."""
        name = getattr(event, "name", "")
        kind = event.kind

        if kind in (EventKind.MCP_SERVER_STARTED,
                    EventKind.MCP_SERVER_STOPPED):
            self._refresh_mcp_server_list()
            return

        # Output or error line
        text = getattr(event, "text", "") or getattr(event, "error", "")
        selected_name = self._mcp_server_combo.currentData()
        if selected_name and selected_name != name:
            return  # filtered out

        prefix = f"[{name}] " if not selected_name else ""
        self._mcp_log_display.append(f"{prefix}{text}")
        sb = self._mcp_log_display.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _clear_mcp_log(self):
        self._mcp_log_display.clear()

    # ------------------------------------------------------------------
    # Close callback
    # ------------------------------------------------------------------

    def _request_close(self):
        self.hide()

    def _toggle_dock(self):
        self.undock_requested.emit()

    def set_popout_icon(self, is_floating: bool):
        """Update the pop-out button icon based on dock state."""
        self._popout_btn.setText("⬋" if is_floating else "⬈")
        self._popout_btn.setToolTip(
            "Dock back" if is_floating else "Pop out to window"
        )
        self._close_btn.setVisible(not is_floating)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def cleanup(self):
        self._log_timer.stop()
        self._bridge.close()


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _event_summary(event: Event) -> str:
    """One-line summary of an event's payload."""
    parts = []
    for attr in ("workdir", "text", "tool_name", "error", "output"):
        val = getattr(event, attr, None)
        if val is not None:
            s = str(val)
            if len(s) > 80:
                s = s[:77] + "..."
            parts.append(f"{attr}={s}")
    return "  ".join(parts) if parts else ""
