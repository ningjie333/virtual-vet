import sys
import os
import pytest

# Add project root and src/ to path so that `from src.xxx import ...` and
# bare `from blood import ...` (used inside src/) both work.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "src"))


def pytest_configure(config):
    """Register custom marks."""
    config.addinivalue_line("markers", "slower: tests that take noticeably longer to run")
    config.addinivalue_line("markers", "slow: long-running tests (>2s); excluded from --quick gate")
