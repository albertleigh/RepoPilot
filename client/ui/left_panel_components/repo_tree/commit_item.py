"""
Tree item representing a single git commit.
"""
from PySide6.QtWidgets import QTreeWidgetItem
from PySide6.QtCore import Qt

from core.git_utils import CommitInfo

# Custom data roles
ROLE_COMMIT_HASH = Qt.UserRole + 10
ROLE_REPO = Qt.UserRole + 11
ROLE_BRANCH = Qt.UserRole + 12


class CommitItem(QTreeWidgetItem):
    """QTreeWidgetItem for a commit in a branch's history."""

    def __init__(
        self,
        parent: QTreeWidgetItem,
        commit: CommitInfo,
        repo_name: str,
        branch_name: str,
    ):
        super().__init__(parent)
        self.setText(0, f"📝 {commit.short_hash} — {commit.subject} ({commit.date})")
        self.setData(0, ROLE_COMMIT_HASH, commit.hash)
        self.setData(0, ROLE_REPO, repo_name)
        self.setData(0, ROLE_BRANCH, branch_name)
        self.setToolTip(0, f"{commit.hash}\n{commit.author}\n{commit.date}")
