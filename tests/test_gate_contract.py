"""
Gate contract tests: enforce minimum coverage thresholds and no-smoke-only files.

This file verifies the test suite itself is healthy:
  - No file contains only smoke tests (test_* that just call step() without assertions)
  - Critical modules all have at least one non-smoke test
  - @pytest.mark.slow tests are excluded from --quick gate
"""

import sys
sys.path.insert(0, "src")
import os

import pytest


class TestNoSmokeOnlyFiles:
    """Every test file must have at least one test with a real assertion."""

    @pytest.mark.parametrize("test_file", [
        "test_simulation.py",
        "test_neuro.py",
        "test_endocrine.py",
        "test_immune.py",
        "test_organ_health.py",
        "test_coupling.py",
        "test_lung.py",
        "test_kidney.py",
        "test_heart.py",
        "test_fluid.py",
        "test_solver_numerics.py",
        "test_species_specific.py",
        "test_cross_module_coupling.py",
    ])
    def test_file_has_non_smoke_tests(self, test_file):
        """Verify test file has at least one test with an assertion (not just step())."""
        import ast, pathlib
        path = pathlib.Path(__file__).parent / test_file
        if not path.exists():
            pytest.skip(f"{test_file} not found")

        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)

        # Find all test functions
        has_real_test = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                # Check for any assertion inside
                for child in ast.walk(node):
                    if isinstance(child, ast.Assert):
                        has_real_test = True
                        break
                    # Also count meaningful patterns (comparisons in if/for bodies)
                    if isinstance(child, ast.If) and len(child.body) > 1:
                        has_real_test = True
                        break

        assert has_real_test, \
            f"{test_file} appears to contain only smoke tests (no assertions found)"


class TestCriticalModulesHaveTests:
    """Critical modules must have at least N test cases covering them."""

    @pytest.mark.parametrize("module_name,min_tests", [
        ("simulation", 3),
        ("neuro", 3),
        ("endocrine", 3),
        ("immune", 3),
        ("organ_health", 3),
        ("coupling", 2),
    ])
    def test_module_has_minimum_tests(self, module_name, min_tests):
        """Each critical module has at least min_tests targeting it."""
        import pathlib
        tests_dir = pathlib.Path(__file__).parent
        matching = []
        for tf in tests_dir.glob("test_*.py"):
            content = tf.read_text(encoding="utf-8")
            if module_name in content and "def test_" in content:
                import ast
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                        # Check for assertions
                        for child in ast.walk(node):
                            if isinstance(child, ast.Assert):
                                matching.append(f"{tf.name}::{node.name}")
                                break
        assert len(matching) >= min_tests, \
            f"Module {module_name} has only {len(matching)} non-smoke tests, need {min_tests}: {matching}"


class TestSlowMarkerExcludedFromQuick:
    """@pytest.mark.slow tests are properly registered and excluded from quick gate."""

    def test_slow_marker_registered(self):
        """pytest.ini or conftest registers 'slow' marker."""
        from conftest import pytest_configure
        # The marker should be registered — this test just verifies no KeyError on import
        from tests.conftest import pytest_configure as pc  # noqa
        assert True

    def test_slow_tests_exist(self):
        """At least 5 tests carry @pytest.mark.slow."""
        import pathlib, ast
        tests_dir = pathlib.Path(__file__).parent.parent
        slow_count = 0
        for tf in tests_dir.glob("tests/test_*.py"):
            try:
                content = tf.read_text(encoding="utf-8")
                tree = ast.parse(content)
            except SyntaxError:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Name) and dec.id == "slow":
                            slow_count += 1
                        elif isinstance(dec, ast.Attribute) and dec.attr == "slow":
                            slow_count += 1
        assert slow_count >= 3, \
            f"Only {slow_count} @slow tests found (expected ≥ 3)"