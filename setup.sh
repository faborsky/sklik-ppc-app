#!/bin/bash
# Setup script for Sklik PPC App

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Setting up Sklik PPC App..."

# Check Python (Windows installs often provide only `python`, not `python3`)
if command -v python3 &> /dev/null; then
    PY=python3
elif command -v python &> /dev/null; then
    PY=python
else
    echo "Error: python3 is required but not found."
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    "$PY" -m venv venv
fi

# Activate and install (venv/bin on Linux/macOS, venv/Scripts on Windows Git Bash).
# `python -m pip` rather than `pip`: on Windows pip cannot replace its own pip.exe
# while running it.
echo "Installing dependencies..."
if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    source venv/Scripts/activate
fi
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

# Create .env from example if it doesn't exist
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "Created .env file. Please edit it and add your SKLIK_API_TOKEN."
fi

echo ""
echo "Setup complete!"
echo ""
echo "Run commands with: ./run.sh <command> [flags]"
echo "Or activate the environment: source venv/bin/activate"
