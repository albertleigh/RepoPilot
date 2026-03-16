"""
Repository Tree Widget
Git-aware tree view for managing repositories, branches, and commits.
Backed by :class:`RepoRegistry` for persistence and
:class:`EngineerManagerRegistry` for agent lifecycle.
"""
from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu, QInputDialog,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction

from core.repo_registry import RepoRegistry
from core.engineer_manager.registry import EngineerManagerRegistry
from core import git_utils
from client.ui.async_runner import run_async

from .branch_item import BranchItem, ROLE_BRANCH, ROLE_REPO, ROLE_ACTIVE
from .commit_item import CommitItem, ROLE_COMMIT_HASH
from .commit_item import ROLE_REPO as COMMIT_ROLE_REPO
from .git_result_dialog import GitCommandDialog

_log = logging.getLogger(__name__)


class RepoTree(QWidget):
    """Repository tree widget with git branch / commit management."""

    # Signals – engineer lifecycle (unchanged)
    repo_selected = Signal(str)
    repo_add_requested = Signal()
    repo_remove_requested = Signal(str)
    repo_refresh_requested = Signal(str)
    repo_start_engineer = Signal(str)
    repo_stop_engineer = Signal(str)
    repo_open_chat = Signal(str)
    open_project_manager = Signal()

    def __init__(
        self,
        repo_registry: RepoRegistry,
        engineer_registry: EngineerManagerRegistry,
        parent=None,
    ):
        super().__init__(parent)
        self._repo_reg = repo_registry
        self._eng_reg = engineer_registry
        self.setup_ui()
        self.refresh()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def setup_ui(self):
        """Create repository tree UI."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header_layout = QHBoxLayout()
        header_label = QLabel("📚 Repositories")
        header_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        header_layout.addWidget(header_label)

        self.manager_button = QPushButton("\U0001F4CB")
        self.manager_button.setMaximumWidth(30)
        self.manager_button.setToolTip("Open Project Manager")
        self.manager_button.clicked.connect(self.open_project_manager.emit)
        header_layout.addWidget(self.manager_button)

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
        self.tree.itemDoubleClicked.connect(self._on_item_double_clicked)
        layout.addWidget(self.tree)

    # ------------------------------------------------------------------
    # Refresh / render
    # ------------------------------------------------------------------

    def refresh(self):
        """Rebuild the tree from registries + git state (non-blocking).

        Heavy git subprocess calls are offloaded to a worker thread so
        the UI stays responsive.  While the worker is running a second
        call to ``refresh()`` is a no-op (debounced).
        """
        if getattr(self, "_refresh_pending", False):
            return
        self._refresh_pending = True

        # Snapshot the repo list + running state (fast, main-thread-safe)
        repos: list[tuple[str, str, bool]] = []
        for name, path_str in self._repo_reg.all_repos().items():
            mgr = self._eng_reg.get(Path(path_str))
            running = mgr is not None and mgr.is_running
            repos.append((name, path_str, running))

        def _fetch():
            """Run in worker thread — collect git data."""
            result = []
            for name, path_str, running in repos:
                branches = git_utils.get_branches(path_str)
                branch_data = []
                for branch in branches:
                    commits = git_utils.get_recent_commits(
                        path_str, branch.name, count=5,
                    )
                    branch_data.append((branch, commits))
                result.append((name, path_str, running, branch_data))
            return result

        def _apply(data):
            """Run on main thread — rebuild the tree widget."""
            self.tree.clear()
            for name, path_str, running, branch_data in data:
                self._add_repo_item(name, path_str, running, branch_data)
            self._refresh_pending = False

        def _on_error(exc):
            _log.warning("Repo tree refresh failed: %s", exc)
            self._refresh_pending = False

        run_async(_fetch, on_result=_apply, on_error=_on_error)

    def _add_repo_item(self, name: str, path_str: str, running: bool,
                       branch_data: list | None = None):
        """Add a single repository with its branches and commits.

        When *branch_data* is ``None`` (legacy call), branches/commits
        are fetched synchronously — prefer passing pre-fetched data.
        """
        item = QTreeWidgetItem(self.tree)
        icon = "\u25B6\uFE0F" if running else "\u23F9\uFE0F"
        item.setText(0, f"{icon} {name} ({path_str})")
        item.setData(0, Qt.UserRole, name)

        if branch_data is None:
            # Fallback: fetch synchronously (only used if called directly)
            branches = git_utils.get_branches(path_str)
            branch_data = [
                (branch, git_utils.get_recent_commits(path_str, branch.name, count=5))
                for branch in branches
            ]

        if not branch_data:
            placeholder = QTreeWidgetItem(item)
            placeholder.setText(0, "No branches found")
            placeholder.setFlags(Qt.NoItemFlags)
            return

        for branch, commits in branch_data:
            branch_node = BranchItem(item, branch, name)
            for commit in commits:
                CommitItem(branch_node, commit, name, branch.name)

    # ------------------------------------------------------------------
    # Click handlers
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item, column):
        name = item.data(0, Qt.UserRole)
        if name:
            self.repo_selected.emit(name)

    def _on_item_double_clicked(self, item, column):
        name = item.data(0, Qt.UserRole)
        if not name:
            return
        path_str = self._repo_reg.get(name)
        mgr = self._eng_reg.get(Path(path_str)) if path_str else None
        running = mgr is not None and mgr.is_running
        if not running:
            self.repo_start_engineer.emit(name)
        self.repo_open_chat.emit(name)

    # ------------------------------------------------------------------
    # Context menus
    # ------------------------------------------------------------------

    def _show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return

        if isinstance(item, CommitItem):
            self._show_commit_context_menu(item, position)
        elif isinstance(item, BranchItem):
            self._show_branch_context_menu(item, position)
        else:
            name = item.data(0, Qt.UserRole)
            if name:
                self._show_repo_context_menu(name, position)

    # -- repo ---------------------------------------------------------

    def _show_repo_context_menu(self, name: str, position):
        import shutil

        path_str = self._repo_reg.get(name)
        mgr = self._eng_reg.get(Path(path_str)) if path_str else None
        running = mgr is not None and mgr.is_running

        menu = QMenu(self)

        if running:
            open_action = QAction("Open Chat", self)
            open_action.triggered.connect(lambda: self.repo_open_chat.emit(name))
            menu.addAction(open_action)

            stop_action = QAction("Stop Engineer", self)
            stop_action.triggered.connect(lambda: self.repo_stop_engineer.emit(name))
            menu.addAction(stop_action)
        else:
            start_action = QAction("Start Engineer", self)
            start_action.triggered.connect(lambda: self.repo_start_engineer.emit(name))
            menu.addAction(start_action)

        menu.addSeparator()

        # Open in VS Code
        code_action = QAction("Open in Code", self)
        code_path = shutil.which("code")
        if code_path and path_str and Path(path_str).is_dir():
            code_action.triggered.connect(lambda: self._open_in_code(path_str))
        else:
            code_action.setEnabled(False)
            if not code_path:
                code_action.setToolTip("'code' not found in PATH")
            elif not path_str or not Path(path_str).is_dir():
                code_action.setToolTip("Folder does not exist")
        menu.addAction(code_action)

        menu.addSeparator()

        refresh_action = QAction("Refresh", self)
        refresh_action.triggered.connect(lambda: self.repo_refresh_requested.emit(name))
        menu.addAction(refresh_action)

        remove_action = QAction("Remove", self)
        remove_action.triggered.connect(lambda: self.repo_remove_requested.emit(name))
        menu.addAction(remove_action)

        menu.exec_(self.tree.viewport().mapToGlobal(position))

    # -- branch -------------------------------------------------------

    def _show_branch_context_menu(self, item: BranchItem, position):
        repo_name = item.data(0, ROLE_REPO)
        branch_name = item.data(0, ROLE_BRANCH)
        is_active = item.data(0, ROLE_ACTIVE)
        path_str = self._repo_reg.get(repo_name)
        if not path_str:
            return

        menu = QMenu(self)

        if not is_active:
            checkout_action = QAction(f"Checkout '{branch_name}'", self)
            checkout_action.triggered.connect(
                lambda _=False, p=path_str, b=branch_name: self._do_checkout(p, b)
            )
            menu.addAction(checkout_action)

        new_branch_action = QAction(f"New branch from '{branch_name}'…", self)
        new_branch_action.triggered.connect(
            lambda _=False, p=path_str, b=branch_name: self._do_new_branch(p, b)
        )
        menu.addAction(new_branch_action)

        if is_active:
            pull_action = QAction("Pull", self)
            pull_action.triggered.connect(
                lambda _=False, p=path_str: self._do_pull(p)
            )
            menu.addAction(pull_action)

        menu.exec_(self.tree.viewport().mapToGlobal(position))

    # -- commit -------------------------------------------------------

    def _show_commit_context_menu(self, item: CommitItem, position):
        repo_name = item.data(0, COMMIT_ROLE_REPO)
        commit_hash = item.data(0, ROLE_COMMIT_HASH)
        path_str = self._repo_reg.get(repo_name)
        if not path_str:
            return

        short = commit_hash[:8]
        menu = QMenu(self)

        hard_action = QAction(f"Reset --hard to {short}", self)
        hard_action.triggered.connect(
            lambda _=False, p=path_str, h=commit_hash: self._do_reset(p, h, "hard")
        )
        menu.addAction(hard_action)

        soft_action = QAction(f"Reset --soft to {short}", self)
        soft_action.triggered.connect(
            lambda _=False, p=path_str, h=commit_hash: self._do_reset(p, h, "soft")
        )
        menu.addAction(soft_action)

        menu.exec_(self.tree.viewport().mapToGlobal(position))

    # ------------------------------------------------------------------
    # Git operations (modal dialog: shows command → runs → shows result)
    # ------------------------------------------------------------------

    def _run_git_dialog(self, label: str, fn):
        """Open a modal dialog, run *fn*, show result, then refresh tree."""
        dialog = GitCommandDialog(label, parent=self)
        dialog.run(fn)
        self.refresh()

    def _do_checkout(self, path: str, branch: str):
        self._run_git_dialog(
            f"git checkout {branch}",
            lambda: git_utils.checkout_branch(path, branch),
        )

    def _do_new_branch(self, path: str, from_branch: str):
        name, ok = QInputDialog.getText(
            self, "New Branch", f"Branch name (from '{from_branch}'):"
        )
        if not ok or not name.strip():
            return
        branch_name = name.strip()
        self._run_git_dialog(
            f"git checkout -b {branch_name} {from_branch}",
            lambda: git_utils.create_branch(path, branch_name, from_branch),
        )

    def _do_pull(self, path: str):
        self._run_git_dialog(
            "git pull",
            lambda: git_utils.pull_current_branch(path),
        )

    def _do_reset(self, path: str, commit_hash: str, mode: str):
        short = commit_hash[:8]
        self._run_git_dialog(
            f"git reset --{mode} {short}",
            lambda: git_utils.reset_to_commit(path, commit_hash, mode),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _open_in_code(self, path: str):
        """Launch VS Code for the given folder."""
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", "code", path])
        else:
            subprocess.Popen(["code", path])

    def clear_repos(self):
        self.tree.clear()
