from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QApplication, QWidget

from pylens.capture.window import capture_region, virtual_screen_bounds


class RegionSelector(QWidget):
    """Fullscreen dim overlay; drag a rectangle to capture (physical pixels)."""

    cancelled = Signal()
    selected = Signal(object)  # CaptureResult

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        self._origin_screen_x, self._origin_screen_y, vw, vh = virtual_screen_bounds()
        screen = QGuiApplication.primaryScreen()
        dpr = float(screen.devicePixelRatio()) if screen else 1.0
        self._dpr = dpr if dpr > 0 else 1.0
        self.setGeometry(
            int(self._origin_screen_x / self._dpr),
            int(self._origin_screen_y / self._dpr),
            int(vw / self._dpr),
            int(vh / self._dpr),
        )

        self._dragging = False
        self._start = None
        self._end = None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._start = event.position().toPoint()
            self._end = self._start
            self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._dragging:
            self._end = event.position().toPoint()
            self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or not self._dragging:
            return
        self._dragging = False
        self._end = event.position().toPoint()
        rect = self._selection_physical()
        self.hide()
        QApplication.processEvents()
        if rect is None:
            self.cancelled.emit()
            self.close()
            return
        x, y, w, h = rect
        if w < 20 or h < 20:
            self.cancelled.emit()
            self.close()
            return
        try:
            capture = capture_region(x, y, w, h)
        except Exception:
            self.cancelled.emit()
            self.close()
            return
        self.selected.emit(capture)
        self.close()

    def closeEvent(self, event) -> None:
        # If closed without selection (e.g. Alt+F4), treat as cancel when still idle.
        super().closeEvent(event)

    def _selection_physical(self) -> tuple[int, int, int, int] | None:
        if self._start is None or self._end is None:
            return None
        x1, y1 = self._start.x(), self._start.y()
        x2, y2 = self._end.x(), self._end.y()
        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)
        phys_x = int(self._origin_screen_x + left * self._dpr)
        phys_y = int(self._origin_screen_y + top * self._dpr)
        phys_w = max(1, int(width * self._dpr))
        phys_h = max(1, int(height * self._dpr))
        return phys_x, phys_y, phys_w, phys_h

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor(0, 0, 0, 100))
        if self._start and self._end:
            x1, y1 = self._start.x(), self._start.y()
            x2, y2 = self._end.x(), self._end.y()
            left, top = min(x1, x2), min(y1, y2)
            w, h = abs(x2 - x1), abs(y2 - y1)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            painter.fillRect(left, top, w, h, Qt.GlobalColor.transparent)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(0, 180, 255), 2))
            painter.drawRect(left, top, w, h)
        painter.end()
