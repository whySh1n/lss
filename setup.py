"""Compatibility shim.

Project metadata lives in ``pyproject.toml`` (PEP 621). This file exists
only so that tools expecting a ``setup.py`` (older Debian tooling, some
CI setups) continue to work.
"""

from setuptools import setup

if __name__ == "__main__":
    setup()
