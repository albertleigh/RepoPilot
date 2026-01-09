"""
Left Panel Component
Combines repository and LLM client tree views
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PySide6.QtCore import Qt, Signal
from .left_panel_components import RepoTree, LLMTree, SkillTree, MCPTree, CollapsibleSection


class LeftPanel(QWidget):
    """Left panel containing repository and LLM trees"""
    
    # Forwarded signals
    repo_selected = Signal(str)
    llm_selected = Signal(str)
    skill_selected = Signal(str)
    mcp_selected = Signal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self._connect_signals()
    
    def setup_ui(self):
        """Create left panel UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Create splitter for resizable sections
        self.splitter = QSplitter(Qt.Vertical)
        self.splitter.setChildrenCollapsible(False)  # Prevent children from collapsing to 0
        self.splitter.setHandleWidth(4)  # Make splitter handle more visible
        
        # Repository tree (top)
        self.repo_tree = RepoTree()
        self.splitter.addWidget(self.repo_tree)

        # LLM tree section (bottom) - collapsible
        self.llm_section = CollapsibleSection(
            "🤖 LLM Clients",
            show_action_button=True,
            action_button_text="+",
            action_button_tooltip="Add LLM client"
        )
        self.llm_tree = LLMTree(show_header=False)  # No header since CollapsibleSection has it
        self.llm_section.set_content(self.llm_tree)

        # Connect action button to add LLM
        self.llm_section.action_button_clicked.connect(self.llm_tree.llm_add_requested.emit)

        # Connect toggle signal to refresh splitter
        self.llm_section.toggled.connect(self._on_section_toggled)
        
        self.splitter.addWidget(self.llm_section)

        # Skill tree section - collapsible
        self.skill_section = CollapsibleSection(
            "⚡ Skills",
            show_action_button=True,
            action_button_text="+",
            action_button_tooltip="Add skill"
        )
        self.skill_tree = SkillTree(show_header=False)
        self.skill_section.set_content(self.skill_tree)
        
        # Connect action button to add skill
        self.skill_section.action_button_clicked.connect(self.skill_tree.skill_add_requested.emit)
        self.skill_section.toggled.connect(self._on_section_toggled)
        
        self.splitter.addWidget(self.skill_section)

        # MCP tree section - collapsible
        self.mcp_section = CollapsibleSection(
            "🔌 MCP Servers",
            show_action_button=True,
            action_button_text="+",
            action_button_tooltip="Add MCP server"
        )
        self.mcp_tree = MCPTree(show_header=False)
        self.mcp_section.set_content(self.mcp_tree)
        
        # Connect action button to add MCP server
        self.mcp_section.action_button_clicked.connect(self.mcp_tree.mcp_add_requested.emit)
        self.mcp_section.toggled.connect(self._on_section_toggled)
        
        self.splitter.addWidget(self.mcp_section)

        # Set initial sizes (40% repos, 20% LLMs, 20% Skills, 20% MCP)
        self.splitter.setSizes([400, 200, 200, 200])

        layout.addWidget(self.splitter)

    def _on_section_toggled(self, is_expanded: bool):
        """Handle section toggle to refresh splitter"""
        # Force splitter to recalculate sizes
        self.splitter.refresh()
    
    def _connect_signals(self):
        """Connect internal signals to external signals"""
        # Forward repository signals
        self.repo_tree.repo_selected.connect(self.repo_selected.emit)
        
        # Forward LLM signals
        self.llm_tree.llm_selected.connect(self.llm_selected.emit)
        
        # Forward Skill signals
        self.skill_tree.skill_selected.connect(self.skill_selected.emit)
        
        # Forward MCP signals
        self.mcp_tree.mcp_selected.connect(self.mcp_selected.emit)
    
    def get_repo_tree(self) -> RepoTree:
        """Get the repository tree widget"""
        return self.repo_tree
    
    def get_llm_tree(self) -> LLMTree:
        """Get the LLM tree widget"""
        return self.llm_tree
    
    def get_skill_tree(self) -> SkillTree:
        """Get the Skill tree widget"""
        return self.skill_tree
    
    def get_mcp_tree(self) -> MCPTree:
        """Get the MCP tree widget"""
        return self.mcp_tree
