"""
Qt Frontend Application
Main entry point for the PySide6 GUI application
"""
import sys
import os
import importlib
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeySequence, QShortcut
from ui.main_window import MainWindow


def _bind_reload_shortcut(state):
    """Bind Ctrl+R reload shortcut to the current window"""
    shortcut = QShortcut(QKeySequence("Ctrl+R"), state['window'])
    shortcut.activated.connect(lambda: reload_app(state))


def reload_app(state):
    """Reload all modules and recreate the main window"""
    # Get the position and size before closing
    geometry = state['window'].geometry()

    # Reload modules
    from ui import main_window as mw_module
    from ui import menu_bar, search_bar, left_panel, tabs_manager
    from ui.left_panel_components import repo_tree, llm_tree, collapsible_section
    from ui.tabs_item import chat_tab, welcome_tab

    importlib.reload(collapsible_section)
    importlib.reload(repo_tree)
    importlib.reload(llm_tree)
    importlib.reload(left_panel)
    importlib.reload(chat_tab)
    importlib.reload(welcome_tab)
    importlib.reload(tabs_manager)
    importlib.reload(search_bar)
    importlib.reload(menu_bar)
    importlib.reload(mw_module)

    # Close old and create new
    state['window'].close()
    new_window = mw_module.MainWindow()
    new_window.setGeometry(geometry)
    new_window.show()

    # Update state and rebind shortcut to the new window
    state['window'] = new_window
    _bind_reload_shortcut(state)
    print("🔄 UI reloaded successfully")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Repo Wiki App")
    
    window = MainWindow()

    # Add Ctrl+R shortcut for hot reload (only in development mode)
    if os.getenv('REPOCODE_DEV', '').lower() in ('1', 'true', 'yes'):
        print("🔥 Hot reload enabled - Press Ctrl+R to reload UI changes")
        state = {'window': window}
        _bind_reload_shortcut(state)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
