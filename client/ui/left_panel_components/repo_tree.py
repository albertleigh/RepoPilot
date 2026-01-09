"""
Repository Tree Component
Tree view for displaying and managing repositories
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction


class RepoTree(QWidget):
    """Repository tree widget with management controls"""
    
    # Signals
    repo_selected = Signal(str)  # Emits repo name/path
    repo_add_requested = Signal()
    repo_remove_requested = Signal(str)
    repo_refresh_requested = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._load_dummy_data()
    
    def setup_ui(self):
        """Create repository tree UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("📚 Repositories")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)
        
        # Add repo button
        self.add_button = QPushButton("+")
        self.add_button.setMaximumWidth(30)
        self.add_button.setToolTip("Add repository")
        self.add_button.clicked.connect(self.repo_add_requested.emit)
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
        """Load dummy repository data"""
        repos = [
            {"name": "MyProject", "path": "/path/to/myproject", "branches": ["main", "develop"]},
            {"name": "LibraryA", "path": "/path/to/librarya", "branches": ["master"]},
            {"name": "ToolsRepo", "path": "/path/to/tools", "branches": ["main", "feature-x"]},
        ]
        
        for repo in repos:
            repo_item = QTreeWidgetItem(self.tree)
            repo_item.setText(0, f"📁 {repo['name']}")
            repo_item.setData(0, Qt.UserRole, repo['path'])
            
            # Add branches
            for branch in repo['branches']:
                branch_item = QTreeWidgetItem(repo_item)
                branch_item.setText(0, f"  🌿 {branch}")
                branch_item.setData(0, Qt.UserRole, branch)
    
    def _on_item_clicked(self, item, column):
        """Handle item selection"""
        repo_path = item.data(0, Qt.UserRole)
        if repo_path:
            self.repo_selected.emit(repo_path)
    
    def _show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tree.itemAt(position)
        if not item:
            return
        
        menu = QMenu(self)
        
        # Refresh action
        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(lambda: self._refresh_repo(item))
        menu.addAction(refresh_action)
        
        # Remove action
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self._remove_repo(item))
        menu.addAction(remove_action)
        
        menu.exec_(self.tree.viewport().mapToGlobal(position))
    
    def _refresh_repo(self, item):
        """Refresh repository"""
        repo_path = item.data(0, Qt.UserRole)
        if repo_path:
            self.repo_refresh_requested.emit(repo_path)
    
    def _remove_repo(self, item):
        """Remove repository"""
        repo_path = item.data(0, Qt.UserRole)
        if repo_path:
            self.repo_remove_requested.emit(repo_path)
    
    def add_repo(self, name: str, path: str, branches: list = None):
        """Add a repository to the tree"""
        repo_item = QTreeWidgetItem(self.tree)
        repo_item.setText(0, f"📁 {name}")
        repo_item.setData(0, Qt.UserRole, path)
        
        if branches:
            for branch in branches:
                branch_item = QTreeWidgetItem(repo_item)
                branch_item.setText(0, f"  🌿 {branch}")
                branch_item.setData(0, Qt.UserRole, branch)
    
    def clear_repos(self):
        """Clear all repositories"""
        self.tree.clear()
