"""
Skill Tree Component
Tree view for displaying and managing skills/capabilities
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction


class SkillTree(QWidget):
    """Skill tree widget with management controls"""
    
    # Signals
    skill_selected = Signal(str)  # Emits skill name
    skill_add_requested = Signal()
    skill_remove_requested = Signal(str)
    skill_configure_requested = Signal(str)
    
    def __init__(self, show_header: bool = True, parent=None):
        super().__init__(parent)
        self.show_header = show_header
        self.setup_ui()
        self._load_dummy_data()
    
    def setup_ui(self):
        """Create skill tree UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Optional header
        if self.show_header:
            header_layout = QHBoxLayout()
            header_label = QLabel("⚡ Skills")
            header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
            header_layout.addWidget(header_label)
            
            # Add skill button
            self.add_button = QPushButton("+")
            self.add_button.setMaximumWidth(30)
            self.add_button.setToolTip("Add skill")
            self.add_button.clicked.connect(self.skill_add_requested.emit)
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
        """Load dummy skill data"""
        skills = [
            {"name": "Code Analysis", "category": "Analysis", "status": "enabled"},
            {"name": "Documentation Generator", "category": "Generation", "status": "enabled"},
            {"name": "Test Generator", "category": "Testing", "status": "disabled"},
            {"name": "Refactoring Assistant", "category": "Code Quality", "status": "enabled"},
        ]
        
        for skill in skills:
            skill_item = QTreeWidgetItem(self.tree)
            status_icon = "✓" if skill['status'] == "enabled" else "✗"
            skill_item.setText(0, f"{status_icon} {skill['name']}")
            skill_item.setData(0, Qt.UserRole, skill['name'])
            
            # Add details as child items
            category_item = QTreeWidgetItem(skill_item)
            category_item.setText(0, f"  Category: {skill['category']}")
            
            status_item = QTreeWidgetItem(skill_item)
            status_item.setText(0, f"  Status: {skill['status']}")
    
    def _on_item_clicked(self, item, column):
        """Handle item selection"""
        skill_name = item.data(0, Qt.UserRole)
        if skill_name:
            self.skill_selected.emit(skill_name)
    
    def _show_context_menu(self, position):
        """Show context menu for tree items"""
        item = self.tree.itemAt(position)
        if not item or not item.data(0, Qt.UserRole):
            return
        
        menu = QMenu(self)
        
        # Configure action
        config_action = QAction("Configure", self)
        config_action.triggered.connect(lambda: self._configure_skill(item))
        menu.addAction(config_action)
        
        menu.addSeparator()
        
        # Remove action
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self._remove_skill(item))
        menu.addAction(remove_action)
        
        menu.exec_(self.tree.viewport().mapToGlobal(position))
    
    def _configure_skill(self, item):
        """Configure skill"""
        skill_name = item.data(0, Qt.UserRole)
        if skill_name:
            self.skill_configure_requested.emit(skill_name)
    
    def _remove_skill(self, item):
        """Remove skill"""
        skill_name = item.data(0, Qt.UserRole)
        if skill_name:
            self.skill_remove_requested.emit(skill_name)
    
    def add_skill(self, name: str, category: str, status: str = "enabled"):
        """Add a skill to the tree"""
        skill_item = QTreeWidgetItem(self.tree)
        status_icon = "✓" if status == "enabled" else "✗"
        skill_item.setText(0, f"{status_icon} {name}")
        skill_item.setData(0, Qt.UserRole, name)
        
        # Add details
        category_item = QTreeWidgetItem(skill_item)
        category_item.setText(0, f"  Category: {category}")
        
        status_item = QTreeWidgetItem(skill_item)
        status_item.setText(0, f"  Status: {status}")
    
    def clear_skills(self):
        """Clear all skills"""
        self.tree.clear()
