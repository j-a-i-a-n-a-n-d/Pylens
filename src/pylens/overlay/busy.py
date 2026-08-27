from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QProgressBar, QVBoxLayout, QWidget


class BusyHud(QWidget):
    """Small always-on-top loading HUD so the user knows OCR/translate is running."""

    def __init__(self, message: str = "Working…", parent=None) -> None:
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setStyleSheet(
            "BusyHud {"
            "  background: rgba(22, 26, 32, 0.92);"
            "  border: 1px solid rgba(255,255,255,0.22);"
            "  border-radius: 12px;"
            "}"
            "QLabel { color: white; font-size: 13px; }"
            "QProgressBar {"
            "  background: rgba(255,255,255,0.12);"
            "  border: none; border-radius: 4px; height: 8px;"
            "}"
            "QProgressBar::chunk {"
            "  background: #3b9eff; border-radius: 4px;"
            "}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        self._label = QLabel(message)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._label)
        bar = QProgressBar()
        bar.setRange(0, 0)  # indeterminate
        bar.setTextVisible(False)
        bar.setFixedWidth(220)
        layout.addWidget(bar, alignment=Qt.AlignmentFlag.AlignCenter)
        self.adjustSize()

    def set_message(self, message: str) -> None:
        self._label.setText(message)
        self.adjustSize()

    def show_centered(self) -> None:
        self.adjustSize()
        screen = self.screen()
        if screen is not None:
            geo = screen.availableGeometry()
            self.move(
                geo.center().x() - self.width() // 2,
                geo.center().y() - self.height() // 2,
            )
        self.show()
        self.raise_()
