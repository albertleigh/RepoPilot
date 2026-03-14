"""
Welcome Tab Component
Landing page shown when application starts or when all tabs are closed
"""
from PySide6.QtWidgets import QVBoxLayout, QTextBrowser
from PySide6.QtCore import Qt

from .base_tab import BaseTab


class WelcomeTab(BaseTab):
    """Welcome/landing page widget without chat functionality"""

    tab_icon = "\U0001F3E0"  # 🏠
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def get_tab_title(self) -> str:
        return "Welcome"
    
    def setup_ui(self):
        """Create welcome tab UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Use QTextBrowser for rich text display (read-only, no input)
        self.content_display = QTextBrowser()
        self.content_display.setOpenExternalLinks(True)
        self.content_display.setHtml(self._get_welcome_content())
        
        layout.addWidget(self.content_display)
    
    def _get_palette_colors(self) -> dict:
        """Extract current palette colors for use in HTML content"""
        palette = self.palette()
        def css_rgb(color):
            return f"rgb({color.red()}, {color.green()}, {color.blue()})"

        bg = palette.window().color()
        fg = palette.windowText().color()
        base = palette.base().color()
        alt_base = palette.alternateBase().color()
        highlight = palette.highlight().color()
        mid = palette.mid().color()
        # Slightly shift background for container contrast
        lighter_bg = bg.lighter(110) if bg.lightness() < 128 else bg.darker(105)
        subtle_bg = bg.lighter(120) if bg.lightness() < 128 else bg.darker(110)
        muted_fg = fg.lighter(150) if fg.lightness() < 128 else fg.darker(150)

        return {
            "bg": css_rgb(bg),
            "fg": css_rgb(fg),
            "base": css_rgb(base),
            "alt_base": css_rgb(alt_base),
            "highlight": css_rgb(highlight),
            "mid": css_rgb(mid),
            "container_bg": css_rgb(lighter_bg),
            "subtle_bg": css_rgb(subtle_bg),
            "muted_fg": css_rgb(muted_fg),
        }

    def _get_welcome_content(self) -> str:
        """Generate welcome page HTML content using current palette colors"""
        c = self._get_palette_colors()
        return f"""
        <html>
        <head>
            <style>
                body {{
                    font-family: 'Segoe UI', Arial, sans-serif;
                    padding: 40px;
                    background-color: {c['bg']};
                    color: {c['fg']};
                }}
                .container {{
                    max-width: 820px;
                    margin: 0 auto;
                    background-color: {c['container_bg']};
                    padding: 48px 44px;
                    border-radius: 12px;
                    border: 1px solid {c['mid']};
                }}
                h1 {{
                    color: {c['fg']};
                    text-align: center;
                    margin-bottom: 4px;
                    font-size: 28px;
                    font-weight: 700;
                }}
                .subtitle {{
                    text-align: center;
                    color: {c['muted_fg']};
                    margin-bottom: 36px;
                    font-size: 16px;
                    line-height: 1.5;
                }}
                h2 {{
                    color: {c['fg']};
                    border-bottom: 2px solid {c['highlight']};
                    padding-bottom: 8px;
                    margin-top: 32px;
                    font-size: 18px;
                }}
                .hero {{
                    text-align: center;
                    margin-bottom: 8px;
                }}
                .hero .icon {{
                    font-size: 56px;
                    margin-bottom: 4px;
                }}
                .getting-started {{
                    background-color: {c['subtle_bg']};
                    padding: 22px 26px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border: 1px solid {c['mid']};
                }}
                .getting-started ol {{
                    margin: 10px 0 0 0;
                    padding-left: 22px;
                }}
                .getting-started li {{
                    margin: 10px 0;
                    line-height: 1.6;
                }}
                .card-grid {{
                    display: flex;
                    flex-wrap: wrap;
                    gap: 14px;
                    margin: 18px 0;
                }}
                .card {{
                    flex: 1 1 45%;
                    background-color: {c['subtle_bg']};
                    border: 1px solid {c['mid']};
                    border-radius: 8px;
                    padding: 16px 18px;
                }}
                .card .card-title {{
                    font-weight: 600;
                    margin-bottom: 4px;
                }}
                .card .card-desc {{
                    color: {c['muted_fg']};
                    font-size: 13px;
                    line-height: 1.5;
                }}
                .shortcut-table {{
                    width: 100%;
                    margin: 16px 0;
                    border-collapse: collapse;
                }}
                .shortcut-table td {{
                    padding: 9px 12px;
                    border: 1px solid {c['mid']};
                    font-size: 13px;
                }}
                .shortcut-table .key {{
                    background-color: {c['subtle_bg']};
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-weight: bold;
                    width: 120px;
                }}
                kbd {{
                    background-color: {c['subtle_bg']};
                    border: 1px solid {c['mid']};
                    border-radius: 3px;
                    padding: 1px 6px;
                    font-family: 'Consolas', 'Courier New', monospace;
                    font-size: 12px;
                }}
                .footer {{
                    text-align: center;
                    color: {c['muted_fg']};
                    font-size: 12px;
                    margin-top: 32px;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="hero">
                    <div class="icon">🤖</div>
                    <h1>RepoPilot</h1>
                </div>
                <p class="subtitle">
                    AI-powered coding agent that lives in your desktop.<br>
                    Explore, understand, and transform any codebase &mdash; backed by the LLM of your choice.
                </p>

                <div class="getting-started">
                    <h2 style="margin-top: 0; border: none; padding: 0;">🚀 Getting Started</h2>
                    <ol>
                        <li><strong>Add a Repository</strong> &mdash; click <strong>+</strong> in the Repositories panel and select a folder.</li>
                        <li><strong>Configure an LLM</strong> &mdash; click <strong>+</strong> in the LLM Clients panel and enter your provider credentials.</li>
                        <li><strong>Start the Engineer</strong> &mdash; right-click the repo and choose <em>Start Engineer</em>.</li>
                        <li><strong>Chat</strong> &mdash; ask the agent to explain, refactor, or extend your code.</li>
                    </ol>
                </div>

                <h2>✨ Capabilities</h2>
                <table class="card-grid" cellspacing="0" cellpadding="0" style="border: none;">
                    <tr>
                        <td class="card" style="border-radius: 8px;">
                            <div class="card-title">🛠️ Engineer Agent</div>
                            <div class="card-desc">Autonomous coding agent that reads, edits, and creates files inside your repo.</div>
                        </td>
                        <td class="card" style="border-radius: 8px;">
                            <div class="card-title">📋 Project Manager</div>
                            <div class="card-desc">High-level planning agent that coordinates tasks across repositories.</div>
                        </td>
                    </tr>
                    <tr>
                        <td class="card" style="border-radius: 8px;">
                            <div class="card-title">🤖 Bring Your Own LLM</div>
                            <div class="card-desc">Azure OpenAI, Anthropic Claude, Kimi K2, and more &mdash; connect any provider.</div>
                        </td>
                        <td class="card" style="border-radius: 8px;">
                            <div class="card-title">🔌 MCP &amp; Skills</div>
                            <div class="card-desc">Extend agents with MCP tool servers and custom SKILL.md knowledge files.</div>
                        </td>
                    </tr>
                    <tr>
                        <td class="card" style="border-radius: 8px;">
                            <div class="card-title">📂 Multi-Repo Workspace</div>
                            <div class="card-desc">Register multiple repositories and switch between them instantly.</div>
                        </td>
                        <td class="card" style="border-radius: 8px;">
                            <div class="card-title">🔒 Fully Local</div>
                            <div class="card-desc">No cloud relay &mdash; LLM calls go directly from your machine to the provider.</div>
                        </td>
                    </tr>
                </table>

                <h2>⌨️ Keyboard Shortcuts</h2>
                <table class="shortcut-table">
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
                        <td class="key">F12</td>
                        <td>Toggle debug panel</td>
                    </tr>
                    <tr>
                        <td class="key">Ctrl+Q</td>
                        <td>Exit application</td>
                    </tr>
                </table>

                <p class="footer">&copy; 2026 RepoPilot Contributors &middot; Version 0.0.1</p>
            </div>
        </body>
        </html>
        """
