"""
Main Window for RepoCode Application
Zeal-like interface with menu, search, side panels, and chat tabs
"""
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QMessageBox, QFileDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence, QShortcut

from core.context import AppContext
from core.events import Event, EventKind

# Import UI components
from .event_bridge import QtEventBridge
from .menu_bar import AppMenuBar
from .search_bar import SearchBar
from .left_panel import LeftPanel
from .tabs_manager import TabsManager
from .llm import CreateLLMDialog, ConfigureLLMDialog


class MainWindow(QMainWindow):
    """Main application window with Zeal-like layout"""

    def __init__(self, ctx: AppContext):
        super().__init__()
        self.ctx = ctx
        self.current_repo = None
        self.current_llm = ctx.llm_client_registry.selected_name()

        # Event bridge: delivers EventBus events on the Qt main thread
        self._event_bridge = QtEventBridge(ctx.event_bus, parent=self)

        self.init_ui()
        self.connect_signals()
        self._init_debug_panel()
    
    def init_ui(self):
        """Initialize the main UI"""
        self.setWindowTitle("RepoCode - Repository Documentation & Chat")
        self.setGeometry(100, 100, 1400, 900)
        
        # Create menu bar
        self.menu_bar = AppMenuBar(self)
        self.setMenuBar(self.menu_bar)
        
        # Central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main layout
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)
        
        # Search bar at top (fixed height, no vertical stretch)
        self.search_bar = SearchBar()
        main_layout.addWidget(self.search_bar, 0)  # stretch factor 0 = fixed size
        
        # Horizontal splitter for left panel and right chat area
        self.main_splitter = QSplitter(Qt.Horizontal)
        
        # Left panel (thin) - repos and LLM trees
        self.left_panel = LeftPanel(self.ctx)
        self.main_splitter.addWidget(self.left_panel)
        
        # Right panel (wide) - chat tabs
        self.chat_tabs = TabsManager()
        self.main_splitter.addWidget(self.chat_tabs)
        
        # Set initial sizes: 20% left, 80% right
        self.main_splitter.setSizes([280, 1120])
        self.main_splitter.setStretchFactor(0, 0)  # Left panel fixed-ish
        self.main_splitter.setStretchFactor(1, 1)  # Right panel stretches
        
        main_layout.addWidget(self.main_splitter, 1)  # stretch factor 1 = expands to fill space

        # Debug panel placeholder — inserted below main_splitter, hidden by default
        self._debug_panel = None
        self._debug_container = QWidget()
        self._debug_container.hide()
        main_layout.addWidget(self._debug_container, 0)

        # Status bar
        self.statusBar().showMessage("Ready")
    
    def connect_signals(self):
        """Connect all UI signals to handlers"""
        # Menu bar signals
        self.menu_bar.add_tab_requested.connect(self.on_add_tab)
        self.menu_bar.close_tab_requested.connect(self.on_close_tab)
        self.menu_bar.exit_requested.connect(self.close)
        self.menu_bar.find_requested.connect(self.on_find)
        self.menu_bar.preferences_requested.connect(self.on_preferences)
        self.menu_bar.llm_requested.connect(self.on_llm_tools)
        self.menu_bar.check_updates_requested.connect(self.on_check_updates)
        self.menu_bar.about_requested.connect(self.on_about)
        
        # Search bar signals
        self.search_bar.search_triggered.connect(self.on_search)
        self.search_bar.search_cleared.connect(self.on_search_cleared)
        
        # Left panel signals
        self.left_panel.repo_selected.connect(self.on_repo_selected)
        self.left_panel.llm_selected.connect(self.on_llm_selected)
        
        # Repository tree signals
        self.left_panel.repo_tree.repo_add_requested.connect(self.on_add_repo)
        self.left_panel.repo_tree.repo_remove_requested.connect(self.on_remove_repo)
        self.left_panel.repo_tree.repo_refresh_requested.connect(self.on_refresh_repo)
        self.left_panel.repo_tree.repo_start_engineer.connect(self.on_start_engineer)
        self.left_panel.repo_tree.repo_stop_engineer.connect(self.on_stop_engineer)
        self.left_panel.repo_tree.repo_open_chat.connect(self.on_open_engineer_chat)

        # Refresh tree icon when an engineer starts or stops
        self._event_bridge.on(
            {EventKind.ENGINEER_STARTED, EventKind.ENGINEER_STOPPED},
            self._on_engineer_lifecycle,
        )
        
        # LLM tree signals
        self.left_panel.llm_tree.llm_add_requested.connect(self.on_add_llm)
        self.left_panel.llm_tree.llm_remove_requested.connect(self.on_remove_llm)
        self.left_panel.llm_tree.llm_configure_requested.connect(self.on_configure_llm)

        # Skill tree signals
        self.left_panel.skill_tree.skill_add_requested.connect(self.on_add_skill)
        self.left_panel.skill_tree.skill_remove_requested.connect(self.on_remove_skill)

    # ------------------------------------------------------------------
    # Debug panel
    # ------------------------------------------------------------------

    def _init_debug_panel(self):
        """Create the debug panel and bind F12 to toggle it."""
        from .debug_panel import DebugPanel

        layout = QVBoxLayout(self._debug_container)
        layout.setContentsMargins(0, 0, 0, 0)
        self._debug_panel = DebugPanel(self.ctx, self, parent=self._debug_container)
        layout.addWidget(self._debug_panel)

        self._debug_panel.undock_requested.connect(self._toggle_debug_dock)

        self._debug_window = None  # floating window when undocked

        shortcut = QShortcut(QKeySequence(Qt.Key_F12), self)
        shortcut.activated.connect(self.toggle_debug_panel)

    def toggle_debug_panel(self):
        """Show / hide the debug panel (docked or floating)."""
        if self._debug_window is not None:
            # Floating — close the window and re-dock (hidden)
            self._dock_debug_panel()
            return
        if self._debug_container.isVisible():
            self._debug_container.hide()
        else:
            self._debug_container.show()
            self._debug_container.setMinimumHeight(250)
            self._debug_container.setMaximumHeight(400)
            self._debug_panel._refresh_services()
            self._debug_panel._refresh_log_tail()

    def _toggle_debug_dock(self):
        """Pop the debug panel out to its own window, or dock it back."""
        if self._debug_window is not None:
            self._dock_debug_panel()
        else:
            self._undock_debug_panel()

    def _undock_debug_panel(self):
        """Move the debug panel into a free-floating window."""
        from PySide6.QtWidgets import QVBoxLayout as _VBox

        self._debug_container.hide()

        self._debug_window = QWidget(None, Qt.Window)
        self._debug_window.setWindowTitle("🛠️ Debug Tools")
        self._debug_window.resize(900, 450)
        lay = _VBox(self._debug_window)
        lay.setContentsMargins(0, 0, 0, 0)

        self._debug_panel.setParent(self._debug_window)
        lay.addWidget(self._debug_panel)
        self._debug_panel.set_popout_icon(True)
        self._debug_panel.show()
        self._debug_window.show()

    def _dock_debug_panel(self):
        """Return the debug panel to the docked container."""
        if self._debug_window is not None:
            self._debug_window.hide()

        self._debug_panel.setParent(self._debug_container)
        self._debug_container.layout().addWidget(self._debug_panel)
        self._debug_panel.set_popout_icon(False)
        self._debug_panel.show()
        self._debug_container.show()
        self._debug_container.setMinimumHeight(250)
        self._debug_container.setMaximumHeight(400)

        if self._debug_window is not None:
            self._debug_window.deleteLater()
            self._debug_window = None

    # Menu handlers
    def on_add_tab(self):
        """Add a new chat tab"""
        from .tabs_item import ChatTab
        repo_name = self.current_repo if self.current_repo else "New Repository"
        llm_name = self.current_llm if self.current_llm else "Default LLM"
        tab = ChatTab(repo_name=repo_name, llm_name=llm_name)
        self.chat_tabs.add_tab(tab)
        self.statusBar().showMessage(f"New chat tab opened for {repo_name}")
    
    def on_close_tab(self):
        """Close current tab"""
        self.chat_tabs.close_current_tab()
    
    def on_find(self):
        """Handle find action"""
        QMessageBox.information(self, "Find", "Find functionality - To be implemented")
    
    def on_preferences(self):
        """Handle preferences action"""
        QMessageBox.information(self, "Preferences", "Preferences dialog - To be implemented")
    
    def on_llm_tools(self):
        """Handle LLM tools action"""
        QMessageBox.information(self, "LLM Tools", "LLM configuration and tools - To be implemented")
    
    def on_check_updates(self):
        """Handle check updates action"""
        QMessageBox.information(
            self, 
            "Check Updates", 
            "Current Version: 1.0.0\n\nNo updates available."
        )
    
    def on_about(self):
        """Handle about action"""
        QMessageBox.about(
            self,
            "About RepoCode",
            "<h3>RepoCode</h3>"
            "<p>Version 1.0.0</p>"
            "<p>A Zeal-like repository documentation and code and chat interface.</p>"
            "<p>Powered by Qt and Python.</p>"
        )
    
    # Search handlers
    def on_search(self, query: str):
        """Handle search"""
        self.statusBar().showMessage(f"Searching for: {query}")
        # TODO: Implement actual search functionality
        QMessageBox.information(self, "Search", f"Search results for: '{query}'\n\nTo be implemented")
    
    def on_search_cleared(self):
        """Handle search cleared"""
        self.statusBar().showMessage("Search cleared")
    
    # Repository handlers
    def on_repo_selected(self, repo_path: str):
        """Handle repository selection"""
        self.current_repo = repo_path
        self.statusBar().showMessage(f"Repository selected: {repo_path}")
    
    def on_add_repo(self):
        """Handle add repository – pick a folder and register it."""
        folder = QFileDialog.getExistingDirectory(self, "Select Repository Root")
        if not folder:
            return
        name = Path(folder).name
        self.ctx.repo_registry.register(name, folder)
        self.left_panel.repo_tree.refresh()
        self.statusBar().showMessage(f"Repository added: {name}")

    def on_remove_repo(self, repo_name: str):
        """Handle remove repository"""
        reply = QMessageBox.question(
            self,
            "Remove Repository",
            f"Remove repository: {repo_name}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            # Stop engineer if running
            path_str = self.ctx.repo_registry.get(repo_name)
            if path_str:
                self.ctx.engineer_manager_registry.remove(Path(path_str))
            self.ctx.repo_registry.unregister(repo_name)
            self.left_panel.repo_tree.refresh()
            self.statusBar().showMessage(f"Repository removed: {repo_name}")

    def on_refresh_repo(self, repo_name: str):
        """Handle refresh repository"""
        self.left_panel.repo_tree.refresh()
        self.statusBar().showMessage(f"Refreshed: {repo_name}")
    
    # LLM handlers
    def on_llm_selected(self, llm_name: str):
        """Handle LLM selection"""
        self.current_llm = llm_name
        self.ctx.llm_client_registry.select(llm_name)
        self.left_panel.llm_tree.refresh()
        self.statusBar().showMessage(f"LLM selected: {llm_name}")
    
    def on_add_llm(self):
        """Handle add LLM – open the creation dialog"""
        dialog = CreateLLMDialog(self.ctx, parent=self)
        dialog.llm_created.connect(self._on_llm_created)
        dialog.exec()

    def _on_llm_created(self, display_name: str, provider: str):
        """Callback when a new LLM client is created via the dialog."""
        self.current_llm = self.ctx.llm_client_registry.selected_name()
        self.left_panel.llm_tree.refresh()
        self.statusBar().showMessage(f"LLM client '{display_name}' added")
    
    def on_remove_llm(self, llm_name: str):
        """Handle remove LLM"""
        reply = QMessageBox.question(
            self,
            "Remove LLM Client",
            f"Remove LLM client: {llm_name}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.ctx.llm_client_registry.unregister(llm_name)
            self.current_llm = self.ctx.llm_client_registry.selected_name()
            self.left_panel.llm_tree.refresh()
            self.statusBar().showMessage(f"LLM client removed: {llm_name}")
    
    def on_configure_llm(self, llm_name: str):
        """Handle configure LLM – open the configuration dialog."""
        dialog = ConfigureLLMDialog(self.ctx, llm_name, parent=self)
        dialog.llm_updated.connect(self._on_llm_updated)
        dialog.exec()

    def _on_llm_updated(self, display_name: str):
        """Callback when an LLM client is updated via the dialog."""
        self.statusBar().showMessage(f"LLM client '{display_name}' updated")

    # Skill handlers
    def on_add_skill(self):
        """Handle add skill – open a file picker for SKILL.md."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SKILL.md", "", "Skill files (SKILL.md)"
        )
        if not path:
            return
        from pathlib import Path
        ok, msg = self.ctx.skill_registry.register(Path(path))
        if ok:
            self.left_panel.skill_tree.refresh()
            self.statusBar().showMessage(f"Skill '{msg}' added")
        else:
            QMessageBox.warning(self, "Invalid Skill", msg)

    def on_remove_skill(self, skill_name: str):
        """Handle remove skill."""
        reply = QMessageBox.question(
            self,
            "Remove Skill",
            f"Remove skill: {skill_name}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.ctx.skill_registry.unregister(skill_name)
            self.left_panel.skill_tree.remove_skill(skill_name)
            self.statusBar().showMessage(f"Skill removed: {skill_name}")

    # ------------------------------------------------------------------
    # Engineer lifecycle handlers
    # ------------------------------------------------------------------

    def on_start_engineer(self, repo_name: str):
        """Start an EngineerManager for *repo_name* and open its chat tab."""
        path_str = self.ctx.repo_registry.get(repo_name)
        if not path_str:
            QMessageBox.warning(self, "Error", f"No path found for repo: {repo_name}")
            return

        workdir = Path(path_str)
        if self.ctx.engineer_manager_registry.get(workdir) is not None:
            self.statusBar().showMessage(f"Engineer already running for {repo_name}")
            self.on_open_engineer_chat(repo_name)
            return

        llm_client = self.ctx.llm_client_registry.selected_client()
        if llm_client is None:
            QMessageBox.warning(
                self, "No LLM selected",
                "Please select an LLM client before starting the engineer.",
            )
            return

        # Sync global skills into the repo before starting the agent
        from core.skills.utils import sync_skills_to_repo
        sync_skills_to_repo(self.ctx.base_dir / "skills", workdir)

        self.ctx.engineer_manager_registry.create(workdir, llm_client, auto_start=True)
        self.left_panel.repo_tree.refresh()
        self.on_open_engineer_chat(repo_name)
        self.statusBar().showMessage(f"Engineer started for {repo_name}")

    def on_stop_engineer(self, repo_name: str):
        """Stop the EngineerManager for *repo_name*."""
        path_str = self.ctx.repo_registry.get(repo_name)
        if path_str:
            self.ctx.engineer_manager_registry.remove(Path(path_str))
        self.left_panel.repo_tree.refresh()
        self.statusBar().showMessage(f"Engineer stopped for {repo_name}")

    def on_open_engineer_chat(self, repo_name: str):
        """Open (or focus) the EngineerChatTab for *repo_name*."""
        from .tabs_item import EngineerChatTab

        path_str = self.ctx.repo_registry.get(repo_name)
        if not path_str:
            return

        # Re-use an existing tab or create a new one
        tab = self.chat_tabs.find_tab(
            EngineerChatTab, lambda t: t.repo_name == repo_name,
        )
        if tab is not None:
            self.chat_tabs.focus_tab(tab)
        else:
            tab = EngineerChatTab(
                repo_name=repo_name,
                event_bus=self.ctx.event_bus,
                workdir=path_str,
            )
            self.chat_tabs.add_tab(tab)

            # Wire signals only once, when the tab is first created
            mgr = self.ctx.engineer_manager_registry.get(Path(path_str))
            if mgr is not None:
                tab.message_sent.connect(mgr.send_message)
                tab.stop_requested.connect(mgr.cancel)

    # ------------------------------------------------------------------
    # Engineer lifecycle (tree refresh only)
    # ------------------------------------------------------------------

    def _on_engineer_lifecycle(self, event: Event):
        """Refresh the repo tree when an engineer starts or stops."""
        self.left_panel.repo_tree.refresh()
