"""
Grid Item Container
Container widget holding a QTabWidget with drag-and-drop support
and a visual overlay for grid split zone indication.
"""
from PySide6.QtWidgets import (QWidget, QTabWidget, QTabBar, QVBoxLayout,
                                QApplication)
from PySide6.QtCore import Signal, Qt, QMimeData, QPoint, QRect
from PySide6.QtGui import (QDrag, QMouseEvent, QPixmap, QPainter,
                            QFont, QColor, QPen, QBrush)
import uuid


TAB_MIME_TYPE = "application/x-repocode-tab"


class DropZone:
    """Drop zone identifiers for split operations."""
    NONE = "none"
    CENTER = "center"
    LEFT = "left"
    RIGHT = "right"
    TOP = "top"
    BOTTOM = "bottom"


class DropOverlay(QWidget):
    """Transparent overlay showing a VS Code-style split zone preview
    with a central compass indicator and highlighted destination area."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_zone = DropZone.NONE
        self.setVisible(False)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)

    # -- zone detection --

    def get_zone_at(self, pos: QPoint) -> str:
        """Determine the drop zone for *pos* (in overlay coordinates)."""
        w, h = self.width(), self.height()
        if w == 0 or h == 0:
            return DropZone.CENTER

        rx = pos.x() / w
        ry = pos.y() / h

        # Inner 50 % → centre
        if 0.25 <= rx <= 0.75 and 0.25 <= ry <= 0.75:
            return DropZone.CENTER

        # Otherwise closest edge wins
        dists = {
            DropZone.LEFT: rx,
            DropZone.RIGHT: 1.0 - rx,
            DropZone.TOP: ry,
            DropZone.BOTTOM: 1.0 - ry,
        }
        return min(dists, key=dists.get)

    # -- preview geometry --

    def _preview_rect(self) -> QRect:
        """Rectangle showing where the tab will land."""
        w, h = self.width(), self.height()
        m = 4
        rects = {
            DropZone.LEFT:   QRect(m, m, w // 2 - m, h - 2 * m),
            DropZone.RIGHT:  QRect(w // 2, m, w // 2 - m, h - 2 * m),
            DropZone.TOP:    QRect(m, m, w - 2 * m, h // 2 - m),
            DropZone.BOTTOM: QRect(m, h // 2, w - 2 * m, h // 2 - m),
            DropZone.CENTER: QRect(m, m, w - 2 * m, h - 2 * m),
        }
        return rects.get(self.current_zone, QRect())

    # -- painting --

    def paintEvent(self, event):
        if not self.isVisible() or self.current_zone == DropZone.NONE:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        highlight = self.palette().highlight().color()

        # dim overlay
        painter.fillRect(self.rect(), QColor(0, 0, 0, 30))

        # preview highlight
        preview = self._preview_rect()
        if not preview.isEmpty():
            fill = QColor(highlight)
            fill.setAlpha(50)
            painter.setBrush(QBrush(fill))
            border = QColor(highlight)
            border.setAlpha(160)
            painter.setPen(QPen(border, 2))
            painter.drawRoundedRect(preview, 6, 6)

        # compass
        if self.width() >= 180 and self.height() >= 140:
            self._draw_compass(painter, highlight)

        # label pill
        self._draw_zone_label(painter, highlight, preview)

        painter.end()

    def _draw_compass(self, painter: QPainter, highlight: QColor):
        """Small centre-screen compass showing all five zones."""
        cx = self.width() // 2
        cy = self.height() // 2
        btn = 26
        gap = 3

        positions = {
            DropZone.CENTER: (cx - btn // 2, cy - btn // 2),
            DropZone.TOP:    (cx - btn // 2, cy - btn // 2 - gap - btn),
            DropZone.BOTTOM: (cx - btn // 2, cy + btn // 2 + gap),
            DropZone.LEFT:   (cx - btn // 2 - gap - btn, cy - btn // 2),
            DropZone.RIGHT:  (cx + btn // 2 + gap, cy - btn // 2),
        }

        for zone, (x, y) in positions.items():
            rect = QRect(x, y, btn, btn)
            if zone == self.current_zone:
                c = QColor(highlight); c.setAlpha(230)
                painter.setBrush(QBrush(c))
                painter.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
            else:
                c = QColor(highlight); c.setAlpha(50)
                painter.setBrush(QBrush(c))
                pc = QColor(highlight); pc.setAlpha(100)
                painter.setPen(QPen(pc, 1))
            painter.drawRoundedRect(rect, 4, 4)

    def _draw_zone_label(self, painter: QPainter, highlight: QColor,
                         preview: QRect):
        labels = {
            DropZone.CENTER: "Add to this group",
            DropZone.LEFT:   "\u2190 Split Left",
            DropZone.RIGHT:  "Split Right \u2192",
            DropZone.TOP:    "\u2191 Split Up",
            DropZone.BOTTOM: "\u2193 Split Down",
        }
        label = labels.get(self.current_zone)
        if not label or preview.isEmpty():
            return

        font = painter.font()
        font.setPointSize(10)
        font.setBold(True)
        painter.setFont(font)

        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(label) + 24
        th = fm.height() + 10

        lx = preview.center().x() - tw // 2
        ly = preview.y() + preview.height() * 3 // 4 - th // 2
        pill = QRect(lx, ly, tw, th)

        bg = QColor(highlight); bg.setAlpha(190)
        painter.setBrush(QBrush(bg))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(pill, th // 2, th // 2)

        painter.setPen(self.palette().highlightedText().color())
        painter.drawText(pill, Qt.AlignCenter, label)

    # -- public helpers --

    def set_zone(self, zone: str):
        if zone != self.current_zone:
            self.current_zone = zone
            self.update()

    def show_overlay(self):
        self.current_zone = DropZone.NONE
        self.setVisible(True)
        self.raise_()
        self.update()

    def hide_overlay(self):
        self.current_zone = DropZone.NONE
        self.setVisible(False)


# ---------------------------------------------------------------------------
# Draggable tab bar
# ---------------------------------------------------------------------------

class DraggableTabBar(QTabBar):
    """Tab bar with drag-and-drop support for grid-based tab management."""

    tab_drag_started = Signal(str, int)       # container_id, tab_index
    tab_dropped_on_bar = Signal(str, int, int) # src_container_id, src_tab_idx, target_idx

    def __init__(self, container_id: str, parent=None):
        super().__init__(parent)
        self.container_id = container_id
        self.setAcceptDrops(True)
        self.setElideMode(Qt.ElideRight)
        self.setSelectionBehaviorOnRemove(QTabBar.SelectPreviousTab)
        self._drag_start_pos = None
        self._dragging_index = -1

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            self._drag_start_pos = event.pos()
            self._dragging_index = self.tabAt(event.pos())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not (event.buttons() & Qt.LeftButton) or self._drag_start_pos is None:
            return
        if (event.pos() - self._drag_start_pos).manhattanLength() < QApplication.startDragDistance():
            return
        if self._dragging_index < 0:
            return

        drag = QDrag(self)
        mime = QMimeData()
        payload = f"{self.container_id}:{self._dragging_index}"
        mime.setData(TAB_MIME_TYPE, payload.encode("utf-8"))
        drag.setMimeData(mime)

        # tab preview pixmap
        tab_rect = self.tabRect(self._dragging_index)
        pixmap = QPixmap(tab_rect.size())
        pixmap.fill(Qt.transparent)
        p = QPainter(pixmap)
        p.setOpacity(0.85)
        p.setBrush(self.palette().button())
        p.setPen(self.palette().mid().color())
        p.drawRoundedRect(pixmap.rect().adjusted(1, 1, -1, -1), 4, 4)
        p.setPen(self.palette().buttonText().color())
        f = QFont(); f.setPointSize(9); p.setFont(f)
        p.drawText(pixmap.rect(), Qt.AlignCenter, self.tabText(self._dragging_index))
        p.end()

        drag.setPixmap(pixmap)
        drag.setHotSpot(self._drag_start_pos - tab_rect.topLeft())

        self.tab_drag_started.emit(self.container_id, self._dragging_index)
        drag.exec(Qt.MoveAction)

        self._drag_start_pos = None
        self._dragging_index = -1

    # -- drop handling on the tab bar itself --

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.acceptProposedAction()

    def dropEvent(self, event):
        if not event.mimeData().hasFormat(TAB_MIME_TYPE):
            return

        data = bytes(event.mimeData().data(TAB_MIME_TYPE)).decode("utf-8")
        src_id, src_idx = data.rsplit(":", 1)
        src_idx = int(src_idx)

        drop_pos = event.position().toPoint()
        target_idx = self.tabAt(drop_pos)

        if src_id == self.container_id:
            # reorder within the same container
            if target_idx >= 0 and target_idx != src_idx:
                tw = self.parent()
                if isinstance(tw, QTabWidget):
                    widget = tw.widget(src_idx)
                    text = tw.tabText(src_idx)
                    tw.removeTab(src_idx)
                    if src_idx < target_idx:
                        target_idx -= 1
                    tw.insertTab(target_idx, widget, text)
                    tw.setCurrentIndex(target_idx)
        else:
            # cross-container move → add to this group
            if target_idx < 0:
                target_idx = self.count()
            self.tab_dropped_on_bar.emit(src_id, src_idx, target_idx)

        event.acceptProposedAction()


# ---------------------------------------------------------------------------
# Grid item container
# ---------------------------------------------------------------------------

class GridItemContainer(QWidget):
    """One cell in the tab grid.

    Wraps a QTabWidget and a DropOverlay.  Emits signals so the parent
    TabsManager can react to split / move / close operations.
    """

    split_requested = Signal(str, int, str, str)
    # (source_container_id, source_tab_idx, target_container_id, zone)

    tab_move_requested = Signal(str, int, str, int)
    # (source_container_id, source_tab_idx, target_container_id, target_tab_idx)

    container_empty = Signal(str)   # container_id
    tab_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.container_id = str(uuid.uuid4())
        self.setAcceptDrops(True)
        self.setMinimumSize(120, 80)
        self._setup_ui()
        self._apply_border_style()

    def _apply_border_style(self):
        self.setContentsMargins(1, 1, 1, 1)

    def paintEvent(self, event):
        super().paintEvent(event)
        p = QPainter(self)
        color = self.palette().mid().color()
        p.setPen(QPen(color, 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        p.end()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.tab_widget = QTabWidget()
        bar = DraggableTabBar(self.container_id)
        self.tab_widget.setTabBar(bar)
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.setMovable(False)
        self.tab_widget.setDocumentMode(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close)
        self.tab_widget.currentChanged.connect(self.tab_changed.emit)

        bar.tab_dropped_on_bar.connect(self._on_bar_drop)

        layout.addWidget(self.tab_widget)

        # overlay (non-layout child – painted on top, transparent to events)
        self.drop_overlay = DropOverlay(self)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.drop_overlay.setGeometry(self.rect())

    # -- drag / drop on the *content area* --

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.acceptProposedAction()
            self.drop_overlay.show_overlay()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(TAB_MIME_TYPE):
            event.acceptProposedAction()
            zone = self.drop_overlay.get_zone_at(event.position().toPoint())
            self.drop_overlay.set_zone(zone)

    def dragLeaveEvent(self, event):
        self.drop_overlay.hide_overlay()

    def dropEvent(self, event):
        self.drop_overlay.hide_overlay()
        if not event.mimeData().hasFormat(TAB_MIME_TYPE):
            return

        data = bytes(event.mimeData().data(TAB_MIME_TYPE)).decode("utf-8")
        src_id, src_idx = data.rsplit(":", 1)
        src_idx = int(src_idx)

        zone = self.drop_overlay.get_zone_at(event.position().toPoint())

        if zone == DropZone.CENTER:
            if src_id != self.container_id:
                self.tab_move_requested.emit(
                    src_id, src_idx, self.container_id, self.tab_widget.count())
        elif zone in (DropZone.LEFT, DropZone.RIGHT, DropZone.TOP, DropZone.BOTTOM):
            # prevent splitting a single-tab container onto itself
            if src_id == self.container_id and self.tab_widget.count() <= 1:
                event.acceptProposedAction()
                return
            self.split_requested.emit(src_id, src_idx, self.container_id, zone)

        event.acceptProposedAction()

    # -- tab management helpers --

    def _on_tab_close(self, index: int):
        w = self.tab_widget.widget(index)
        self.tab_widget.removeTab(index)
        if w:
            w.deleteLater()
        if self.tab_widget.count() == 0:
            self.container_empty.emit(self.container_id)

    def _on_bar_drop(self, src_id: str, src_idx: int, target_idx: int):
        self.tab_move_requested.emit(src_id, src_idx, self.container_id, target_idx)

    # -- public API --

    def add_tab(self, widget: QWidget, title: str) -> int:
        idx = self.tab_widget.addTab(widget, title)
        self.tab_widget.setCurrentIndex(idx)
        return idx

    def insert_tab(self, index: int, widget: QWidget, title: str) -> int:
        idx = self.tab_widget.insertTab(index, widget, title)
        self.tab_widget.setCurrentIndex(idx)
        return idx

    def remove_tab(self, index: int):
        """Remove tab and return (widget, title) without deleting."""
        widget = self.tab_widget.widget(index)
        title = self.tab_widget.tabText(index)
        self.tab_widget.removeTab(index)
        return widget, title

    def tab_count(self) -> int:
        return self.tab_widget.count()

    def current_widget(self) -> QWidget:
        return self.tab_widget.currentWidget()

    def current_index(self) -> int:
        return self.tab_widget.currentIndex()
