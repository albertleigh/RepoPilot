"""
Collapsible Section Component
A collapsible/expandable container with header that can hold any widget
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QSizePolicy
)
from PySide6.QtCore import Qt, Signal


class CollapsibleSection(QWidget):
    """Collapsible section with toggle button and content area"""

    # Signals
    toggled = Signal(bool)  # Emits expanded state
    action_button_clicked = Signal()  # Emits when action button (e.g., +) is clicked
    
    def __init__(self, title: str = "Section", show_action_button: bool = False,
                 action_button_text: str = "+", action_button_tooltip: str = "Add", parent=None):
        super().__init__(parent)
        self.title = title
        self.is_expanded = True
        self.content_widget = None
        self.show_action_button = show_action_button
        self.action_button_text = action_button_text
        self.action_button_tooltip = action_button_tooltip
        self.setup_ui()

    def setup_ui(self):
        """Create collapsible section UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # Header frame
        self.header_frame = QFrame()
        self.header_frame.setFrameShape(QFrame.StyledPanel)
        self.header_frame.setStyleSheet("""
            QFrame {
                background-color: palette(button);
                border: 1px solid palette(mid);
                border-radius: 3px;
            }
            QFrame:hover {
                background-color: palette(midlight);
            }
        """)
        self.header_frame.mousePressEvent = self._header_clicked
        
        header_layout = QHBoxLayout(self.header_frame)
        header_layout.setContentsMargins(5, 3, 5, 3)
        
        # Toggle button (arrow)
        self.toggle_button = QPushButton("▼")
        self.toggle_button.setMaximumWidth(20)
        self.toggle_button.setFlat(True)
        self.toggle_button.setStyleSheet("""
            QPushButton {
                border: none;
                font-weight: bold;
                background: transparent;
                color: palette(button-text);
            }
        """)
        self.toggle_button.clicked.connect(self.toggle)
        header_layout.addWidget(self.toggle_button)
        
        # Title label
        self.title_label = QLabel(self.title)
        self.title_label.setStyleSheet("""
            QLabel {
                font-weight: bold;
                font-size: 12px;
                background: transparent;
                border: none;
                padding: 0px;
                color: palette(button-text);
            }
        """)
        header_layout.addWidget(self.title_label)
        
        header_layout.addStretch()

        # Optional action button (e.g., + button)
        if self.show_action_button:
            self.action_button = QPushButton(self.action_button_text)
            self.action_button.setMinimumWidth(24)
            self.action_button.setMinimumHeight(24)
            self.action_button.setToolTip(self.action_button_tooltip)
            self.action_button.setStyleSheet("""
                QPushButton {
                    border: 1px solid palette(mid);
                    border-radius: 3px;
                    background: palette(button);
                    color: palette(button-text);
                    font-weight: bold;
                    font-size: 14px;
                    padding: 2px 0px;
                }
                QPushButton:hover {
                    background: palette(midlight);
                    border: 1px solid palette(dark);
                }
                QPushButton:pressed {
                    background: palette(dark);
                }
            """)
            self.action_button.clicked.connect(self.action_button_clicked.emit)
            header_layout.addWidget(self.action_button)

        layout.addWidget(self.header_frame)
        
        # Content container
        self.content_frame = QFrame()
        self.content_frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(0, 2, 0, 0)
        layout.addWidget(self.content_frame, 1)  # stretch factor 1 to allow expansion
    
    def set_content(self, widget: QWidget):
        """Set the content widget for this section"""
        # Remove previous content if exists
        if self.content_widget:
            self.content_layout.removeWidget(self.content_widget)
        
        self.content_widget = widget
        self.content_layout.addWidget(widget)
    
    def _header_clicked(self, event):
        """Handle header click - toggle unless action button was clicked"""
        # Check if click was on action button
        if self.show_action_button:
            button_geometry = self.action_button.geometry()
            click_pos = event.pos()
            if button_geometry.contains(click_pos):
                # Let the button handle it
                return
        
        # Toggle the section
        self.toggle()
    
    def toggle(self):
        """Toggle expanded/collapsed state"""
        self.is_expanded = not self.is_expanded
        
        # Update arrow direction
        self.toggle_button.setText("▼" if self.is_expanded else "▶")
        
        # Show/hide content and adjust size policy
        if self.is_expanded:
            self.content_frame.show()
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.setMaximumHeight(16777215)  # Reset to Qt's default max (QWIDGETSIZE_MAX)
            self.setMinimumHeight(0)  # Reset minimum height
        else:
            self.content_frame.hide()
            self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            header_height = self.header_frame.sizeHint().height()
            self.setMaximumHeight(header_height + 10)
            self.setMinimumHeight(header_height + 10)
        
        # Emit signal
        self.toggled.emit(self.is_expanded)
        
        # Force parent splitter to recalculate
        if self.parent() and hasattr(self.parent(), 'refresh'):
            self.parent().refresh()
        elif self.parent():
            self.parent().update()
    
    def expand(self):
        """Expand the section"""
        if not self.is_expanded:
            self.toggle()
    
    def collapse(self):
        """Collapse the section"""
        if self.is_expanded:
            self.toggle()
    
    def set_title(self, title: str):
        """Update section title"""
        self.title = title
        self.title_label.setText(title)
