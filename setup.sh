#!/bin/bash
# PyLens macOS/Linux setup script
# Creates virtual environment and installs dependencies

set -e

echo "=== PyLens Setup (macOS/Linux) ==="

# Check Python version - use python3.12 if available
if command -v python3.12 &> /dev/null; then
    PYTHON_CMD="python3.12"
elif command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
else
    echo "Error: Python 3 not found"
    exit 1
fi

PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
echo "Python version: $PYTHON_VERSION"

# Verify Python 3.11+
PYTHON_MAJOR=$(echo $PYTHON_VERSION | cut -d. -f1)
PYTHON_MINOR=$(echo $PYTHON_VERSION | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    echo "Error: Python 3.11+ required"
    exit 1
fi

# Create venv
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment in $VENV_DIR..."
    $PYTHON_CMD -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists"
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install base requirements
echo "Installing base requirements..."
pip install -r requirements-base.txt

# Install macOS-specific requirements
echo "Installing macOS requirements..."
pip install -r requirements-macos.txt

# Install dev requirements
echo "Installing dev requirements..."
pip install -r requirements-dev.txt

# Install PyLens in editable mode
echo "Installing PyLens in editable mode..."
pip install -e .

echo ""
echo "=== Setup complete! ==="
echo "Activate the environment with: source .venv/bin/activate"
echo "Run PyLens with: pylens"
echo ""
echo "Next steps:"
echo "1. Download models: python scripts/download_models.py"
echo "2. Run PyLens: pylens"