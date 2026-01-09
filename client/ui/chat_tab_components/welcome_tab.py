"""
Welcome Tab Component
Landing page shown when application starts or when all tabs are closed
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QTextBrowser
from PySide6.QtCore import Qt


class WelcomeTab(QWidget):
    """Welcome/landing page widget without chat functionality"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
    
    def setup_ui(self):
        """Create welcome tab UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Use QTextBrowser for rich text display (read-only, no input)
        self.content_display = QTextBrowser()
        self.content_display.setOpenExternalLinks(True)
        self.content_display.setHtml(self._get_welcome_content())
        
        layout.addWidget(self.content_display)
    
    def _get_welcome_content(self) -> str:
        """Generate welcome page HTML content"""
        return """
        <html>
        <head>
            <style>
                body {
                    font-family: 'Segoe UI', Arial, sans-serif;
                    padding: 40px;
                    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
                }
                .container {
                    max-width: 800px;
                    margin: 0 auto;
                    background: white;
                    padding: 40px;
                    border-radius: 10px;
                    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
                }
                h1 {
                    color: #2c3e50;
                    text-align: center;
                    margin-bottom: 10px;
                }
                .subtitle {
                    text-align: center;
                    color: #7f8c8d;
                    margin-bottom: 40px;
                    font-size: 18px;
                }
                h2 {
                    color: #34495e;
                    border-bottom: 2px solid #3498db;
                    padding-bottom: 10px;
                    margin-top: 30px;
                }
                .getting-started {
                    background-color: #ecf0f1;
                    padding: 20px;
                    border-radius: 5px;
                    margin: 20px 0;
                }
                .getting-started ol {
                    margin: 10px 0;
                    padding-left: 25px;
                }
                .getting-started li {
                    margin: 10px 0;
                    line-height: 1.6;
                }
                .feature-list {
                    list-style: none;
                    padding: 0;
                }
                .feature-list li {
                    padding: 12px 0;
                    border-bottom: 1px solid #ecf0f1;
                }
                .feature-list li:before {
                    content: "✓ ";
                    color: #27ae60;
                    font-weight: bold;
                    margin-right: 10px;
                }
                .shortcut-table {
                    width: 100%;
                    margin: 20px 0;
                    border-collapse: collapse;
                }
                .shortcut-table td {
                    padding: 10px;
                    border: 1px solid #ddd;
                }
                .shortcut-table .key {
                    background-color: #f8f9fa;
                    font-family: monospace;
                    font-weight: bold;
                    width: 150px;
                }
                .icon {
                    font-size: 48px;
                    text-align: center;
                    margin: 20px 0;
                }
            </style>
        </head>
        <body>
            <div class="container">
                <div class="icon">📚 🤖</div>
                <h1>Welcome to RepoWiki</h1>
                <p class="subtitle">Your AI-Powered Repository Documentation Assistant</p>
                
                <div class="getting-started">
                    <h2>🚀 Getting Started</h2>
                    <ol>
                        <li><strong>Add a Repository</strong>: Click the <strong>+</strong> button in the "Repositories" panel to add your codebase</li>
                        <li><strong>Configure LLM</strong>: Select or add an LLM client from the "LLM Clients" panel</li>
                        <li><strong>Start Chatting</strong>: Press <kbd>Ctrl+T</kbd> or use <strong>File → Add Tab</strong> to open a new conversation</li>
                        <li><strong>Ask Questions</strong>: Start asking questions about your code, documentation, or repository structure!</li>
                    </ol>
                </div>
                
                <h2>✨ Features</h2>
                <ul class="feature-list">
                    <li>Multi-repository support - Chat about multiple codebases</li>
                    <li>Multiple LLM providers - OpenAI, Anthropic, Google, and local models</li>
                    <li>Tab-based conversations - Keep multiple chats open simultaneously</li>
                    <li>Context-aware search - Find relevant code and documentation</li>
                    <li>Code analysis - Get insights about your repository structure</li>
                </ul>
                
                <h2>⌨️ Keyboard Shortcuts</h2>
                <table class="shortcut-table">
                    <tr>
                        <td class="key">Ctrl+T</td>
                        <td>Open new conversation tab</td>
                    </tr>
                    <tr>
                        <td class="key">Ctrl+W</td>
                        <td>Close current tab</td>
                    </tr>
                    <tr>
                        <td class="key">Ctrl+F</td>
                        <td>Find in conversation</td>
                    </tr>
                    <tr>
                        <td class="key">Ctrl+,</td>
                        <td>Open preferences</td>
                    </tr>
                    <tr>
                        <td class="key">Ctrl+Q</td>
                        <td>Exit application</td>
                    </tr>
                </table>
                
                <h2>💡 Tips</h2>
                <ul class="feature-list">
                    <li>Use the search bar to quickly find documentation across all repositories</li>
                    <li>Right-click on repositories or LLM clients for additional options</li>
                    <li>Each tab maintains its own conversation history</li>
                    <li>Switch between different LLM models for different types of questions</li>
                </ul>
            </div>
        </body>
        </html>
        """
