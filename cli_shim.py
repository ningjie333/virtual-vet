#!/usr/bin/env python3
"""Entry point shim for vet-monitor CLI."""
import os
import sys

# Ensure both project root and src/ are on sys.path
# (src/ is needed because simulation.py uses 'from blood import ...')
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_PROJECT_ROOT, "src")
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from src.cli import main

if __name__ == "__main__":
    main()
