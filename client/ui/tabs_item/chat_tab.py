"""
Chat Tab Component
Individual chat conversation tab with message history and input
"""
from PySide6.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QTextEdit,
    QPushButton, QLabel, QWidget,
)
from PySide6.QtCore import Signal
from datetime import datetime

from .base_tab import BaseTab


class ChatTab(BaseTab):
    """Individual chat conversation tab"""
    
    # Signals
    message_sent = Signal(str)  # Emits user message

    tab_icon = "\U0001F4AC"  # 💬
    
    def __init__(self, repo_name: str = "Unknown", llm_name: str = "Default LLM", parent=None):
        super().__init__(parent)
        self.repo_name = repo_name
        self.llm_name = llm_name
        self.message_history = []
        self.setup_ui()
    
    def setup_ui(self):
        """Create chat tab UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header with context info
        header_layout = QHBoxLayout()
        context_label = QLabel(f"💬 Chat - Repo: {self.repo_name} | LLM: {self.llm_name}")
        context_label.setStyleSheet("font-weight: bold; padding: 5px; background-color: palette(midlight); color: palette(window-text);")
        header_layout.addWidget(context_label)
        layout.addLayout(header_layout)
        
        # Chat history display
        self.chat_display = QTextEdit()
        self.chat_display.setReadOnly(True)
        self.chat_display.setPlaceholderText("Conversation will appear here...")
        layout.addWidget(self.chat_display, stretch=3)
        
        # Input section
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(0, 5, 0, 0)
        
        # Multi-line input
        input_label = QLabel("Input your message:")
        input_layout.addWidget(input_label)
        
        self.message_input = QTextEdit()
        self.message_input.setPlaceholderText("Type your question about the repository here...")
        self.message_input.setMaximumHeight(100)
        input_layout.addWidget(self.message_input)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        self.send_button = QPushButton("Send Message")
        self.send_button.clicked.connect(self._on_send_message)
        self.send_button.setMinimumHeight(35)
        button_layout.addWidget(self.send_button)
        
        self.clear_button = QPushButton("Clear History")
        self.clear_button.clicked.connect(self._on_clear_history)
        button_layout.addWidget(self.clear_button)
        
        button_layout.addStretch()
        input_layout.addLayout(button_layout)
        
        layout.addWidget(input_container, stretch=0)
    
    def _on_send_message(self):
        """Handle send message"""
        message = self.message_input.toPlainText().strip()
        if not message:
            return
        
        # Add user message to display
        self._add_message("User", message)
        
        # Clear input
        self.message_input.clear()
        
        # Emit signal
        self.message_sent.emit(message)
        
        # Add dummy response (placeholder for actual LLM integration)
        self._add_dummy_response(message)
    
    def _add_message(self, sender: str, message: str):
        """Add a message to the chat display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # Use palette-aware colors for sender names
        palette = self.palette()
        highlight = palette.highlight().color()
        link = palette.link().color()
        # User gets the link color, assistant gets a contrasting accent
        if sender == "User":
            sender_color = f"rgb({link.red()}, {link.green()}, {link.blue()})"
        else:
            # Shift highlight hue for assistant to differentiate
            accent = highlight.lighter(130) if highlight.lightness() < 128 else highlight.darker(130)
            sender_color = f"rgb({accent.red()}, {accent.green()}, {accent.blue()})"

        fg = palette.windowText().color()
        text_color = f"rgb({fg.red()}, {fg.green()}, {fg.blue()})"

        formatted_message = f"""
<div style="margin-bottom: 10px;">
    <b style="color: {sender_color};">[{timestamp}] {sender}:</b><br>
    <span style="margin-left: 20px; color: {text_color};">{message}</span>
</div>
        """
        
        self.chat_display.append(formatted_message)
        self.message_history.append({"sender": sender, "message": message, "timestamp": timestamp})
    
    def _add_dummy_response(self, user_message: str):
        """Add a dummy LLM response (placeholder)"""
        dummy_response = f"This is a simulated response to: '{user_message[:50]}...'. Integration with {self.llm_name} pending."
        self._add_message(self.llm_name, dummy_response)
    
    def _on_clear_history(self):
        """Clear chat history"""
        self.chat_display.clear()
        self.message_history.clear()
    
    def add_assistant_message(self, message: str):
        """Add an assistant message (for external calls)"""
        self._add_message(self.llm_name, message)
    
    def get_tab_title(self) -> str:
        """Get the tab title"""
        return f"{self.repo_name[:20]}"
