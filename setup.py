"""
Development Installation Script

This setup.py script is used to install the package in "editable" mode,
which allows developers to work on the package's source code directly
without needing to reinstall it after each change.

To install the package in editable mode, run:
    pip install -e .

Author: Yanhua Xu
"""

from setuptools import setup, find_packages
import os
from pathlib import Path


# # Update the path to the requirements.txt file
# requirements_path = os.path.join("guide_installation", "pip", "requirements.txt")

# # list dependencies from file
# with open(requirements_path) as f:
#     content = f.readlines()
# requirements = [x.strip() for x in content]

ROOT = Path(__file__).parent
requirements = (ROOT / "guide_installation" / "pip" / "requirements.txt").read_text().splitlines()


setup(
    name="neetml",
    version="0.1.0",
    description="A machine learning package to predict NEET risk among students.",
    
    # packages=find_packages(),
    
    packages=find_packages(
        include=["neetml", "neetml.*"],
        exclude=["neetml.tests", "neetml.tests.*", "*_TBD*"],
    ),
    
    # package_dir={'': '.'}, 
    install_requires=requirements,
    
    entry_points={
        'console_scripts': [
            'neetml=neetml.cli:main',
        ]
    },
    
    author="Yanhua Xu",
    
    package_data={
        "assets.models": ["*.pkl"],
        "assets.templates": ["*.csv"],
    },
    
    python_requires='>=3.11',
)