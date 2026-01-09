"""
Chat Tab Widget Container
Manages multiple chat tabs with VS Code-style drag-and-drop split view
"""
from PySide6.QtWidgets import (QWidget, QTabWidget, QTabBar, QMessageBox,
                               QVBoxLayout, QSplitter, QApplication, QStyle)
from PySide6.QtCore import Signal, Qt, QMimeData, QPoint, QRect
from PySide6.QtGui import QDrag, QMouseEvent, QPixmap, QPainter, QCursor, QFont
from .chat_tab_components import ChatTab, WelcomeTab


class DraggableTabBar(QTabBar):
    """Custom tab bar that supports drag and drop for splitting"""

    tab_drag_started = Signal(int, QTabBar)  # tab index, source tab bar
    tab_drop_requested = Signal(int, QPoint, QTabBar)  # tab index, global pos, source tab bar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setElideMode(Qt.ElideRight)
        self.setSelectionBehaviorOnRemove(QTabBar.SelectPreviousTab)
        self.drag_start_pos = None
        self.dragging_index = -1

    def mousePressEvent(self, event: QMouseEvent):
        """Store the starting position for drag detection"""
        if event.button() == Qt.LeftButton:
            self.drag_start_pos = event.pos()
            self.dragging_index = self.tabAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        """Initiate drag operation when moved far enough"""
        if not (event.buttons() & Qt.LeftButton):
            return
        if self.drag_start_pos is None:
            return

        # Check if we've moved far enough to start a drag
        if (event.pos() - self.drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return

        if self.dragging_index < 0:
            return

        # Start drag operation
        drag = QDrag(self)
        mime_data = QMimeData()
        mime_data.setText(f"tab_{self.dragging_index}")
        drag.setMimeData(mime_data)

        # Create a simple pixmap of the tab being dragged
        tab_rect = self.tabRect(self.dragging_index)
        pixmap = QPixmap(tab_rect.size())
        pixmap.fill(Qt.transparent)
        
        painter = QPainter(pixmap)
        painter.setOpacity(0.8)
        
        # Draw a rounded rectangle background
        painter.setBrush(self.palette().button())
        painter.setPen(self.palette().mid().color())
        painter.drawRoundedRect(pixmap.rect().adjusted(1, 1, -1, -1), 4, 4)
        
        # Draw the tab text
        painter.setPen(self.palette().buttonText().color())
        font = QFont()
        font.setPointSize(9)
        painter.setFont(font)
        tab_text = self.tabText(self.dragging_index)
        painter.drawText(pixmap.rect(), Qt.AlignCenter, tab_text)
        
        painter.end()
        
        # Set the pixmap and hotspot
        drag.setPixmap(pixmap)
        drag.setHotSpot(self.drag_start_pos - tab_rect.topLeft())
        
        # Set cursor to moving cursor
        QApplication.setOverrideCursor(QCursor(Qt.SizeAllCursor))

        # Emit signal that drag started
        self.tab_drag_started.emit(self.dragging_index, self)

        # Execute drag
        drag.exec(Qt.MoveAction)
        
        # Restore cursor
        QApplication.restoreOverrideCursor()

        self.drag_start_pos = None
        self.dragging_index = -1

    def dragEnterEvent(self, event):
        """Accept drag events"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("tab_"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop - reorder tabs or emit signal for splitting"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("tab_"):
            source = event.source()
            if isinstance(source, DraggableTabBar):
                tab_index = int(event.mimeData().text().split("_")[1])
                drop_pos = event.position().toPoint()
                target_index = self.tabAt(drop_pos)
                
                # Check if drop is on a tab (for reordering within same tab bar)
                if target_index >= 0 and source == self:
                    # Reorder within same tab bar
                    # Get the parent tab widget to move the tab
                    parent_widget = self.parent()
                    if isinstance(parent_widget, QTabWidget):
                        widget = parent_widget.widget(tab_index)
                        tab_text = parent_widget.tabText(tab_index)
                        
                        # Remove and reinsert at new position
                        parent_widget.removeTab(tab_index)
                        # Adjust target if we removed a tab before it
                        if tab_index < target_index:
                            target_index -= 1
                        parent_widget.insertTab(target_index, widget, tab_text)
                        parent_widget.setCurrentIndex(target_index)
                    event.acceptProposedAction()
                    return
                
                # Drop not on a tab or from different tab bar - emit for splitting
                global_pos = self.mapToGlobal(drop_pos)
                self.tab_drop_requested.emit(tab_index, global_pos, source)
                event.acceptProposedAction()


class SplittableTabWidget(QTabWidget):
    """Tab widget with draggable tab bar"""

    tab_dropped = Signal(int, QPoint, QTabBar)  # tab index, drop position, source bar

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabBar(DraggableTabBar())
        self.setTabsClosable(True)
        self.setMovable(True)
        self.setDocumentMode(True)
        self.setAcceptDrops(True)

        # Connect tab bar drop signal
        self.tabBar().tab_drop_requested.connect(self.tab_dropped.emit)

    def dragEnterEvent(self, event):
        """Accept drag events on the widget"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("tab_"):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        """Accept drag move events"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("tab_"):
            event.acceptProposedAction()

    def dropEvent(self, event):
        """Handle drop on the widget area (content, not tab bar)"""
        if event.mimeData().hasText() and event.mimeData().text().startswith("tab_"):
            source = event.source()
            if isinstance(source, DraggableTabBar):
                tab_index = int(event.mimeData().text().split("_")[1])
                drop_pos = event.position().toPoint()
                
                # Check if drop is on tab bar area
                tab_bar = self.tabBar()
                tab_bar_rect = tab_bar.geometry()
                
                if tab_bar_rect.contains(drop_pos):
                    # Drop on tab bar - don't split, just ignore (Qt handles reordering)
                    event.ignore()
                    return
                
                # Drop on content area - emit for potential split
                global_pos = self.mapToGlobal(drop_pos)
                self.tab_dropped.emit(tab_index, global_pos, source)
                event.acceptProposedAction()


class ChatTabWidget(QWidget):
    """Tab widget container with VS Code-style drag-and-drop split view"""

    # Signals
    tab_changed = Signal(int)
    all_tabs_closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._add_welcome_tab()

    def _setup_ui(self):
        """Setup the UI with splitter support"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Main splitter for horizontal splits
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setChildrenCollapsible(True)

        # Create initial tab widget
        self.tab_widgets = []
        self._create_tab_widget()

        layout.addWidget(self.splitter)

    def _create_tab_widget(self):
        """Create a new tab widget and add to splitter"""
        tab_widget = SplittableTabWidget()
        tab_widget.tabCloseRequested.connect(lambda idx: self._close_tab(idx, tab_widget))
        tab_widget.currentChanged.connect(self.tab_changed.emit)

        # Connect drag and drop signals
        tab_bar = tab_widget.tabBar()
        tab_bar.tab_drag_started.connect(self._on_tab_drag_started)
        tab_widget.tab_dropped.connect(lambda idx, pos, bar: self._on_tab_drop_requested(idx, pos, bar, tab_widget))

        self.tab_widgets.append(tab_widget)
        self.splitter.addWidget(tab_widget)

        return tab_widget

    def _on_tab_drag_started(self, index: int, source_bar: DraggableTabBar):
        """Handle when a tab drag is started"""
        self.drag_source_index = index
        self.drag_source_bar = source_bar

    def _on_tab_drop_requested(self, index: int, global_pos: QPoint, source_bar: DraggableTabBar,
                               target_widget: SplittableTabWidget):
        """Handle tab drop - determine if we should split or just reorder"""
        if target_widget is None:
            return

        # Find source tab widget
        source_widget = None
        for widget in self.tab_widgets:
            if widget.tabBar() == source_bar:
                source_widget = widget
                break

        if source_widget is None:
            return

        # Get the drop position relative to the target widget
        local_pos = target_widget.mapFromGlobal(global_pos)
        widget_rect = target_widget.rect()

        # Determine if we should create a split
        # Split if dropped on the edges (25% from left or right)
        split_threshold = max(widget_rect.width() * 0.25, 80)  # At least 80px or 25%
        should_split = False
        split_right = False

        # Check if drop is on the edges
        if local_pos.x() < split_threshold:
            should_split = True
            split_right = False
        elif local_pos.x() > widget_rect.width() - split_threshold:
            should_split = True
            split_right = True

        # Create split if needed and we haven't reached limit
        if should_split and len(self.tab_widgets) < 3:
            self._split_and_move_tab(source_widget, index, target_widget, split_right)
        elif source_widget != target_widget:
            # Move tab to another existing pane
            self._move_tab_between_widgets(source_widget, index, target_widget)

    def _split_and_move_tab(self, source_widget: QTabWidget, tab_index: int,
                            reference_widget: QTabWidget, split_right: bool):
        """Create a new split and move the tab there"""
        # Get tab info before removing
        widget = source_widget.widget(tab_index)
        tab_text = source_widget.tabText(tab_index)

        # Create new tab widget
        new_tab_widget = self._create_tab_widget()

        # Insert it in the splitter at the right position
        ref_index = self.splitter.indexOf(reference_widget)
        if split_right:
            insert_index = ref_index + 1
        else:
            insert_index = ref_index

        # Move the new widget to the correct position
        self.splitter.insertWidget(insert_index, new_tab_widget)

        # Remove from source
        source_widget.removeTab(tab_index)

        # Add to new widget
        new_tab_widget.addTab(widget, tab_text)
        new_tab_widget.setCurrentIndex(0)

        # Equal sizes for all widgets
        sizes = [100] * len(self.tab_widgets)
        self.splitter.setSizes(sizes)

        # Clean up empty widgets
        self._cleanup_empty_widgets()

    def _move_tab_between_widgets(self, source_widget: QTabWidget, tab_index: int,
                                  target_widget: QTabWidget):
        """Move a tab from one widget to another"""
        widget = source_widget.widget(tab_index)
        tab_text = source_widget.tabText(tab_index)

        source_widget.removeTab(tab_index)
        target_widget.addTab(widget, tab_text)
        target_widget.setCurrentIndex(target_widget.count() - 1)

        self._cleanup_empty_widgets()

    def _cleanup_empty_widgets(self):
        """Remove empty tab widgets, but keep at least one"""
        for widget in self.tab_widgets[:]:  # Iterate over copy
            if widget.count() == 0 and len(self.tab_widgets) > 1:
                self.tab_widgets.remove(widget)
                widget.deleteLater()
            # elif widget.count() == 0:
            # Last widget - add welcome tab
            # self._add_welcome_tab(widget)

    def _add_welcome_tab(self, tab_widget=None):
        """Add a welcome/placeholder tab"""
        if tab_widget is None:
            tab_widget = self.tab_widgets[0] if self.tab_widgets else None
        if tab_widget is None:
            return
        welcome_tab = WelcomeTab()
        tab_widget.addTab(welcome_tab, "🏠 Welcome")

    def add_chat_tab(self, repo_name: str = "New Repository", llm_name: str = "Default LLM"):
        """Add a new chat tab to the first widget"""
        chat_tab = ChatTab(repo_name=repo_name, llm_name=llm_name)

        # Connect signals
        chat_tab.message_sent.connect(lambda msg: self._handle_message(msg, chat_tab))

        # Add to first tab widget
        tab_widget = self.tab_widgets[0] if self.tab_widgets else None
        if tab_widget:
            index = tab_widget.addTab(chat_tab, f"💬 {chat_tab.get_tab_title()}")
            tab_widget.setCurrentIndex(index)

        return chat_tab

    def _close_tab(self, index: int, tab_widget: QTabWidget):
        """Close a tab at the given index"""
        # Count total tabs across all widgets
        total_tabs = sum(w.count() for w in self.tab_widgets)

        if total_tabs <= 1:
            reply = QMessageBox.question(
                self,
                "Close Last Tab",
                "This is the last tab. Close it?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                return

        widget = tab_widget.widget(index)
        tab_widget.removeTab(index)
        widget.deleteLater()

        # Clean up empty widgets
        self._cleanup_empty_widgets()

        if total_tabs <= 1:
            self.all_tabs_closed.emit()

    def close_current_tab(self):
        """Close the currently active tab"""
        for tab_widget in self.tab_widgets:
            if tab_widget.currentWidget():
                current_index = tab_widget.currentIndex()
                if current_index >= 0:
                    self._close_tab(current_index, tab_widget)
                    break

    def _handle_message(self, message: str, chat_tab: ChatTab):
        """Handle message sent from a chat tab"""
        # Placeholder for actual message handling
        pass

    def get_current_chat_tab(self) -> ChatTab:
        """Get the currently active chat tab"""
        for tab_widget in self.tab_widgets:
            widget = tab_widget.currentWidget()
            if isinstance(widget, ChatTab):
                return widget
        return None

    def get_all_chat_tabs(self) -> list:
        """Get all chat tabs from all widgets"""
        tabs = []
        for tab_widget in self.tab_widgets:
            for i in range(tab_widget.count()):
                widget = tab_widget.widget(i)
                if isinstance(widget, ChatTab):
                    tabs.append(widget)
        return tabs
