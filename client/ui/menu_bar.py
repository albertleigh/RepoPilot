"""
Menu Bar Component
Main application menu with File, Edit, Tools, and Help menus
"""
from PySide6.QtWidgets import QMenuBar
from PySide6.QtGui import QAction
from PySide6.QtCore import Signal


class AppMenuBar(QMenuBar):
    """Application menu bar with signal hooks for actions"""
    
    # File menu signals
    add_tab_requested = Signal()
    close_tab_requested = Signal()
    exit_requested = Signal()
    
    # Edit menu signals
    find_requested = Signal()
    preferences_requested = Signal()
    
    # Tools menu signals
    llm_requested = Signal()
    skill_requested = Signal()
    mcp_requested = Signal()

    # Help menu signals
    check_updates_requested = Signal()
    about_requested = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_menus()
    
    def setup_menus(self):
        """Create all menu items"""
        self._create_file_menu()
        self._create_edit_menu()
        self._create_tools_menu()
        self._create_help_menu()
    
    def _create_file_menu(self):
        """Create File menu"""
        file_menu = self.addMenu("&File")
        
        # Add Tab
        add_tab_action = QAction("&Add Tab", self)
        add_tab_action.setShortcut("Ctrl+T")
        add_tab_action.setStatusTip("Open a new conversation tab")
        add_tab_action.triggered.connect(self.add_tab_requested.emit)
        file_menu.addAction(add_tab_action)
        
        # Close Tab
        close_tab_action = QAction("&Close Tab", self)
        close_tab_action.setShortcut("Ctrl+W")
        close_tab_action.setStatusTip("Close the current tab")
        close_tab_action.triggered.connect(self.close_tab_requested.emit)
        file_menu.addAction(close_tab_action)
        
        file_menu.addSeparator()
        
        # Exit
        exit_action = QAction("E&xit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.exit_requested.emit)
        file_menu.addAction(exit_action)
    
    def _create_edit_menu(self):
        """Create Edit menu"""
        edit_menu = self.addMenu("&Edit")
        
        # Find
        find_action = QAction("&Find", self)
        find_action.setShortcut("Ctrl+F")
        find_action.setStatusTip("Find in current conversation")
        find_action.triggered.connect(self.find_requested.emit)
        edit_menu.addAction(find_action)
        
        edit_menu.addSeparator()
        
        # Preferences
        pref_action = QAction("&Preferences", self)
        pref_action.setShortcut("Ctrl+,")
        pref_action.setStatusTip("Open application preferences")
        pref_action.triggered.connect(self.preferences_requested.emit)
        edit_menu.addAction(pref_action)
    
    def _create_tools_menu(self):
        """Create Tools menu"""
        tools_menu = self.addMenu("&Tools")
        
        # LLM
        llm_action = QAction("&LLM", self)
        llm_action.setStatusTip("Manage LLM settings")
        llm_action.triggered.connect(self.llm_requested.emit)
        tools_menu.addAction(llm_action)

        # Skills
        skills_action = QAction("&Skills", self)
        skills_action.setStatusTip("Manage Skills settings")
        skills_action.triggered.connect(self.skill_requested.emit)
        tools_menu.addAction(skills_action)

        # MCP
        mcp_action = QAction("&MCP", self)
        mcp_action.setStatusTip("Manage MCP settings")
        mcp_action.triggered.connect(self.mcp_requested.emit)
        tools_menu.addAction(mcp_action)
    
    def _create_help_menu(self):
        """Create Help menu"""
        help_menu = self.addMenu("&Help")
        
        # Check Updates
        update_action = QAction("Check &Updates", self)
        update_action.setStatusTip("Check for application updates")
        update_action.triggered.connect(self.check_updates_requested.emit)
        help_menu.addAction(update_action)
        
        help_menu.addSeparator()
        
        # About
        about_action = QAction("&About RepoCode", self)
        about_action.setStatusTip("About RepoCode")
        about_action.triggered.connect(self.about_requested.emit)
        help_menu.addAction(about_action)
