from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from pylens.ocr.factory import available_engines, create_ocr_adapter
from pylens.paths import argos_models_dir, paddle_models_dir
from pylens.settings import Settings
from pylens.translate.argos import ArgosTranslator


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("PyLens Settings")
        self.setMinimumWidth(480)
        self._settings = settings

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.target = QLineEdit(settings.target_lang)
        self.target.textChanged.connect(self._refresh_translation_status)
        form.addRow("Target language (e.g. en)", self.target)

        self.translation_engine = QComboBox()
        self.translation_engine.addItem("Argos (offline)", "argos")
        self.translation_engine.addItem("Google / MyMemory (online)", "google")
        translation_index = self.translation_engine.findData(settings.translation_engine)
        self.translation_engine.setCurrentIndex(max(0, translation_index))
        self.translation_engine.currentIndexChanged.connect(self._refresh_translation_status)
        form.addRow("Translation", self.translation_engine)

        self.engine = QComboBox()
        for engine_id, label in available_engines():
            self.engine.addItem(label, engine_id.value)
        idx = self.engine.findData(settings.ocr_engine)
        self.engine.setCurrentIndex(max(0, idx))
        self.engine.currentIndexChanged.connect(self._refresh_ocr_status)
        form.addRow("OCR engine", self.engine)

        self.ocr_profile = QComboBox()
        self.ocr_profile.addItem("Fast", "fast")
        self.ocr_profile.addItem("Moderate (recommended)", "balanced")
        self.ocr_profile.addItem("Accurate", "accuracy")
        self.ocr_profile.setToolTip(
            "Fast: 1920px target, lowest latency. "
            "Moderate: 2560px target, recommended default. "
            "Accurate: 3200px target and forced 2×2 tiles, highest CPU/RAM."
        )
        profile_index = self.ocr_profile.findData(settings.ocr_profile)
        self.ocr_profile.setCurrentIndex(max(0, profile_index))
        form.addRow("OCR profile", self.ocr_profile)

        lang_row = QHBoxLayout()
        self.ocr_lang = QLineEdit("ja")
        self.ocr_lang.setReadOnly(True)
        self.ocr_lang.setToolTip("Paddle mode is Japanese-only.")
        lang_row.addWidget(self.ocr_lang)
        form.addRow("OCR language", lang_row)

        self.hotkey_region = QLineEdit(settings.hotkey_region)
        form.addRow("Region hotkey", self.hotkey_region)

        self.hotkey_window = QLineEdit(settings.hotkey_window)
        form.addRow("Active window hotkey", self.hotkey_window)

        self.privacy = QCheckBox(
            "I understand extracted text is sent to Google / MyMemory for translation"
        )
        self.privacy.setChecked(settings.privacy_acknowledged)
        form.addRow(self.privacy)

        self.debug = QCheckBox("Debug: save last capture to %TEMP%")
        self.debug.setChecked(settings.debug_save_capture)
        form.addRow(self.debug)

        self.debug_ocr = QCheckBox(
            "Debug OCR: log preprocess + raw/post OCR under %TEMP%\\pylens_ocr\\"
        )
        self.debug_ocr.setChecked(settings.debug_ocr)
        form.addRow(self.debug_ocr)

        form.addRow(QLabel("— Overlay —"))

        self.always_shrink = QCheckBox("Always shrink chip font (expect longer English)")
        self.always_shrink.setChecked(settings.overlay_always_shrink_font)
        form.addRow(self.always_shrink)

        self.shrink_pt = QLineEdit(str(settings.overlay_always_shrink_pt))
        self.shrink_pt.setToolTip("Points subtracted from preferred font when always-shrink is on (e.g. 4)")
        form.addRow("Always-shrink amount (pt)", self.shrink_pt)

        self.collide_shrink = QCheckBox("Shrink fonts further when chips overlap")
        self.collide_shrink.setChecked(settings.overlay_shrink_on_collide)
        form.addRow(self.collide_shrink)

        self.hover_full = QCheckBox("Hover a chip to expand and show full text clearly")
        self.hover_full.setChecked(settings.overlay_hover_show_full)
        form.addRow(self.hover_full)

        layout.addLayout(form)

        self.ocr_status = QLabel("")
        self.ocr_status.setWordWrap(True)
        layout.addWidget(self.ocr_status)
        self._refresh_ocr_status()

        self.translation_status = QLabel("")
        self.translation_status.setWordWrap(True)
        layout.addWidget(self.translation_status)
        self._refresh_translation_status()

        hint = QLabel(
            "Primary OCR: PaddleOCR (Japanese only). Models stay under the project "
            f"folder ({paddle_models_dir()}). Windows OCR remains available as secondary. "
            "PyLens never downloads models automatically."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666;")
        layout.addWidget(hint)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _selected_engine(self) -> str:
        data = self.engine.currentData()
        return str(data) if data else "paddle"

    def _selected_translation_engine(self) -> str:
        data = self.translation_engine.currentData()
        return str(data) if data else "argos"

    def _refresh_ocr_status(self) -> None:
        adapter = create_ocr_adapter(
            self._selected_engine(),
            auto_download=False,
        )
        message = adapter.readiness_message("ja")
        color = "#1e7e34" if adapter.is_ready("ja") else "#c0392b"
        self.ocr_status.setStyleSheet(f"color: {color};")
        self.ocr_status.setText(message)

    def _refresh_translation_status(self) -> None:
        if not hasattr(self, "translation_status"):
            return
        engine = self._selected_translation_engine()
        is_google = engine == "google"
        self.privacy.setEnabled(is_google)
        if is_google:
            self.translation_status.setStyleSheet("color: #b26a00;")
            self.translation_status.setText(
                "Online mode: OCR text is sent to Google, then MyMemory on failure."
            )
            return

        raw = self.target.text().strip().lower() or "en"
        target = raw.split("-")[0]
        # Offline Argos is JA↔EN only. Status must never throw for ko/zh/etc.
        if target not in ("en", "ja"):
            self.translation_status.setStyleSheet("color: #c0392b;")
            self.translation_status.setText(
                f"Argos offline supports only JA↔EN (target={raw}). "
                "Set target to en, or switch Translation to Google / MyMemory for ko/zh/etc."
            )
            return

        source = "ja" if target == "en" else "en"
        translator = ArgosTranslator(argos_models_dir())
        try:
            ready = translator.is_ready(source, target)
            message = translator.readiness_message(source, target)
        except Exception as ex:
            ready = False
            message = f"Could not check Argos status: {ex}"
        self.translation_status.setStyleSheet(
            "color: #1e7e34;" if ready else "color: #c0392b;"
        )
        self.translation_status.setText(message)

    def _save(self) -> None:
        translation_engine = self._selected_translation_engine()
        if translation_engine == "google" and not self.privacy.isChecked():
            QMessageBox.warning(
                self,
                "Privacy",
                "Please acknowledge that OCR text is sent to online translators.",
            )
            return

        engine = self._selected_engine()
        adapter = create_ocr_adapter(engine, auto_download=False)
        if engine == "paddle" and not adapter.is_ready("ja"):
            QMessageBox.warning(
                self,
                "PaddleOCR not ready",
                adapter.readiness_message("ja")
                + f"\n\nPlace approved model files under:\n{paddle_models_dir()}",
            )

        self._settings.target_lang = self.target.text().strip() or "en"
        self._settings.translation_engine = translation_engine
        self._settings.ocr_engine = engine
        self._settings.ocr_language = "ja"
        self._settings.ocr_profile = str(self.ocr_profile.currentData())
        self._settings.paddle_auto_download = False
        self._settings.hotkey_region = self.hotkey_region.text().strip().lower()
        self._settings.hotkey_window = self.hotkey_window.text().strip().lower()
        self._settings.privacy_acknowledged = True
        self._settings.debug_save_capture = self.debug.isChecked()
        self._settings.debug_ocr = self.debug_ocr.isChecked()
        self._settings.overlay_always_shrink_font = self.always_shrink.isChecked()
        try:
            self._settings.overlay_always_shrink_pt = max(0.0, float(self.shrink_pt.text().strip() or "4"))
        except ValueError:
            self._settings.overlay_always_shrink_pt = 4.0
        self._settings.overlay_shrink_on_collide = self.collide_shrink.isChecked()
        self._settings.overlay_hover_show_full = self.hover_full.isChecked()
        self._settings.first_run_done = True
        self._settings.save()
        self.accept()
