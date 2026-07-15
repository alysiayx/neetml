#!/bin/bash

set -e

if ! command -v poetry >/dev/null 2>&1; then
    echo "Poetry is required. Install it from https://python-poetry.org/docs/#installation"
    exit 1
fi

if [ -z "${CONDA_PREFIX:-}" ]; then
    echo "Activate a Conda environment before running this script."
    exit 1
fi

echo "Installing NEETML into the active Conda environment: ${CONDA_PREFIX}"
poetry install

echo "Setup is complete. Keep the Conda environment active when using NEETML."
