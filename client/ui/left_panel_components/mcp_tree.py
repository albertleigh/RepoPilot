"""
MCP Tree Component
Tree view for displaying and managing MCP (Model Context Protocol) servers.
Backed by ``McpServerRegistry`` for persistence and process management.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QAction

from core.mcp.registry import McpServerRegistry


_STATUS_POLL_MS = 3000  # refresh running indicators every 3 s


class MCPTree(QWidget):
    """MCP servers tree widget with management controls.

    Mirrors the pattern of ``LLMTree`` but adds process-lifecycle
    actions (start / stop / start-all) and a periodic status poll.
    """

    # Signals
    mcp_selected = Signal(str)          # Emits MCP server name
    mcp_add_requested = Signal()
    mcp_remove_requested = Signal(str)
    mcp_configure_requested = Signal(str)
    mcp_start_requested = Signal(str)
    mcp_stop_requested = Signal(str)
    mcp_start_all_requested = Signal()

    def __init__(self, mcp_registry: McpServerRegistry,
                 show_header: bool = True, parent=None):
        super().__init__(parent)
        self._registry = mcp_registry
        self.show_header = show_header
        self._setup_ui()
        self.refresh()

        # Periodic status refresh
        self._poll_timer = QTimer(self)
        self._poll_timer.timeout.connect(self._refresh_status_icons)
        self._poll_timer.start(_STATUS_POLL_MS)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if self.show_header:
            header_layout = QHBoxLayout()
            header_label = QLabel("🔌 MCP Servers")
            header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
            header_layout.addWidget(header_label)

            header_layout.addStretch()

            # Start-all button
            self.start_all_button = QPushButton("▶ All")
            self.start_all_button.setMaximumWidth(50)
            self.start_all_button.setToolTip("Start all enabled servers")
            self.start_all_button.clicked.connect(
                self.mcp_start_all_requested.emit)
            header_layout.addWidget(self.start_all_button)

            # Add button
            self.add_button = QPushButton("+")
            self.add_button.setMaximumWidth(30)
            self.add_button.setToolTip("Add MCP server")
            self.add_button.clicked.connect(self.mcp_add_requested.emit)
            header_layout.addWidget(self.add_button)

            layout.addLayout(header_layout)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

    # ------------------------------------------------------------------
    # Refresh / rebuild from registry
    # ------------------------------------------------------------------

    def refresh(self):
        """Rebuild the tree from the McpServerRegistry."""
        self.tree.clear()
        for name, cfg in self._registry.all_servers().items():
            running = self._registry.is_running(name)
            self._add_server_item(name, cfg.command, running)

    def _add_server_item(self, name: str, command: str,
                         running: bool = False):
        item = QTreeWidgetItem(self.tree)
        icon = "🟢" if running else "⚪"
        item.setText(0, f"{icon} {name}")
        item.setData(0, Qt.UserRole, name)

        cmd_item = QTreeWidgetItem(item)
        cmd_item.setText(0, f"  Cmd: {command}")

        status_item = QTreeWidgetItem(item)
        status_item.setText(0, f"  Status: {'running' if running else 'stopped'}")

    def _refresh_status_icons(self):
        """Update the status icons of every top-level item without
        rebuilding the entire tree."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            name = item.data(0, Qt.UserRole)
            if name is None:
                continue
            running = self._registry.is_running(name)
            icon = "🟢" if running else "⚪"
            item.setText(0, f"{icon} {name}")
            # Update status child
            for j in range(item.childCount()):
                child = item.child(j)
                text = child.text(0)
                if text.strip().startswith("Status:"):
                    child.setText(
                        0, f"  Status: {'running' if running else 'stopped'}")

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item, column):
        mcp_name = item.data(0, Qt.UserRole)
        if mcp_name:
            self.mcp_selected.emit(mcp_name)

    def _show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item or not item.data(0, Qt.UserRole):
            return

        name = item.data(0, Qt.UserRole)
        running = self._registry.is_running(name)
        menu = QMenu(self)

        if running:
            stop_action = QAction("⏹ Stop", self)
            stop_action.triggered.connect(lambda: self._stop_server(name))
            menu.addAction(stop_action)
        else:
            start_action = QAction("▶ Start", self)
            start_action.triggered.connect(lambda: self._start_server(name))
            menu.addAction(start_action)

        menu.addSeparator()

        config_action = QAction("Configure…", self)
        config_action.triggered.connect(
            lambda: self.mcp_configure_requested.emit(name))
        menu.addAction(config_action)

        menu.addSeparator()

        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(
            lambda: self.mcp_remove_requested.emit(name))
        menu.addAction(remove_action)

        menu.exec_(self.tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Start / stop helpers (emit signals so parent can optionally
    # intercept, but also talk directly to the registry).
    # ------------------------------------------------------------------

    def _start_server(self, name: str):
        self._registry.start(name)
        self.mcp_start_requested.emit(name)
        self._refresh_status_icons()

    def _stop_server(self, name: str):
        self._registry.stop(name)
        self.mcp_stop_requested.emit(name)
        self._refresh_status_icons()

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    def remove_mcp(self, name: str):
        """Remove an MCP server item from the tree by name."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item and item.data(0, Qt.UserRole) == name:
                self.tree.takeTopLevelItem(i)
                return

    def clear_mcps(self):
        self.tree.clear()

    def cleanup(self):
        """Stop the status-poll timer."""
        self._poll_timer.stop()
