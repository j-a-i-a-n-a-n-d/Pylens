#!/bin/bash
# PyLens macOS/Linux launcher

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
else
    echo "Virtual environment not found. Run ./setup.sh first."
    exit 1
fi

# Set environment variables for macOS
export QT_MAC_WANTS_LAYER=1
export QT_QPA_PLATFORM=cocoa

# Run PyLens
exec python -m pylens.app "$@"