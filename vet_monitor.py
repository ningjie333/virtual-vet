#!/usr/bin/env python3
"""Entry point for vet-monitor CLI."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from src.ascii_dashboard import main
main()
