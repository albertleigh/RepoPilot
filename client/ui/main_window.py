"""
Main Window for RepoWiki Application
Zeal-like interface with menu, search, side panels, and chat tabs
"""
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QSplitter, QMessageBox
)
from PySide6.QtCore import Qt

from core.services import get_data_service

# Import UI components
from .menu_bar import AppMenuBar
from .search_bar import SearchBar
from .left_panel import LeftPanel
from .chat_tab_widget import ChatTabWidget


class MainWindow(QMainWindow):
    """Main application window with Zeal-like layout"""

    def __init__(self):
        super().__init__()
        self.data_service = get_data_service()
        self.current_repo = None
        self.current_llm = None
        self.init_ui()
        self.connect_signals()
    
    def init_ui(self):
        """Initialize the main UI"""
        self.setWindowTitle("RepoWiki - Repository Documentation & Chat")
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
        self.left_panel = LeftPanel()
        self.main_splitter.addWidget(self.left_panel)
        
        # Right panel (wide) - chat tabs
        self.chat_tabs = ChatTabWidget()
        self.main_splitter.addWidget(self.chat_tabs)
        
        # Set initial sizes: 20% left, 80% right
        self.main_splitter.setSizes([280, 1120])
        self.main_splitter.setStretchFactor(0, 0)  # Left panel fixed-ish
        self.main_splitter.setStretchFactor(1, 1)  # Right panel stretches
        
        main_layout.addWidget(self.main_splitter, 1)  # stretch factor 1 = expands to fill space
        
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
        
        # LLM tree signals
        self.left_panel.llm_tree.llm_add_requested.connect(self.on_add_llm)
        self.left_panel.llm_tree.llm_remove_requested.connect(self.on_remove_llm)
        self.left_panel.llm_tree.llm_configure_requested.connect(self.on_configure_llm)
    
    # Menu handlers
    def on_add_tab(self):
        """Add a new chat tab"""
        repo_name = self.current_repo if self.current_repo else "New Repository"
        llm_name = self.current_llm if self.current_llm else "Default LLM"
        self.chat_tabs.add_chat_tab(repo_name=repo_name, llm_name=llm_name)
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
            "About RepoWiki",
            "<h3>RepoWiki</h3>"
            "<p>Version 1.0.0</p>"
            "<p>A Zeal-like repository documentation and chat interface.</p>"
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
        """Handle add repository"""
        QMessageBox.information(self, "Add Repository", "Add repository dialog - To be implemented")
    
    def on_remove_repo(self, repo_path: str):
        """Handle remove repository"""
        reply = QMessageBox.question(
            self,
            "Remove Repository",
            f"Remove repository: {repo_path}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.statusBar().showMessage(f"Repository removed: {repo_path}")
    
    def on_refresh_repo(self, repo_path: str):
        """Handle refresh repository"""
        self.statusBar().showMessage(f"Refreshing repository: {repo_path}")
        # TODO: Implement actual refresh
    
    # LLM handlers
    def on_llm_selected(self, llm_name: str):
        """Handle LLM selection"""
        self.current_llm = llm_name
        self.statusBar().showMessage(f"LLM selected: {llm_name}")
    
    def on_add_llm(self):
        """Handle add LLM"""
        QMessageBox.information(self, "Add LLM Client", "Add LLM client dialog - To be implemented")
    
    def on_remove_llm(self, llm_name: str):
        """Handle remove LLM"""
        reply = QMessageBox.question(
            self,
            "Remove LLM Client",
            f"Remove LLM client: {llm_name}?",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self.statusBar().showMessage(f"LLM client removed: {llm_name}")
    
    def on_configure_llm(self, llm_name: str):
        """Handle configure LLM"""
        QMessageBox.information(
            self,
            "Configure LLM",
            f"Configuration for: {llm_name}\n\nTo be implemented"
        )
