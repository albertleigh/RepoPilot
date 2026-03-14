"""
Tabs Manager
Grid-based tab management with VS Code-style split views and drag-drop.
Replaces the old ChatTabWidget.

Layout model (recursively nested splitters):

    TabsManager
    └── QSplitter (root – starts Horizontal)
        ├── GridItemContainer
        ├── QSplitter (Vertical)
        │   ├── GridItemContainer
        │   └── GridItemContainer
        └── QSplitter (Vertical)
            ├── GridItemContainer
            └── QSplitter (Horizontal)
                ├── GridItemContainer
                └── GridItemContainer

Each split direction toggles orientation:
  - LEFT / RIGHT → insert sibling in the same parent (or wrap in Horizontal)
  - TOP / BOTTOM → insert sibling in the same parent (or wrap in Vertical)

This allows arbitrary nesting (1×2, 2×2, 4×3, etc.) without limits.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSplitter, QApplication
from PySide6.QtCore import Signal, Qt

from client.ui.tabs_manager.grid_item_container import GridItemContainer, DropZone
from client.ui.tabs_item import BaseTab, WelcomeTab


class TabsManager(QWidget):
    """Grid-based manager for tab containers with VS Code-style split views."""

    tab_changed = Signal(int)
    all_tabs_closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._containers: dict[str, GridItemContainer] = {}
        self._active_container_id: str | None = None
        self._setup_ui()
        self._add_welcome_tab()

        # Track focus changes globally to update active container
        QApplication.instance().focusChanged.connect(self._on_app_focus_changed)

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Root splitter – starts horizontal but may be replaced as needed
        self.root_splitter = QSplitter(Qt.Horizontal)
        layout.addWidget(self.root_splitter)

        container = self._create_container()
        self.root_splitter.addWidget(container)

    def _create_container(self) -> GridItemContainer:
        container = GridItemContainer()
        cid = container.container_id

        container.split_requested.connect(self._on_split_requested)
        container.tab_move_requested.connect(self._on_tab_move_requested)
        container.container_empty.connect(self._on_container_empty)
        container.tab_changed.connect(
            lambda idx, _cid=cid: self._on_container_tab_changed(_cid, idx))

        self._containers[cid] = container
        return container

    # ------------------------------------------------------------------
    # Tree helpers
    # ------------------------------------------------------------------

    def _find_parent_splitter(self, container_id: str):
        """Walk the splitter tree and return (parent_splitter, index_in_parent)
        for the container, or (None, -1)."""
        container = self._containers.get(container_id)
        if container is None:
            return None, -1
        return self._find_widget_in_tree(self.root_splitter, container)

    def _find_widget_in_tree(self, splitter: QSplitter, target: QWidget):
        """Recursively find *target* in the splitter tree.
        Returns (parent_splitter, index) or (None, -1)."""
        for i in range(splitter.count()):
            child = splitter.widget(i)
            if child is target:
                return splitter, i
            if isinstance(child, QSplitter):
                result = self._find_widget_in_tree(child, target)
                if result[0] is not None:
                    return result
        return None, -1

    def _get_first_container(self) -> GridItemContainer | None:
        """Return the first GridItemContainer found via depth-first walk."""
        return self._dfs_first_container(self.root_splitter)

    def _dfs_first_container(self, splitter: QSplitter) -> GridItemContainer | None:
        for i in range(splitter.count()):
            w = splitter.widget(i)
            if isinstance(w, GridItemContainer):
                return w
            if isinstance(w, QSplitter):
                r = self._dfs_first_container(w)
                if r:
                    return r
        return None

    # ------------------------------------------------------------------
    # Signal handlers
    # ------------------------------------------------------------------

    def _on_app_focus_changed(self, _old: QWidget, new: QWidget):
        """Walk up from the newly focused widget to find its GridItemContainer."""
        w = new
        while w is not None:
            if isinstance(w, GridItemContainer) and w.container_id in self._containers:
                self._active_container_id = w.container_id
                return
            w = w.parentWidget()

    def _on_container_tab_changed(self, container_id: str, index: int):
        self._active_container_id = container_id
        self.tab_changed.emit(index)

    def _on_split_requested(self, src_cid: str, src_idx: int,
                            tgt_cid: str, zone: str):
        src = self._containers.get(src_cid)
        tgt = self._containers.get(tgt_cid)
        if not src or not tgt:
            return

        widget, title = src.remove_tab(src_idx)

        new_container = self._create_container()
        new_container.add_tab(widget, title)

        # Determine required orientation for the split
        if zone in (DropZone.LEFT, DropZone.RIGHT):
            needed_orientation = Qt.Horizontal
        else:  # TOP / BOTTOM
            needed_orientation = Qt.Vertical

        insert_before = zone in (DropZone.LEFT, DropZone.TOP)

        parent, idx = self._find_parent_splitter(tgt_cid)
        if parent is None:
            return

        if parent.orientation() == needed_orientation:
            # Parent already has the right orientation – just insert a sibling
            insert_idx = idx if insert_before else idx + 1
            parent.insertWidget(insert_idx, new_container)
            self._equalize(parent)
        else:
            # Need to wrap the target in a sub-splitter with the right orientation
            sub = QSplitter(needed_orientation)
            # Replace target in parent with the sub-splitter
            parent.insertWidget(idx, sub)
            # Move target into sub (removeWidget alone doesn't work reliably,
            # addWidget re-parents it out of the old splitter automatically)
            sub.addWidget(tgt)
            if insert_before:
                sub.insertWidget(0, new_container)
            else:
                sub.addWidget(new_container)
            self._equalize(sub)
            self._equalize(parent)

        if src.tab_count() == 0:
            self._remove_container(src_cid)

    def _on_tab_move_requested(self, src_cid: str, src_idx: int,
                               tgt_cid: str, tgt_idx: int):
        src = self._containers.get(src_cid)
        tgt = self._containers.get(tgt_cid)
        if not src or not tgt or src_cid == tgt_cid:
            return

        widget, title = src.remove_tab(src_idx)
        tgt.insert_tab(tgt_idx, widget, title)

        if src.tab_count() == 0:
            self._remove_container(src_cid)

    def _on_container_empty(self, container_id: str):
        """All tabs in a container were closed by the user."""
        if len(self._containers) <= 1:
            container = self._containers.get(container_id)
            if container:
                container.add_tab(WelcomeTab(), "\U0001F3E0 Welcome")
            self.all_tabs_closed.emit()
            return
        self._remove_container(container_id)

    # ------------------------------------------------------------------
    # Container management
    # ------------------------------------------------------------------

    def _remove_container(self, container_id: str):
        if len(self._containers) <= 1:
            return

        container = self._containers.pop(container_id, None)
        if not container:
            return

        parent, _ = self._find_widget_in_tree(self.root_splitter, container)
        if parent is None:
            return

        container.setParent(None)
        container.deleteLater()

        # Collapse parent splitters that have only one child left
        self._collapse_single_child_splitters(self.root_splitter)

    def _collapse_single_child_splitters(self, splitter: QSplitter):
        """Recursively collapse splitters that have only a single child
        by promoting that child up to the grandparent.  Also remove
        empty splitters."""
        i = 0
        while i < splitter.count():
            child = splitter.widget(i)
            if isinstance(child, QSplitter):
                # Recurse first
                self._collapse_single_child_splitters(child)
                if child.count() == 0:
                    child.setParent(None)
                    child.deleteLater()
                    continue  # don't increment i; indices shifted
                if child.count() == 1:
                    # Promote the sole child up into our splitter
                    sole = child.widget(0)
                    splitter.insertWidget(i, sole)
                    child.setParent(None)
                    child.deleteLater()
                    continue  # re-check at same index
            i += 1

    @staticmethod
    def _equalize(splitter: QSplitter):
        n = splitter.count()
        if n > 0:
            splitter.setSizes([100] * n)

    # ------------------------------------------------------------------
    # Public API  (compatible with old ChatTabWidget)
    # ------------------------------------------------------------------

    def add_tab(self, tab: BaseTab) -> BaseTab:
        """Add a :class:`BaseTab` to the active container.

        The tab's :meth:`~BaseTab.tab_label` is used as the title shown
        in the tab bar.  Returns the same *tab* for convenience.
        """
        container = self._containers.get(self._active_container_id)
        if container is None:
            container = self._get_first_container()
        if container:
            container.add_tab(tab, tab.tab_label())
            self._active_container_id = container.container_id
        return tab

    def add_tab_split(self, tab: BaseTab, orientation: Qt.Orientation = Qt.Horizontal) -> BaseTab:
        """Add *tab* in a **new** container beside the active one.

        If there is only a single empty welcome container, the tab is placed
        there instead of creating an unnecessary split.

        *orientation* controls the split direction (default: side-by-side).
        Returns the same *tab* for convenience.
        """
        active = self._containers.get(self._active_container_id)
        if active is None:
            active = self._get_first_container()
        if active is None:
            return self.add_tab(tab)

        new_container = self._create_container()
        new_container.add_tab(tab, tab.tab_label())

        parent, idx = self._find_widget_in_tree(self.root_splitter, active)
        if parent is None:
            return self.add_tab(tab)

        if parent.orientation() == orientation:
            parent.insertWidget(idx + 1, new_container)
            self._equalize(parent)
        else:
            sub = QSplitter(orientation)
            parent.insertWidget(idx, sub)
            sub.addWidget(active)
            sub.addWidget(new_container)
            self._equalize(sub)
            self._equalize(parent)

        self._active_container_id = new_container.container_id
        return tab

    def find_tab(self, tab_type: type, predicate=None) -> BaseTab | None:
        """Find the first open tab matching *tab_type* and optional *predicate*.

        *predicate* is an optional callable ``(tab) -> bool``.
        Returns ``None`` when no match is found.
        """
        for c in self._containers.values():
            for i in range(c.tab_count()):
                w = c.tab_widget.widget(i)
                if isinstance(w, tab_type):
                    if predicate is None or predicate(w):
                        return w
        return None

    def focus_tab(self, tab: BaseTab) -> bool:
        """Bring an existing *tab* into focus.  Returns ``True`` on success."""
        for c in self._containers.values():
            for i in range(c.tab_count()):
                if c.tab_widget.widget(i) is tab:
                    c.tab_widget.setCurrentIndex(i)
                    self._active_container_id = c.container_id
                    return True
        return False

    def close_current_tab(self):
        container = self._containers.get(self._active_container_id)
        if container is None:
            container = self._get_first_container()
        if container and container.current_index() >= 0:
            container._on_tab_close(container.current_index())

    def get_current_tab(self) -> BaseTab | None:
        """Return the active tab widget, or ``None``."""
        container = self._containers.get(self._active_container_id)
        if container:
            w = container.current_widget()
            if isinstance(w, BaseTab):
                return w
        return None

    def get_all_tabs(self, tab_type: type | None = None) -> list[BaseTab]:
        """Return all open tabs, optionally filtered by *tab_type*."""
        tabs: list[BaseTab] = []
        for c in self._containers.values():
            for i in range(c.tab_count()):
                w = c.tab_widget.widget(i)
                if isinstance(w, BaseTab):
                    if tab_type is None or isinstance(w, tab_type):
                        tabs.append(w)
        return tabs

    def _add_welcome_tab(self):
        container = self._get_first_container()
        if container:
            tab = WelcomeTab()
            container.add_tab(tab, tab.tab_label())
