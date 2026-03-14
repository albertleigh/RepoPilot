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
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from core.context import AppContext
from ui.main_window import MainWindow

LOG_FORMAT = "%(asctime)s  %(levelname)-8s  [%(name)s]  %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
LOG_BACKUP_COUNT = 5  # keep 5 rotated files


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
    """Reload all UI modules and recreate the main window.

    Modules are reloaded bottom-up: leaf modules first, composites last.
    """
    geometry = state['window'].geometry()

    # -- Import every UI module (for reload) --
    from ui import event_bridge

    # left_panel_components (leaves)
    from ui.left_panel_components import (
        collapsible_section, repo_tree, llm_tree, mcp_tree, skill_tree,
    )
    from ui import left_panel

    # llm dialogs
    from ui.llm import configure_llm_dialog, create_llm_dialog

    # tabs_item (leaves → composites)
    from ui.tabs_item import base_tab, chat_tab, welcome_tab, engineer_chat_tab

    # tabs_manager (leaves → composites)
    from ui.tabs_manager import grid_item_container
    from ui.tabs_manager import manager as tabs_mgr_module

    from ui import search_bar, menu_bar
    from ui import debug_panel
    from ui import main_window as mw_module

    # -- Reload in dependency order (leaves first) --
    importlib.reload(event_bridge)

    importlib.reload(collapsible_section)
    importlib.reload(repo_tree)
    importlib.reload(llm_tree)
    importlib.reload(mcp_tree)
    importlib.reload(skill_tree)
    importlib.reload(left_panel)

    importlib.reload(configure_llm_dialog)
    importlib.reload(create_llm_dialog)

    importlib.reload(base_tab)
    importlib.reload(chat_tab)
    importlib.reload(welcome_tab)
    importlib.reload(engineer_chat_tab)

    importlib.reload(grid_item_container)
    importlib.reload(tabs_mgr_module)

    importlib.reload(search_bar)
    importlib.reload(menu_bar)
    importlib.reload(debug_panel)
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
    app.setApplicationName("RepoPilot")

    # -- Application icon --
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "repopilot.ico"
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # -- Dependency injection context --
    ctx = AppContext()

    # -- Logging (rotated files under base_dir/logs/) --
    setup_logging(ctx.base_dir / "logs")

    window = MainWindow(ctx)

    # Add Ctrl+R shortcut for hot reload (only in development mode)
    if os.getenv('REPOPILOT_DEV', '').lower() in ('1', 'true', 'yes'):
        print("🔥 Hot reload enabled - Press Ctrl+R to reload UI changes")
        state = {'window': window, 'ctx': ctx}
        _bind_reload_shortcut(state)

    window.show()
    exit_code = app.exec()
    ctx.shutdown()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
