"""
Search Bar Component
Search widget for querying repositories and documentation
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLineEdit, QPushButton, QLabel
from PySide6.QtCore import Signal, Qt


class SearchBar(QWidget):
    """Search bar widget with search functionality"""
    
    # Signals
    search_triggered = Signal(str)  # Emits search query
    search_cleared = Signal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Create search bar UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Search icon/label
        search_label = QLabel("🔍")
        search_label.setStyleSheet("font-size: 16px;")
        layout.addWidget(search_label)
        
        # Search input
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search repositories, documentation, or code...")
        self.search_input.returnPressed.connect(self._on_search)
        self.search_input.setMinimumHeight(30)
        layout.addWidget(self.search_input)
        
        # Search button
        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search)
        self.search_button.setMinimumWidth(80)
        layout.addWidget(self.search_button)
        
        # Clear button
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear)
        self.clear_button.setMinimumWidth(60)
        layout.addWidget(self.clear_button)
    
    def _on_search(self):
        """Handle search trigger"""
        query = self.search_input.text().strip()
        if query:
            self.search_triggered.emit(query)
    
    def _on_clear(self):
        """Handle clear button"""
        self.search_input.clear()
        self.search_cleared.emit()
    
    def get_query(self) -> str:
        """Get current search query"""
        return self.search_input.text().strip()
    
    def set_query(self, query: str):
        """Set search query"""
        self.search_input.setText(query)
