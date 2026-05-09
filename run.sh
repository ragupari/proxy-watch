#!/bin/bash
set -e

echo "Starting ProxyMaze setup..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null
then
    echo "python3 could not be found. Please install Python 3."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install requirements
echo "Installing dependencies..."
pip install -r requirements.txt

# Run the application
echo "Starting ProxyMaze server..."
uvicorn src.main:app --host 0.0.0.0 --port 8000
