"""
Base Tab
Abstract base class for all tab widgets hosted in the :class:`TabsManager`.
"""
from __future__ import annotations

from abc import abstractmethod

from PySide6.QtWidgets import QWidget
from PySide6.QtCore import Signal


class BaseTab(QWidget):
    """Common interface that every tab widget must implement.

    Sub-classes **must** override :meth:`get_tab_title` and may
    optionally override :attr:`tab_icon` to control the icon shown
    in the tab bar.

    See ``TABS.md`` in this package for the full contract.
    """

    tab_close_requested = Signal()

    # Override in sub-classes to provide a custom emoji/icon prefix.
    tab_icon: str = ""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

    @abstractmethod
    def get_tab_title(self) -> str:
        """Return a short display title for the tab bar."""
        ...

    def tab_label(self) -> str:
        """Return the full label ``icon + title`` used by TabsManager."""
        icon = f"{self.tab_icon} " if self.tab_icon else ""
        return f"{icon}{self.get_tab_title()}"
