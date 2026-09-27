# PyLens

Cross-platform in-place desktop screen translator — a Python take on [WinLens](https://github.com/marco-beltrame/WinLens).

Press a hotkey, capture a **region** or the **active window**, run **OCR** (Windows OCR / macOS Vision / PaddleOCR / Tesseract), translate with **Argos (offline)** or **Google/MyMemory (online)**, and show translated text over the original.

## Supported Platforms

| Platform | OCR Engines | Hotkeys | System Tray |
|----------|-------------|---------|-------------|
| Windows 10/11 | Windows OCR, PaddleOCR | Win32 RegisterHotKey | ✅ |
| macOS 12+ | Apple Vision (native), PaddleOCR | Carbon HotKey API | ✅ |
| Linux (X11/Wayland) | Tesseract, PaddleOCR | X11 Grab / D-Bus | ✅ |

## Requirements

- Python 3.11+
- Platform-specific dependencies (installed automatically via `setup.sh` / `setup.bat`)

## Quick Start

### Windows
```powershell
cd C:\path\to\pylens
.\setup.bat
.\run-pylens.bat
```

### macOS / Linux
```bash
cd /path/to/pylens
chmod +x setup.sh run-pylens.sh
./setup.sh
./run-pylens.sh
```

### Manual Setup (any platform)
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate.bat
pip install -e ".[dev]"
# Platform-specific:
# Windows: pip install -r requirements-windows.txt
# macOS:   pip install -r requirements-macos.txt
# Linux:   pip install -r requirements-linux.txt
pylens
```

## Download Models

```bash
# Download all models (PaddleOCR Japanese + Argos JA↔EN)
python scripts/download_models.py --all

# Or individually
python scripts/download_models.py --paddle --argos --install-argos
```

## Usage

1. Run `pylens` — tray icon appears
2. First launch opens Settings — acknowledge privacy
3. Use hotkeys to capture and translate:

| Action | Windows/Linux | macOS |
|--------|---------------|-------|
| Translate region | `Ctrl+Alt+R` | `Option+Ctrl+R` |
| Translate active window | `Ctrl+Alt+T` | `Option+Ctrl+T` |
| Dismiss overlay / cancel region | `Esc` | `Esc` |

## OCR Engines

- **PaddleOCR** (cross-platform, Japanese primary) — models in `models/paddle/`
- **Windows OCR** (Windows only) — requires Japanese language pack
- **Apple Vision** (macOS only) — native, no models needed
- **Tesseract** (Linux) — install `tesseract-ocr` + language packs

## Translation Engines

- **Argos Translate** (offline, JA↔EN) — models in `models/argos/`
- **Google / MyMemory** (online) — requires internet

## Privacy

- Screenshots stay in memory and are not uploaded.
- Only extracted text strings are sent to translation providers.
- Debug logs written to platform-appropriate temp directory.

## Project Structure

```
pylens/
├── setup.sh / setup.bat          # Platform-specific setup
├── run-pylens.sh / run-pylens.bat # Platform-specific launchers
├── requirements-*.txt            # Platform-specific dependencies
├── scripts/download_models.py    # Cross-platform model downloader
├── src/pylens/
│   ├── platform/                 # Platform detection
│   ├── capture/                  # Screen capture (region/window)
│   ├── hotkeys/                  # Global hotkey registration
│   ├── dpi/                      # DPI/scale handling
│   ├── ocr/                      # OCR adapters (Paddle, Windows, Vision, Tesseract)
│   ├── translate/                # Translation providers (Argos, Google)
│   ├── overlay/                  # Translation overlay UI
│   └── app.py                    # Main application
└── tests/                        # Unit tests
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check src tests
```

## Architecture

```
Hotkey → Capture (region/window) → OCR Adapter → Translation → Overlay
```

OCR uses an **adapter pattern**:
- **PaddleOCR** (cross-platform, Japanese) — models under `models/paddle/`
- **Windows OCR** (Windows) — system OCR
- **Apple Vision** (macOS) — native framework
- **Tesseract** (Linux) — traditional OCR

Translation providers:
- **Argos Translate** (offline) — models under `models/argos/`
- **Google / MyMemory** (online)