"""
Repository Tree Component
Tree view for displaying and managing repositories.
Backed by :class:`RepoRegistry` for persistence and
:class:`EngineerManagerRegistry` for agent lifecycle.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem,
    QPushButton, QHBoxLayout, QLabel, QMenu
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction

from core.repo_registry import RepoRegistry
from core.engineer_manager.registry import EngineerManagerRegistry


class RepoTree(QWidget):
    """Repository tree widget with management controls"""

    # Signals
    repo_selected = Signal(str)  # Emits repo display name
    repo_add_requested = Signal()
    repo_remove_requested = Signal(str)
    repo_refresh_requested = Signal(str)
    repo_start_engineer = Signal(str)   # Emits repo name → start agent
    repo_stop_engineer = Signal(str)    # Emits repo name → stop agent
    repo_open_chat = Signal(str)        # Emits repo name → open engineer tab
    open_project_manager = Signal()     # Request to open the PM chat tab

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

    def setup_ui(self):
        """Create repository tree UI"""
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
        """Rebuild the tree from the RepoRegistry + running status."""
        self.tree.clear()
        from pathlib import Path

        for name, path_str in self._repo_reg.all_repos().items():
            mgr = self._eng_reg.get(Path(path_str))
            running = mgr is not None and mgr.is_running
            self._add_repo_item(name, path_str, running)

    def _add_repo_item(self, name: str, path: str, running: bool):
        """Add a single repo item to the tree."""
        item = QTreeWidgetItem(self.tree)
        icon = "\u25B6\uFE0F" if running else "\u23F9\uFE0F"
        item.setText(0, f"{icon} {name}")
        item.setData(0, Qt.UserRole, name)

        path_item = QTreeWidgetItem(item)
        path_item.setText(0, f"  \U0001F4C2 {path}")

    # ------------------------------------------------------------------
    # Interaction
    # ------------------------------------------------------------------

    def _on_item_clicked(self, item, column):
        name = item.data(0, Qt.UserRole)
        if name:
            self.repo_selected.emit(name)

    def _on_item_double_clicked(self, item, column):
        name = item.data(0, Qt.UserRole)
        if not name:
            return
        from pathlib import Path
        path_str = self._repo_reg.get(name)
        mgr = self._eng_reg.get(Path(path_str)) if path_str else None
        running = mgr is not None and mgr.is_running
        if not running:
            self.repo_start_engineer.emit(name)
        self.repo_open_chat.emit(name)

    def _show_context_menu(self, position):
        item = self.tree.itemAt(position)
        if not item:
            return
        name = item.data(0, Qt.UserRole)
        if not name:
            return

        from pathlib import Path
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

    def _open_in_code(self, path: str):
        """Launch VS Code for the given folder."""
        import subprocess
        import sys
        if sys.platform == "win32":
            subprocess.Popen(["cmd", "/c", "code", path])
        else:
            subprocess.Popen(["code", path])

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    def clear_repos(self):
        self.tree.clear()
