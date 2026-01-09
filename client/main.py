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


def reload_app(main_window):
    """Reload all modules and recreate the main window"""
    # Get the position and size before closing
    geometry = main_window.geometry()

    # Reload modules
    from ui import main_window as mw_module
    from ui import menu_bar, search_bar, left_panel, chat_tab_widget
    from ui.left_panel_components import repo_tree, llm_tree, collapsible_section
    from ui.chat_tab_components import chat_tab, welcome_tab

    importlib.reload(collapsible_section)
    importlib.reload(repo_tree)
    importlib.reload(llm_tree)
    importlib.reload(left_panel)
    importlib.reload(chat_tab)
    importlib.reload(welcome_tab)
    importlib.reload(chat_tab_widget)
    importlib.reload(search_bar)
    importlib.reload(menu_bar)
    importlib.reload(mw_module)

    # Close old and create new
    main_window.close()
    new_window = mw_module.MainWindow()
    new_window.setGeometry(geometry)
    new_window.show()
    return new_window


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Repo Wiki App")
    
    window = MainWindow()

    # Add Ctrl+R shortcut for hot reload (only in development mode)
    if os.getenv('REPOWIKI_DEV', '').lower() in ('1', 'true', 'yes'):
        print("🔥 Hot reload enabled - Press Ctrl+R to reload UI changes")
        reload_shortcut = QShortcut(QKeySequence("Ctrl+R"), window)
        reload_shortcut.activated.connect(lambda: globals().update({'window': reload_app(window)}))

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
