from __future__ import annotations

import sys
import traceback
from pathlib import Path
from tempfile import gettempdir

from PIL import Image, ImageDraw
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from pylens.capture.region import RegionSelector
from pylens.capture.window import capture_foreground_window
from pylens.models import CaptureResult
from pylens.native.dpi import set_dpi_awareness
from pylens.native.hotkeys import HotkeyManager
from pylens.ocr.cache import get_shared_ocr_adapter, warm_ocr_adapter
from pylens.ocr.tiles import recognize_regions
from pylens.overlay.busy import BusyHud
from pylens.overlay.window import OverlayDisplayOptions, OverlayWindow
from pylens.settings import Settings, appdata_dir
from pylens.translate.factory import create_translator
from pylens.translate.service import TranslationService
from pylens.ui_settings import SettingsDialog


def _make_tray_icon() -> QIcon:
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse((4, 4, 60, 60), fill=(0, 120, 215, 255))
    draw.rectangle((18, 28, 46, 36), fill=(255, 255, 255, 255))
    path = appdata_dir() / "tray.png"
    img.save(path)
    return QIcon(str(path))


class PipelineWorker(QObject):
    finished = Signal(object, object)  # capture, blocks
    failed = Signal(str)

    def __init__(self, capture: CaptureResult, settings: Settings, translator: TranslationService):
        super().__init__()
        self._capture = capture
        self._settings = settings
        self._translator = translator

    @Slot()
    def run(self) -> None:
        try:
            if self._settings.debug_save_capture:
                out = Path(gettempdir()) / "pylens_last_capture.png"
                self._capture.image.save(out)

            adapter = get_shared_ocr_adapter(
                self._settings.ocr_engine,
                auto_download=False,
            )
            # Single-pass OCR for UI quality; tiling only kicks in for huge images.
            blocks = recognize_regions(
                self._capture.image,
                lambda region: adapter.recognize(
                    region,
                    self._settings.ocr_language,
                    debug=self._settings.debug_ocr,
                    profile=self._settings.ocr_profile,
                ),
                force_tiles=False,
            )
            if self._settings.debug_ocr:
                from pylens.ocr.debug import ocr_debug_root

                # Always remind where to look when investigating OCR quality.
                print(f"[PyLens] OCR debug dumps: {ocr_debug_root()}", flush=True)
            if not blocks:
                self.failed.emit("No text detected.")
                return
            blocks = self._translator.translate_blocks(blocks, self._settings.target_lang)
            self.finished.emit(self._capture, blocks)
        except Exception as ex:
            self.failed.emit(f"{ex}\n\n{traceback.format_exc()}")


class PyLensApp(QObject):
    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self.app = qt_app
        self.settings = Settings.load()
        self.translator = TranslationService(
            engine=create_translator(self.settings.translation_engine)
        )
        self.hotkeys = HotkeyManager()
        self._overlay: OverlayWindow | None = None
        self._selector: RegionSelector | None = None
        self._busy = False
        self._busy_hud: BusyHud | None = None
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None

        # Hidden window owns HWND for RegisterHotKey
        self._host = QWidget()
        self._host.setWindowTitle("PyLensHost")
        self._host.resize(1, 1)
        self._host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._host.show()
        self._host.hide()

        self._tray = QSystemTrayIcon(_make_tray_icon(), self.app)
        menu = QMenu()
        menu.addAction("Translate region…", self.start_region)
        menu.addAction("Translate active window", self.start_window)
        menu.addSeparator()
        menu.addAction("Settings…", self.open_settings)
        menu.addAction("Quit", self.quit)
        self._tray.setContextMenu(menu)
        self._tray.setToolTip("PyLens")
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

        hwnd = int(self._host.winId())
        self.hotkeys.bind_to_widget(hwnd)
        self._register_hotkeys()

        if not self.settings.first_run_done or not self.settings.privacy_acknowledged:
            self.open_settings()

        # Warm OCR + Argos off the UI thread so the first capture is not cold.
        QTimer.singleShot(250, self._start_warmup)

    def _register_hotkeys(self) -> None:
        self.hotkeys.unregister_all()
        try:
            self.hotkeys.register(self.settings.hotkey_region, self.start_region)
            self.hotkeys.register(self.settings.hotkey_window, self.start_window)
        except OSError as ex:
            self._tray.showMessage("PyLens", f"Hotkey registration failed: {ex}", QSystemTrayIcon.MessageIcon.Warning)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings()

    def open_settings(self) -> None:
        dlg = SettingsDialog(self.settings, self._host)
        if dlg.exec():
            if self._overlay is not None:
                self._overlay.close()
                self._overlay = None
            self.translator.close()
            self.translator = TranslationService(
                engine=create_translator(self.settings.translation_engine)
            )
            self._register_hotkeys()

    def quit(self) -> None:
        self.hotkeys.unregister_all()
        self.translator.close()
        self._tray.hide()
        self.app.quit()

    def _show_busy_hud(self, message: str) -> None:
        if self._busy_hud is None:
            self._busy_hud = BusyHud(message)
        else:
            self._busy_hud.set_message(message)
        self._busy_hud.show_centered()

    def _hide_busy_hud(self) -> None:
        if self._busy_hud is not None:
            self._busy_hud.hide()

    def start_region(self) -> None:
        if self._busy:
            return
        if not self._precheck():
            return
        self._busy = True
        # No HUD during marquee — it would sit on top of the region selector.
        self._selector = RegionSelector()
        self._selector.selected.connect(self._on_capture_ready)
        self._selector.cancelled.connect(self._on_region_cancelled)
        self._selector.show()
        self._selector.raise_()
        self._selector.activateWindow()

    def _on_region_cancelled(self) -> None:
        self._busy = False
        self._selector = None
        self._hide_busy_hud()

    def _start_warmup(self) -> None:
        settings = self.settings
        translator = self.translator

        class _WarmWorker(QObject):
            finished = Signal()

            @Slot()
            def run(self) -> None:
                try:
                    target = settings.target_lang.split("-")[0].lower()
                    source = "ja" if target == "en" else "en"
                    if settings.translation_engine == "argos" and target not in ("en", "ja"):
                        source, target = "ja", "en"
                    translator.prepare(source, target)
                    warm_ocr_adapter(settings.ocr_engine, settings.ocr_language)
                except Exception:
                    pass
                self.finished.emit()

        self._warm_thread = QThread(self)
        self._warm_worker = _WarmWorker()
        self._warm_worker.moveToThread(self._warm_thread)
        self._warm_thread.started.connect(self._warm_worker.run)
        self._warm_worker.finished.connect(self._warm_thread.quit)
        self._warm_thread.finished.connect(self._warm_thread.deleteLater)
        self._warm_thread.start()

    def start_window(self) -> None:
        if self._busy:
            return
        if not self._precheck():
            return
        # Capture BEFORE showing HUD — otherwise GetForegroundWindow returns our UI.
        exclude = {int(self._host.winId())}
        if self._busy_hud is not None:
            exclude.add(int(self._busy_hud.winId()))
        capture = capture_foreground_window(exclude_hwnds=exclude)
        if capture is None:
            self._tray.showMessage(
                "PyLens",
                "Could not capture the active window. Click the target window, then try again.",
                QSystemTrayIcon.MessageIcon.Warning,
            )
            return
        self._on_capture_ready(capture)

    def _precheck(self) -> bool:
        if not self.settings.privacy_acknowledged:
            self.open_settings()
            return False
        target = self.settings.target_lang.split("-")[0].lower()
        source = "ja" if target == "en" else "en"
        if self.settings.translation_engine == "argos" and target not in ("en", "ja"):
            QMessageBox.warning(
                None,
                "Translation not ready",
                f"Argos offline supports only JA↔EN (current target={self.settings.target_lang}).\n"
                "Set target language to en in Settings, or switch Translation to Google / MyMemory.",
            )
            self.open_settings()
            return False
        try:
            self.translator.prepare(source, target)
        except Exception as ex:
            QMessageBox.warning(None, "Translation not ready", str(ex))
            return False
        adapter = get_shared_ocr_adapter(
            self.settings.ocr_engine,
            auto_download=False,
        )
        if not adapter.is_ready(self.settings.ocr_language):
            QMessageBox.warning(
                None,
                "PyLens",
                adapter.readiness_message(self.settings.ocr_language),
            )
            return False
        return True

    def _on_capture_ready(self, capture: CaptureResult) -> None:
        self._busy = True
        self._selector = None
        if self._overlay is not None:
            self._overlay.close()
            self._overlay = None

        self._show_busy_hud("OCR + translating…")

        self._thread = QThread()
        self._worker = PipelineWorker(capture, self.settings, self.translator)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.finished.connect(self._on_pipeline_ok)
        self._worker.failed.connect(self._on_pipeline_fail)
        self._worker.finished.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_worker)
        self._thread.start()

    def _cleanup_worker(self) -> None:
        self._worker = None
        if self._thread is not None:
            self._thread.deleteLater()
            self._thread = None

    def _on_pipeline_ok(self, capture: CaptureResult, blocks) -> None:
        self._busy = False
        self._hide_busy_hud()
        self._overlay = OverlayWindow(
            capture,
            blocks,
            self.translator,
            self.settings.target_lang,
            self.settings.recent_targets,
            display=OverlayDisplayOptions(
                always_shrink_font=self.settings.overlay_always_shrink_font,
                always_shrink_pt=self.settings.overlay_always_shrink_pt,
                shrink_on_collide=self.settings.overlay_shrink_on_collide,
                hover_show_full=self.settings.overlay_hover_show_full,
            ),
        )
        self._overlay.target_changed.connect(self._on_target_changed)
        self._overlay.closed.connect(self._on_overlay_closed)
        self._overlay.show()
        self._overlay.raise_()
        self._overlay.activateWindow()

    def _on_pipeline_fail(self, message: str) -> None:
        self._busy = False
        self._hide_busy_hud()
        QMessageBox.warning(None, "PyLens", message[:2000])

    def _on_target_changed(self, code: str) -> None:
        self.settings.target_lang = code
        if code not in self.settings.recent_targets:
            self.settings.recent_targets = [code, *self.settings.recent_targets][:8]
        self.settings.save()

    def _on_overlay_closed(self) -> None:
        self._overlay = None


def main() -> int:
    set_dpi_awareness()
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("PyLens")
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "PyLens", "System tray is not available.")
        return 1
    controller = PyLensApp(app)
    _ = controller  # keep alive
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
