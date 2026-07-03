"""
Setup script for Predictive Maintenance Library
"""

from pathlib import Path

from setuptools import find_packages, setup

# Read README
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text()

# Read requirements
requirements = []
with open(this_directory / "requirements.txt") as f:
    requirements = [
        line.strip() for line in f if line.strip() and not line.startswith("#")
    ]

setup(
    name="predictive-maintenance-library",
    version="0.1.0",
    author="ThingsBoard Team",
    author_email="info@thingsboard.io",
    description="A comprehensive library for predictive maintenance in industrial IoT applications",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/thingsboard/thingsboard",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries :: Python Modules",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0.0",
            "pytest-cov>=3.0.0",
            "black>=22.0.0",
            "flake8>=4.0.0",
            "mypy>=0.950",
        ],
        "viz": [
            "matplotlib>=3.4.0",
            "seaborn>=0.11.0",
            "plotly>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "pm-train=library.cli:train_command",
            "pm-predict=library.cli:predict_command",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
