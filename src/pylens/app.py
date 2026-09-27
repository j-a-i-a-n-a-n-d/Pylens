from __future__ import annotations

import sys
import traceback
from pathlib import Path
from tempfile import gettempdir

from PIL import Image, ImageDraw
from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QMessageBox, QSystemTrayIcon, QWidget

from pylens.capture import create_capture_backend, create_region_selector
from pylens.models import CaptureResult
from pylens.dpi import create_dpi_backend
from pylens.hotkeys import create_hotkey_backend
from pylens.ocr.cache import get_shared_ocr_adapter, warm_ocr_adapter
from pylens.ocr.tiles import recognize_regions
from pylens.overlay.busy import BusyHud
from pylens.overlay.window import OverlayDisplayOptions, OverlayWindow
from pylens.settings import Settings
from pylens.translate.factory import create_translator
from pylens.translate.service import TranslationService
from pylens.ui_settings import SettingsDialog


def _make_tray_icon() -> QIcon:
    pixmap = QPixmap(64, 64)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor(0, 120, 215, 255))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(4, 4, 56, 56)
    painter.setBrush(QColor(255, 255, 255, 255))
    painter.drawRect(18, 28, 28, 8)
    painter.end()
    return QIcon(pixmap)


from pylens.logger import get_logger, log_debug, log_error, log_info, log_warning
from pylens.platform import current_platform, Platform


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
            log_info(f"Running OCR ({self._settings.ocr_engine}, {self._settings.ocr_language}, profile={self._settings.ocr_profile})...")
            if self._settings.debug_save_capture:
                out = Path(gettempdir()) / "pylens_last_capture.png"
                self._capture.image.save(out)
                log_debug(f"Saved debug capture to {out}")

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
                log_debug(f"OCR debug dumps: {ocr_debug_root()}")
            if not blocks:
                log_warning("No text detected in capture region.")
                self.failed.emit("No text detected.")
                return
            log_info(f"OCR detected {len(blocks)} text blocks. Translating with {self._settings.translation_engine} -> {self._settings.target_lang}...")
            blocks = self._translator.translate_blocks(blocks, self._settings.target_lang)
            log_info("Translation completed. Rendering overlay.")
            self.finished.emit(self._capture, blocks)
        except Exception as ex:
            log_error(f"Pipeline failed: {ex}")
            self.failed.emit(f"{ex}\n\n{traceback.format_exc()}")


class PyLensApp(QObject):
    def __init__(self, qt_app: QApplication) -> None:
        super().__init__()
        self.app = qt_app
        self.settings = Settings.load()
        log_info("Initializing PyLens...")
        log_info(f"Settings: target_lang='{self.settings.target_lang}', ocr='{self.settings.ocr_engine}', translation='{self.settings.translation_engine}'")

        self.translator = TranslationService(
            engine=create_translator(self.settings.translation_engine)
        )

        # Platform-specific backends
        self._capture_backend = create_capture_backend()
        self._hotkey_backend = create_hotkey_backend()
        self._dpi_backend = create_dpi_backend()

        self._overlay: OverlayWindow | None = None
        self._selector = None
        self._busy = False
        self._busy_hud: BusyHud | None = None
        self._thread: QThread | None = None
        self._worker: PipelineWorker | None = None

        # Hidden window for hotkey binding (Windows) or event handling
        self._host = QWidget()
        self._host.setWindowTitle("PyLensHost")
        self._host.resize(1, 1)
        self._host.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
        self._host.show()
        self._host.hide()

        # System tray
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
        log_info("System tray icon active.")

        # Bind hotkeys
        hwnd = int(self._host.winId())
        self._hotkey_backend.bind_to_window(hwnd)
        self._register_hotkeys()

        if not self.settings.first_run_done or not self.settings.privacy_acknowledged:
            self.open_settings()

        # Warm OCR + Argos off the UI thread
        QTimer.singleShot(250, self._start_warmup)

    def _register_hotkeys(self) -> None:
        self._hotkey_backend.unregister_all()
        try:
            r_id = self._hotkey_backend.register(self.settings.hotkey_region, self.start_region)
            w_id = self._hotkey_backend.register(self.settings.hotkey_window, self.start_window)
            log_info(f"Registered hotkeys: Region='{self.settings.hotkey_region}' (id={r_id}), Window='{self.settings.hotkey_window}' (id={w_id})")
        except OSError as ex:
            log_error(f"Hotkey registration failed: {ex}")
            self._tray.showMessage("PyLens", f"Hotkey registration failed: {ex}", QSystemTrayIcon.MessageIcon.Warning)

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_settings()

    def open_settings(self) -> None:
        log_info("Opening Settings dialog...")
        if current_platform() == Platform.MACOS:
            try:
                from Cocoa import NSApplication
                NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
            except Exception:
                pass
        dlg = SettingsDialog(self.settings, None)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        if dlg.exec():
            log_info("Settings updated and saved.")
            if self._overlay is not None:
                self._overlay.close()
                self._overlay = None
            self.translator.close()
            self.translator = TranslationService(
                engine=create_translator(self.settings.translation_engine)
            )
            self._register_hotkeys()

    def quit(self) -> None:
        log_info("Quitting PyLens...")
        if hasattr(self, "_warm_thread") and self._warm_thread is not None and self._warm_thread.isRunning():
            self._warm_thread.quit()
            self._warm_thread.wait(1000)
        if self._thread is not None and self._thread.isRunning():
            self._thread.quit()
            self._thread.wait(1000)
        self._hotkey_backend.unregister_all()
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
        log_info("Hotkey triggered: Start region translation")
        if self._busy:
            log_warning("Ignored start_region: busy")
            return
        if not self._precheck():
            return
        self._busy = True
        self._selector = create_region_selector(self._on_capture_ready, self._on_region_cancelled)
        self._selector.show()

    def _on_region_cancelled(self) -> None:
        log_info("Region selection cancelled.")
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
                    log_info(f"Background warmup started (OCR: {settings.ocr_engine}, Translation: {settings.translation_engine})...")
                    target = settings.target_lang.split("-")[0].lower()
                    source = "ja" if target == "en" else "en"
                    if settings.translation_engine == "argos" and target not in ("en", "ja"):
                        source, target = "ja", "en"
                    translator.prepare(source, target)
                    warm_ocr_adapter(settings.ocr_engine, settings.ocr_language)
                    log_info("Background warmup completed successfully.")
                except Exception as ex:
                    log_warning(f"Background warmup note: {ex}")
                self.finished.emit()

        self._warm_thread = QThread(self)
        self._warm_thread.setStackSize(16 * 1024 * 1024)
        self._warm_worker = _WarmWorker()
        self._warm_worker.moveToThread(self._warm_thread)
        self._warm_thread.started.connect(self._warm_worker.run)
        self._warm_worker.finished.connect(self._warm_thread.quit)
        self._warm_thread.finished.connect(self._warm_thread.deleteLater)
        self._warm_thread.start()

    def start_window(self) -> None:
        log_info("Hotkey triggered: Start active window translation")
        if self._busy:
            log_warning("Ignored start_window: busy")
            return
        if not self._precheck():
            return

        # Capture BEFORE showing HUD — otherwise GetForegroundWindow returns our UI.
        exclude = {int(self._host.winId())}
        if self._busy_hud is not None:
            exclude.add(int(self._busy_hud.winId()))

        capture = self._capture_backend.capture_window(exclude_hwnds=exclude)
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
        self._thread.setStackSize(16 * 1024 * 1024)
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
    import threading
    try:
        threading.stack_size(16 * 1024 * 1024)
    except Exception:
        pass

    # Set DPI awareness early
    dpi_backend = create_dpi_backend()
    dpi_backend.set_dpi_awareness()

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("PyLens")

    # Check system tray availability
    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "PyLens", "System tray is not available.")
        return 1

    controller = PyLensApp(app)
    _ = controller  # keep alive
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())