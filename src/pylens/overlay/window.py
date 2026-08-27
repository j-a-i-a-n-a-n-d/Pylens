from __future__ import annotations

from dataclasses import dataclass

from PIL import Image, ImageEnhance, ImageFilter
from PySide6.QtCore import QObject, QRect, Qt, QThread, Signal, Slot
from PySide6.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from pylens.models import CaptureResult, TextBlock
from pylens.native.dpi import get_system_dpi, physical_to_dip
from pylens.overlay.colors import CHIP_BG_ALPHA, apply_colors
from pylens.overlay.layout import (
    MAX_HEIGHT_MULT,
    MIN_FONT_PT,
    chip_rect,
    find_overlapping_indices,
    preferred_font_pt,
)
from pylens.translate.service import TranslationService


@dataclass(frozen=True)
class OverlayDisplayOptions:
    always_shrink_font: bool = True
    always_shrink_pt: float = 4.0
    shrink_on_collide: bool = True
    hover_show_full: bool = True

    @property
    def base_shrink_pt(self) -> float:
        return self.always_shrink_pt if self.always_shrink_font else 0.0


def pil_to_qpixmap(image: Image.Image) -> QPixmap:
    rgb = image.convert("RGBA")
    data = rgb.tobytes("raw", "RGBA")
    qimg = QImage(data, rgb.width, rgb.height, QImage.Format.Format_RGBA8888)
    return QPixmap.fromImage(qimg.copy())


def make_liquid_glass(image: Image.Image, target_size: tuple[int, int]) -> QPixmap:
    rgba = image.convert("RGBA")
    w, h = rgba.size
    small = rgba.resize((max(1, w // 5), max(1, h // 5)), Image.Resampling.BILINEAR)
    blurred = small.filter(ImageFilter.GaussianBlur(radius=4))
    glass = blurred.resize((w, h), Image.Resampling.BILINEAR)
    glass = ImageEnhance.Brightness(glass).enhance(0.96)
    tint = Image.new("RGBA", glass.size, (255, 255, 255, 18))
    glass = Image.alpha_composite(glass, tint)
    r, g, b, a = glass.split()
    a = a.point(lambda p: int(p * 0.28))
    glass = Image.merge("RGBA", (r, g, b, a))
    pix = pil_to_qpixmap(glass)
    return pix.scaled(
        target_size[0],
        target_size[1],
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


def fit_full_text(
    text: str,
    family: str,
    box_w: float,
    ocr_h: float,
    max_h: float,
    *,
    shrink_pt: float = 0.0,
    start_font_pt: float | None = None,
) -> tuple[float, float, bool]:
    """Fit translation with wrap; never ellipsize. Returns (font_pt, needed_h, wrap)."""
    font_pt = (
        start_font_pt
        if start_font_pt is not None
        else preferred_font_pt(ocr_h, shrink_pt=shrink_pt)
    )
    font_pt = max(MIN_FONT_PT, font_pt)
    font = QFont(family)
    width = max(8, int(box_w))

    while font_pt >= MIN_FONT_PT:
        font.setPointSizeF(font_pt)
        metrics = QFontMetrics(font)
        if metrics.horizontalAdvance(text) <= width and metrics.height() <= max_h:
            return font_pt, float(metrics.height()), False
        br = metrics.boundingRect(
            QRect(0, 0, width, 10_000),
            int(Qt.TextFlag.TextWordWrap),
            text,
        )
        if br.height() <= max_h:
            return font_pt, float(max(metrics.height(), br.height())), True
        font_pt -= 0.5

    font.setPointSizeF(MIN_FONT_PT)
    metrics = QFontMetrics(font)
    br = metrics.boundingRect(
        QRect(0, 0, width, 10_000),
        int(Qt.TextFlag.TextWordWrap),
        text,
    )
    return MIN_FONT_PT, float(min(max_h, max(metrics.height(), br.height()))), True


class TextChipWidget(QLabel):
    def __init__(
        self,
        block: TextBlock,
        ocr_dip: tuple[float, float, float, float],
        bounds: tuple[float, float],
        options: OverlayDisplayOptions,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.block = block
        self._ocr_dip = ocr_dip
        self._bounds = bounds
        self._options = options
        self._extra_shrink_pt = 0.0
        self._hovering = False
        self._compact_geom: tuple[int, int, int, int] | None = None
        self._compact_font_pt: float | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context_menu)
        self.setMouseTracking(True)
        self.apply_text(block.translated or block.original)

    def set_extra_shrink(self, pt: float) -> None:
        self._extra_shrink_pt = max(0.0, pt)
        if not self._hovering:
            self.apply_text(self.block.translated or self.block.original)

    def geometry_tuple(self) -> tuple[float, float, float, float]:
        g = self.geometry()
        return (float(g.x()), float(g.y()), float(g.width()), float(g.height()))

    def apply_text(self, text: str, *, expanded: bool = False) -> None:
        self.block.translated = text
        full = text or ""
        self.setToolTip(full if full else self.block.original)

        fr, fg, fb = self.block.fg_color
        self.setStyleSheet(
            "QLabel {"
            f"  color: rgb({fr},{fg},{fb});"
            "  background: transparent;"
            "  padding: 1px 2px;"
            "}"
        )

        _ox, oy, ow, oh = self._ocr_dip
        bw, bh = self._bounds
        # Compact (default): tight to OCR height to reduce overlap.
        # Expanded (hover): allow taller wrap for full readability.
        height_mult = MAX_HEIGHT_MULT if expanded else (1.15 if self._options.hover_show_full else MAX_HEIGHT_MULT)
        max_h = min(bh - max(0.0, oy - 1), oh * height_mult, bh * 0.9)
        shrink = self._options.base_shrink_pt + self._extra_shrink_pt
        family = "Segoe UI"
        font_pt, needed_h, wrap = fit_full_text(
            full,
            family,
            max(8.0, ow - 2),
            oh,
            max_h,
            shrink_pt=shrink,
        )
        x, y, w, h = chip_rect(
            self._ocr_dip,
            bw,
            bh,
            needed_h=needed_h,
            max_height_mult=height_mult,
        )
        self.setGeometry(round(x), round(y), max(1, round(w)), max(1, round(h)))
        self.setWordWrap(wrap)
        font = self.font()
        font.setFamily(family)
        font.setPointSizeF(font_pt)
        self.setFont(font)
        self.setText(full)
        self.update()

    def enterEvent(self, event) -> None:
        if self._options.hover_show_full and not self._hovering:
            self._hovering = True
            g = self.geometry()
            self._compact_geom = (g.x(), g.y(), g.width(), g.height())
            self._compact_font_pt = self.font().pointSizeF()
            self.apply_text(self.block.translated or self.block.original, expanded=True)
            self.raise_()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        if self._options.hover_show_full and self._hovering:
            self._hovering = False
            self.apply_text(self.block.translated or self.block.original, expanded=False)
            if self._compact_geom is not None:
                # Re-assert compact layout (apply_text already did; keep hook for clarity)
                self._compact_geom = None
                self._compact_font_pt = None
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        br, bg, bb = self.block.bg_color
        fill = QColor(br, bg, bb, CHIP_BG_ALPHA)
        painter.setPen(QColor(0, 0, 0, 50))
        painter.setBrush(fill)
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 2, 2)
        painter.end()
        super().paintEvent(event)

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        act_o = menu.addAction("Copy original")
        act_t = menu.addAction("Copy translation")
        chosen = menu.exec(self.mapToGlobal(pos))
        clipboard = QApplication.clipboard()
        if chosen is act_o:
            clipboard.setText(self.block.original)
        elif chosen is act_t:
            clipboard.setText(self.block.translated or self.block.original)


class _RetargetWorker(QObject):
    finished = Signal(list)
    failed = Signal(str)

    def __init__(self, originals: list[str], target: str, translator: TranslationService):
        super().__init__()
        self._originals = originals
        self._target = target
        self._translator = translator

    @Slot()
    def run(self) -> None:
        try:
            out = [self._translator.translate(t, self._target) for t in self._originals]
            self.finished.emit(out)
        except Exception as ex:
            self.failed.emit(str(ex))


class OverlayWindow(QWidget):
    closed = Signal()
    target_changed = Signal(str)

    def __init__(
        self,
        capture: CaptureResult,
        blocks: list[TextBlock],
        translator: TranslationService,
        target_lang: str,
        recent_targets: list[str] | None = None,
        display: OverlayDisplayOptions | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._capture = capture
        self._blocks = apply_colors(capture.image, blocks)
        self._translator = translator
        self._target = target_lang
        self._recent = recent_targets or ["en", "ja"]
        self._display = display or OverlayDisplayOptions()
        self._boxes: list[TextChipWidget] = []
        self._retarget_thread: QThread | None = None
        self._retarget_worker: _RetargetWorker | None = None
        self._toolbar: QWidget | None = None

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("OverlayWindow { background: transparent; }")

        dpi = get_system_dpi()
        ox = physical_to_dip(capture.origin_x, dpi)
        oy = physical_to_dip(capture.origin_y, dpi)
        ow = physical_to_dip(capture.width, dpi)
        oh = physical_to_dip(capture.height, dpi)
        self.setGeometry(int(ox), int(oy), int(ow), int(oh))

        self._bg = QLabel(self)
        self._bg.setStyleSheet("background: transparent;")
        self._bg.setPixmap(make_liquid_glass(capture.image, (self.width(), self.height())))
        self._bg.setGeometry(0, 0, self.width(), self.height())
        self._bg.lower()

        self._build_busy_layer()
        self._build_chips(dpi)
        self._build_toolbar()
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _build_busy_layer(self) -> None:
        self._busy = QWidget(self)
        self._busy.setObjectName("busyLayer")
        self._busy.setStyleSheet(
            "#busyLayer { background: rgba(10, 12, 16, 120); border-radius: 8px; }"
            "QLabel { color: white; font-size: 13px; background: transparent; }"
            "QProgressBar {"
            "  background: rgba(255,255,255,0.15); border: none; border-radius: 4px; height: 8px;"
            "}"
            "QProgressBar::chunk { background: #3b9eff; border-radius: 4px; }"
        )
        layout = QVBoxLayout(self._busy)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._busy_label = QLabel("Updating translation…")
        self._busy_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self._busy_label)
        bar = QProgressBar()
        bar.setRange(0, 0)
        bar.setTextVisible(False)
        bar.setFixedWidth(180)
        layout.addWidget(bar, alignment=Qt.AlignmentFlag.AlignCenter)
        self._busy.setGeometry(0, 0, self.width(), self.height())
        self._busy.hide()

    def _show_busy(self, message: str) -> None:
        self._busy_label.setText(message)
        self._busy.setGeometry(0, 0, self.width(), self.height())
        self._busy.show()
        self._busy.raise_()
        self._lang.setEnabled(False)

    def _hide_busy(self) -> None:
        self._busy.hide()
        self._lang.setEnabled(True)

    def _build_toolbar(self) -> None:
        """Floating control bar outside the capture rect so chips stay fully visible."""
        bar = QWidget(None)
        bar.setObjectName("toolbar")
        bar.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        bar.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        bar.setStyleSheet(
            "#toolbar {"
            "  background-color: #f4f6f8;"
            "  border: 1px solid #9aa3b2;"
            "  border-radius: 10px;"
            "}"
            "#toolbar QLabel {"
            "  color: #1b2430;"
            "  background: transparent;"
            "  font-size: 12px;"
            "  font-weight: 600;"
            "}"
            "#toolbar QComboBox {"
            "  color: #1b2430;"
            "  background-color: #ffffff;"
            "  border: 1px solid #8b95a5;"
            "  border-radius: 6px;"
            "  padding: 3px 8px;"
            "  min-width: 72px;"
            "}"
            "#toolbar QComboBox QAbstractItemView {"
            "  color: #1b2430;"
            "  background-color: #ffffff;"
            "  selection-background-color: #d7e6ff;"
            "  selection-color: #1b2430;"
            "}"
            "#toolbar QPushButton {"
            "  color: #1b2430;"
            "  background-color: #e4e8ee;"
            "  border: 1px solid #8b95a5;"
            "  border-radius: 6px;"
            "  padding: 4px 12px;"
            "  font-weight: 600;"
            "}"
            "#toolbar QPushButton:hover {"
            "  background-color: #d5dbe4;"
            "}"
        )
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.addWidget(QLabel("Target"))
        self._lang = QComboBox()
        # Prefer common codes; keep recent order but de-dupe.
        codes: list[str] = []
        for code in [*self._recent, self._target, "en", "ja"]:
            c = str(code).strip()
            if c and c not in codes:
                codes.append(c)
        for code in codes:
            self._lang.addItem(code, code)
        idx = self._lang.findData(self._target)
        self._lang.setCurrentIndex(max(0, idx))
        self._lang.currentIndexChanged.connect(self._on_lang_changed)
        layout.addWidget(self._lang)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(self.close)
        layout.addWidget(close_btn)
        bar.adjustSize()

        # Place above the overlay when possible; otherwise below; always outside chips.
        gap = 8
        screen = self.screen()
        avail = screen.availableGeometry() if screen is not None else self.geometry()
        ox, oy, ow, _oh = self.x(), self.y(), self.width(), self.height()
        tw, th = bar.width(), bar.height()
        tx = min(max(avail.left() + gap, ox + ow - tw), avail.right() - tw - gap)
        above_y = oy - th - gap
        below_y = oy + self.height() + gap
        if above_y >= avail.top() + gap:
            ty = above_y
        elif below_y + th <= avail.bottom() - gap:
            ty = below_y
        else:
            ty = max(avail.top() + gap, min(oy + gap, avail.bottom() - th - gap))
        bar.move(int(tx), int(ty))
        bar.show()
        bar.raise_()
        self._toolbar = bar

    def _build_chips(self, dpi: int) -> None:
        for box in self._boxes:
            box.deleteLater()
        self._boxes.clear()

        bounds = (float(self.width()), float(self.height()))
        for block in self._blocks:
            x, y, w, h = block.rect
            ocr_dip = (
                physical_to_dip(x, dpi),
                physical_to_dip(y, dpi),
                physical_to_dip(w, dpi),
                physical_to_dip(h, dpi),
            )
            widget = TextChipWidget(block, ocr_dip, bounds, self._display, self)
            widget.show()
            self._boxes.append(widget)

        if self._display.shrink_on_collide:
            self._resolve_collisions()
        for widget in self._boxes:
            widget.raise_()

    def _resolve_collisions(self) -> None:
        """Iteratively shrink fonts on overlapping chips until clear or min size."""
        for _ in range(12):
            rects = [w.geometry_tuple() for w in self._boxes]
            overlapping = find_overlapping_indices(rects)
            if not overlapping:
                return
            for idx in overlapping:
                chip = self._boxes[idx]
                chip.set_extra_shrink(chip._extra_shrink_pt + 1.0)

    def _on_lang_changed(self) -> None:
        code = self._lang.currentData()
        if not code or code == self._target:
            return
        if self._retarget_thread is not None and self._retarget_thread.isRunning():
            return

        self._target = str(code)
        self.target_changed.emit(self._target)
        self._show_busy("Updating translation…")

        originals = [w.block.original for w in self._boxes]
        self._retarget_thread = QThread(self)
        self._retarget_worker = _RetargetWorker(originals, self._target, self._translator)
        self._retarget_worker.moveToThread(self._retarget_thread)
        self._retarget_thread.started.connect(self._retarget_worker.run)
        self._retarget_worker.finished.connect(self._on_retarget_ok)
        self._retarget_worker.failed.connect(self._on_retarget_fail)
        self._retarget_worker.finished.connect(self._retarget_thread.quit)
        self._retarget_worker.failed.connect(self._retarget_thread.quit)
        self._retarget_thread.finished.connect(self._cleanup_retarget)
        self._retarget_thread.start()

    @Slot(list)
    def _on_retarget_ok(self, translations: list) -> None:
        for widget, text in zip(self._boxes, translations, strict=False):
            widget._extra_shrink_pt = 0.0
            widget.apply_text(str(text))
        if self._display.shrink_on_collide:
            self._resolve_collisions()
        self._hide_busy()

    @Slot(str)
    def _on_retarget_fail(self, message: str) -> None:
        self._hide_busy()
        self.setToolTip(f"Retarget failed: {message}")

    def _cleanup_retarget(self) -> None:
        self._retarget_worker = None
        if self._retarget_thread is not None:
            self._retarget_thread.deleteLater()
            self._retarget_thread = None

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._busy.isVisible():
            return
        child = self.childAt(event.position().toPoint())
        if child is self._bg or child is None:
            self.close()
            return
        super().mousePressEvent(event)

    def closeEvent(self, event) -> None:
        if self._retarget_thread is not None and self._retarget_thread.isRunning():
            self._retarget_thread.quit()
            self._retarget_thread.wait(1000)
        if self._toolbar is not None:
            self._toolbar.close()
            self._toolbar.deleteLater()
            self._toolbar = None
        self.closed.emit()
        super().closeEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        painter.fillRect(self.rect(), Qt.GlobalColor.transparent)
        painter.end()
        super().paintEvent(event)

    def resizeEvent(self, event) -> None:
        self._bg.setGeometry(0, 0, self.width(), self.height())
        self._bg.setPixmap(make_liquid_glass(self._capture.image, (self.width(), self.height())))
        if hasattr(self, "_busy"):
            self._busy.setGeometry(0, 0, self.width(), self.height())
        super().resizeEvent(event)
