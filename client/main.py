"""
Qt Frontend Application
Main entry point for the PySide6 GUI application
"""
import logging
import logging.handlers
import sys
import os
import importlib
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QKeySequence, QShortcut
from core.context import AppContext
from ui.main_window import MainWindow

LOG_FORMAT = "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
LOG_BACKUP_COUNT = 5             # keep 5 rotated files


def setup_logging(log_dir: Path) -> None:
    """Configure root logger with rotating file + optional console output."""
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # -- Rotating file handler (all levels) --
    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_dir / "repocode.log",
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(file_handler)

    # -- Console handler (INFO+ in prod, DEBUG in dev) --
    console = logging.StreamHandler(sys.stderr)
    if os.getenv("REPOCODE_DEV", "").lower() in ("1", "true", "yes"):
        console.setLevel(logging.DEBUG)
    else:
        console.setLevel(logging.INFO)
    console.setFormatter(logging.Formatter(LOG_FORMAT, LOG_DATE_FORMAT))
    root.addHandler(console)

    # Quieten noisy third-party loggers
    logging.getLogger("PySide6").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)

    logging.getLogger(__name__).info(
        "Logging initialised – file: %s", log_dir / "repocode.log",
    )


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
    new_window = mw_module.MainWindow(state['ctx'])
    new_window.setGeometry(geometry)
    new_window.show()

    # Update state and rebind shortcut to the new window
    state['window'] = new_window
    _bind_reload_shortcut(state)
    print("🔄 UI reloaded successfully")


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Repo Wiki App")
    
    # -- Dependency injection context --
    ctx = AppContext()

    # -- Logging (rotated files under base_dir/logs/) --
    setup_logging(ctx.base_dir / "logs")

    window = MainWindow(ctx)

    # Add Ctrl+R shortcut for hot reload (only in development mode)
    if os.getenv('REPOCODE_DEV', '').lower() in ('1', 'true', 'yes'):
        print("🔥 Hot reload enabled - Press Ctrl+R to reload UI changes")
        state = {'window': window, 'ctx': ctx}
        _bind_reload_shortcut(state)

    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
