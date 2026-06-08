#!/bin/bash
# Setup script for Sklik PPC App

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "Setting up Sklik PPC App..."

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 is required but not found."
    exit 1
fi

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate and install
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

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
