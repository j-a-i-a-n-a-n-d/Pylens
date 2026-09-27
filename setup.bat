@echo off
REM PyLens Windows setup script
REM Creates virtual environment and installs dependencies

echo === PyLens Setup (Windows) ===

REM Check Python version
python --version

REM Create venv
if not exist ".venv" (
    echo Creating virtual environment in .venv...
    python -m venv .venv
) else (
    echo Virtual environment already exists
)

REM Activate venv
call .venv\Scripts\activate.bat

REM Upgrade pip
echo Upgrading pip...
python -m pip install --upgrade pip

REM Install base requirements
echo Installing base requirements...
pip install -r requirements-base.txt

REM Install Windows-specific requirements
echo Installing Windows requirements...
pip install -r requirements-windows.txt

REM Install dev requirements
echo Installing dev requirements...
pip install -r requirements-dev.txt

REM Install PyLens in editable mode
echo Installing PyLens in editable mode...
pip install -e .

echo.
echo === Setup complete! ===
echo Activate the environment with: .venv\Scripts\activate.bat
echo Run PyLens with: pylens
echo.
echo Next steps:
echo 1. Download models: python scripts\download_models.py
echo 2. Run PyLens: pylens

pause