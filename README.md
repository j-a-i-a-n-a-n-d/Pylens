# PyLens

In-place desktop screen translator for Windows — a Python take on [WinLens](https://github.com/marco-beltrame/WinLens).

Press a hotkey, capture a **region** or the **active window**, run **Windows OCR**, translate with **Google gtx → MyMemory**, and show English over the original text.

## Requirements

- Windows 10/11
- Python 3.11+
- Japanese (or other) **OCR language pack**:
  - Settings → Time & Language → Language & region → Japanese → Language options → **Optical character recognition**

## Install

```powershell
cd c:\Users\ve00ym959\py-lens
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

## Run

```powershell
pylens
# or
python -m pylens.app
```

Tray icon appears. First launch opens Settings — acknowledge privacy (OCR text is sent to Google/MyMemory).

### Hotkeys (defaults)

| Action | Hotkey |
|---|---|
| Translate region | `Ctrl+Alt+R` |
| Translate active window | `Ctrl+Alt+T` |
| Dismiss overlay / cancel region | `Esc` |

## Privacy

- Screenshots stay in memory and are not uploaded.
- Only extracted text strings are sent to `translate.googleapis.com` (primary) and MyMemory (fallback).
- Failures log to `%TEMP%\pylens.log` (no full document dumps by default).

## Architecture

```
Hotkey → capture → OCR adapter (Windows | Paddle) → Google gtx / MyMemory → overlay
```

OCR uses an **adapter pattern**:
- **PaddleOCR (Japanese only)** — primary; models under `<project>/models/paddle/`
- **Windows OCR** — secondary fallback
- Translation: Google gtx → MyMemory (unchanged)

```
pip install -e ".[paddle]"
```

Then either click **Download Japanese models** in Settings, or leave auto-download on (first capture pulls models into the project folder).

## Dev

```powershell
pytest
ruff check src tests
```
# Pylens
