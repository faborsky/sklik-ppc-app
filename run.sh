#!/bin/bash
# Run the Sklik PPC App with its virtual environment

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Check if venv exists
if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Running setup first..."
    ./setup.sh
fi

# Activate venv and run. The venv layout differs by platform: venv/bin on
# Linux/macOS, venv/Scripts on Windows (Git Bash). UTF-8 is forced because the
# Windows console/pipes default to a legacy code page and would mangle the
# Czech output and --json.
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    source venv/Scripts/activate
fi
PYTHONUTF8=1 PYTHONIOENCODING=utf-8 python sklik_cli.py "$@"
