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

from core.skills.skill_registry import SkillRegistry


class SkillTree(QWidget):
    """Skill tree widget with management controls"""
    
    # Signals
    skill_selected = Signal(str)  # Emits skill name
    skill_add_requested = Signal()
    skill_remove_requested = Signal(str)
    
    def __init__(self, skill_registry: SkillRegistry,
                 show_header: bool = True, parent=None):
        super().__init__(parent)
        self._skill_reg = skill_registry
        self.show_header = show_header
        self.setup_ui()
        self.refresh()
    
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
    
    def refresh(self):
        """Rebuild the tree from the SkillRegistry."""
        self.tree.clear()
        for name, skill in self._skill_reg.all_skills().items():
            meta = skill.get("meta", {})
            description = meta.get("description", "")
            self.add_skill(name, description)
    
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
        
        # Remove action
        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self._remove_skill(item))
        menu.addAction(remove_action)
        
        menu.exec_(self.tree.viewport().mapToGlobal(position))
    
    def _remove_skill(self, item):
        """Remove skill"""
        skill_name = item.data(0, Qt.UserRole)
        if skill_name:
            self.skill_remove_requested.emit(skill_name)
    
    def add_skill(self, name: str, description: str = ""):
        """Add a skill to the tree"""
        skill_item = QTreeWidgetItem(self.tree)
        skill_item.setText(0, f"⚡ {name}")
        skill_item.setData(0, Qt.UserRole, name)
        
        # Add description as child (unwrap to single line, tooltip for full text)
        if description:
            one_line = " ".join(description.splitlines())
            desc_item = QTreeWidgetItem(skill_item)
            desc_item.setText(0, f"  {one_line}")
            desc_item.setToolTip(0, description)

    def remove_skill(self, name: str):
        """Remove a skill from the tree by name."""
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item and item.data(0, Qt.UserRole) == name:
                self.tree.takeTopLevelItem(i)
                return
    
    def clear_skills(self):
        """Clear all skills"""
        self.tree.clear()
