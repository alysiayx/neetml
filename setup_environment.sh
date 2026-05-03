#!/bin/bash

# Check if virtual environment folder already exists
if [ ! -d "neet_ml_env" ]; then
    # Create a virtual environment
    echo "Creating a virtual environment..."
    python -m venv neet_ml_env
else
    echo "Virtual environment already exists."
fi

# Activate the virtual environment
echo "Activating the virtual environment..."
source neet_ml_env/bin/activate

# Install the package using the setup.py in editable mode
echo "Installing the neet-ml package..."
pip install -e .

echo "Setup is complete. The environment 'neet_ml_env' is ready to use."
echo "To activate the virtual environment, use 'source neet_ml_env/bin/activate' in this terminal."