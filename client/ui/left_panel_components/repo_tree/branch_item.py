"""
Tree item representing a local git branch.
"""
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import Qt

from core.git_utils import BranchInfo

# Custom data roles
ROLE_BRANCH = Qt.UserRole + 1
ROLE_REPO = Qt.UserRole + 2
ROLE_ACTIVE = Qt.UserRole + 3


class BranchItem(QTreeWidgetItem):
    """QTreeWidgetItem for a local git branch."""

    def __init__(self, parent: QTreeWidgetItem, branch: BranchInfo, repo_name: str):
        super().__init__(parent)
        prefix = "* " if branch.is_active else ""
        self.setText(0, f"🌿 {prefix}{branch.name}")
        self.setData(0, ROLE_BRANCH, branch.name)
        self.setData(0, ROLE_REPO, repo_name)
        self.setData(0, ROLE_ACTIVE, branch.is_active)

        if branch.is_active:
            font = self.font(0)
            font.setBold(True)
            self.setFont(0, font)
