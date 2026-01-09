"""
LLM Clients Tree Component
Tree view for displaying and managing LLM clients/providers
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction


class LLMTree(QWidget):
    """LLM clients tree widget with management controls"""
    
    # Signals
    llm_selected = Signal(str)  # Emits LLM client name
    llm_add_requested = Signal()
    llm_remove_requested = Signal(str)
    llm_configure_requested = Signal(str)
    
    def __init__(self, show_header: bool = True, parent=None):
        super().__init__(parent)
        self.show_header = show_header
        self.setup_ui()
        self._load_dummy_data()
    
    def setup_ui(self):
        """Create LLM clients tree UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Optional header
        if self.show_header:
            header_layout = QHBoxLayout()
            header_label = QLabel("🤖 LLM Clients")
            header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
            header_layout.addWidget(header_label)
            
            # Add LLM button
            self.add_button = QPushButton("+")
            self.add_button.setMaximumWidth(30)
            self.add_button.setToolTip("Add LLM client")
            self.add_button.clicked.connect(self.llm_add_requested.emit)
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
        """Load dummy LLM client data"""
        llm_clients = [
            {"name": "OpenAI GPT-4", "type": "OpenAI", "status": "active"},
            {"name": "Claude 3.5 Sonnet", "type": "Anthropic", "status": "active"},
            {"name": "Local LLaMA", "type": "Local", "status": "inactive"},
            {"name": "Gemini Pro", "type": "Google", "status": "active"},
        ]
        
        for client in llm_clients:
            client_item = QTreeWidgetItem(self.tree)
            status_icon = "🟢" if client['status'] == "active" else "🔴"
            client_item.setText(0, f"{status_icon} {client['name']}")
            client_item.setData(0, Qt.UserRole, client['name'])
            
            # Add details as child items
            type_item = QTreeWidgetItem(client_item)
            type_item.setText(0, f"  Type: {client['type']}")
            
            status_item = QTreeWidgetItem(client_item)
            status_item.setText(0, f"  Status: {client['status']}")
    
    def _on_item_clicked(self, item, column):
        """Handle item selection"""
        llm_name = item.data(0, Qt.UserRole)
        if llm_name:
            self.llm_selected.emit(llm_name)
    
    def _show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tree.itemAt(position)
        if not item or not item.data(0, Qt.UserRole):
            return
        
        menu = QMenu(self)
        
        # Configure action
        config_action = QAction("Configure", self)
        config_action.triggered.connect(lambda: self._configure_llm(item))
        menu.addAction(config_action)
        
        menu.addSeparator()
        
        # Remove action
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self._remove_llm(item))
        menu.addAction(remove_action)
        
        menu.exec_(self.tree.viewport().mapToGlobal(position))
    
    def _configure_llm(self, item):
        """Configure LLM client"""
        llm_name = item.data(0, Qt.UserRole)
        if llm_name:
            self.llm_configure_requested.emit(llm_name)
    
    def _remove_llm(self, item):
        """Remove LLM client"""
        llm_name = item.data(0, Qt.UserRole)
        if llm_name:
            self.llm_remove_requested.emit(llm_name)
    
    def add_llm(self, name: str, llm_type: str, status: str = "active"):
        """Add an LLM client to the tree"""
        client_item = QTreeWidgetItem(self.tree)
        status_icon = "🟢" if status == "active" else "🔴"
        client_item.setText(0, f"{status_icon} {name}")
        client_item.setData(0, Qt.UserRole, name)
        
        # Add details
        type_item = QTreeWidgetItem(client_item)
        type_item.setText(0, f"  Type: {llm_type}")
        
        status_item = QTreeWidgetItem(client_item)
        status_item.setText(0, f"  Status: {status}")
    
    def clear_llms(self):
        """Clear all LLM clients"""
        self.tree.clear()
