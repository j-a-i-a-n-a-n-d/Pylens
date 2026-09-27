@echo off
REM PyLens Windows launcher

cd /d "%~dp0"

REM Activate virtual environment
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
) else (
    echo Virtual environment not found. Run setup.bat first.
    pause
    exit /b 1
)

REM Run PyLens
python -m pylens.app %*