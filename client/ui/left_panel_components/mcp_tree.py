"""
MCP Tree Component
Tree view for displaying and managing MCP (Model Context Protocol) servers
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction


class MCPTree(QWidget):
    """MCP servers tree widget with management controls"""
    
    # Signals
    mcp_selected = Signal(str)  # Emits MCP server name
    mcp_add_requested = Signal()
    mcp_remove_requested = Signal(str)
    mcp_configure_requested = Signal(str)
    
    def __init__(self, show_header: bool = True, parent=None):
        super().__init__(parent)
        self.show_header = show_header
        self.setup_ui()
        self._load_dummy_data()
    
    def setup_ui(self):
        """Create MCP servers tree UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Optional header
        if self.show_header:
            header_layout = QHBoxLayout()
            header_label = QLabel("🔌 MCP Servers")
            header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
            header_layout.addWidget(header_label)
            
            # Add MCP button
            self.add_button = QPushButton("+")
            self.add_button.setMaximumWidth(30)
            self.add_button.setToolTip("Add MCP server")
            self.add_button.clicked.connect(self.mcp_add_requested.emit)
            header_layout.addWidget(self.add_button)
            
            layout.addLayout(header_layout)
        
        # Tree widget
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)
    
    def _load_dummy_data(self):
        """Load dummy MCP server data"""
        mcp_servers = [
            {"name": "Filesystem Server", "type": "Built-in", "status": "running"},
            {"name": "Git Server", "type": "Built-in", "status": "running"},
            {"name": "Docker Server", "type": "Custom", "status": "stopped"},
            {"name": "Database Server", "type": "Custom", "status": "running"},
        ]
        
        for server in mcp_servers:
            server_item = QTreeWidgetItem(self.tree)
            status_icon = "🟢" if server['status'] == "running" else "🔴"
            server_item.setText(0, f"{status_icon} {server['name']}")
            server_item.setData(0, Qt.UserRole, server['name'])
            
            # Add details as child items
            type_item = QTreeWidgetItem(server_item)
            type_item.setText(0, f"  Type: {server['type']}")
            
            status_item = QTreeWidgetItem(server_item)
            status_item.setText(0, f"  Status: {server['status']}")
    
    def _on_item_clicked(self, item, column):
        """Handle item selection"""
        mcp_name = item.data(0, Qt.UserRole)
        if mcp_name:
            self.mcp_selected.emit(mcp_name)
    
    def _show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tree.itemAt(position)
        if not item or not item.data(0, Qt.UserRole):
            return
        
        menu = QMenu(self)
        
        # Configure action
        config_action = QAction("Configure", self)
        config_action.triggered.connect(lambda: self._configure_mcp(item))
        menu.addAction(config_action)
        
        menu.addSeparator()
        
        # Remove action
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self._remove_mcp(item))
        menu.addAction(remove_action)
        
        menu.exec_(self.tree.viewport().mapToGlobal(position))
    
    def _configure_mcp(self, item):
        """Configure MCP server"""
        mcp_name = item.data(0, Qt.UserRole)
        if mcp_name:
            self.mcp_configure_requested.emit(mcp_name)
    
    def _remove_mcp(self, item):
        """Remove MCP server"""
        mcp_name = item.data(0, Qt.UserRole)
        if mcp_name:
            self.mcp_remove_requested.emit(mcp_name)
    
    def add_mcp(self, name: str, server_type: str, status: str = "running"):
        """Add an MCP server to the tree"""
        server_item = QTreeWidgetItem(self.tree)
        status_icon = "🟢" if status == "running" else "🔴"
        server_item.setText(0, f"{status_icon} {name}")
        server_item.setData(0, Qt.UserRole, name)
        
        # Add details
        type_item = QTreeWidgetItem(server_item)
        type_item.setText(0, f"  Type: {server_type}")
        
        status_item = QTreeWidgetItem(server_item)
        status_item.setText(0, f"  Status: {status}")
    
    def clear_mcps(self):
        """Clear all MCP servers"""
        self.tree.clear()
