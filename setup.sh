#!/bin/bash

echo "Installing Python requirements..."

# Try normal install first
pip install -r requirements.txt

# Check if previous command failed
if [ $? -ne 0 ]; then
    echo "Normal install failed. Creating virtual environment..."

    python3 -m venv venv
    source venv/bin/activate

    pip install --upgrade pip
    pip install -r requirements.txt

    echo "Dependencies installed inside virtual environment."
else
    echo "Dependencies installed successfully."
fi
