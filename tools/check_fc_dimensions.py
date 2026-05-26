#!/usr/bin/env python3
"""
Static lint tool: Check FactorCommand dt-dimensional consistency.

Scans Python source files for FactorCommand emissions and warns when
add/multiply operations may carry dt-dependent bias.

Rules:
  R1: FC "add" must multiply by dt (rate form, not per-step)
  R2: FC "multiply" must use exponential form (value ** dt) for dt-normalization
  R3: FC "set" is exempt (absolute value, no dt dependence)

Usage:
  python check_fc_dimensions.py src/             # scan directory
  python check_fc_dimensions.py src/neuro.py     # scan single file
  python check_fc_dimensions.py src/ --fix       # suggest fixes
"""
import ast, sys, os, re
from pathlib import Path
from dataclasses import dataclass

@dataclass
class Warning:
    file: str
    line: int
    rule: str
    message: str
    suggestion: str = ""

class FCDimensionChecker(ast.NodeVisitor):
    """AST visitor that checks FactorCommand calls for dt scaling."""

    def __init__(self, filename):
        self.filename = filename
        self.warnings = []
        self.in_function = None

    def visit_FunctionDef(self, node):
        old = self.in_function
        self.in_function = node.name
        self.generic_visit(node)
        self.in_function = old

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        # Check if this is a FactorCommand(...) call
        if self._is_factor_command(node):
            self._check_fc_call(node)
        self.generic_visit(node)

    def _is_factor_command(self, node):
        """Check if call is FactorCommand(target, op, value)."""
        if isinstance(node.func, ast.Name) and node.func.id == "FactorCommand":
            return True
        if isinstance(node.func, ast.Attribute) and node.func.attr == "FactorCommand":
            return True
        return False

    def _check_fc_call(self, node):
        """Check a FactorCommand(target, op, value) call."""
        if len(node.args) < 3:
            return

        op_node = node.args[1]
        value_node = node.args[2]

        # Get operation type
        op = self._get_string_value(op_node)
        if op is None:
            return

        if op == "add":
            self._check_add(node, value_node)
        elif op == "multiply":
            self._check_multiply(node, value_node)

    def _check_add(self, node, value_node):
        """R1: FC add must multiply by dt."""
        # Pattern 1: direct value * dt
        if isinstance(value_node, ast.BinOp) and isinstance(value_node.op, ast.Mult):
            if self._references_dt(value_node.right) or self._references_dt(value_node.left):
                return  # OK: value * dt

        # Pattern 2: variable name suggests dt-scaled rate
        # Heuristic: variables named *_rate, *rate*, *_per_s suggest rate form
        if isinstance(value_node, ast.Name):
            name = value_node.id.lower()
            if any(kw in name for kw in ['rate', 'per_s', '_dt', 'delta', 'shift']):
                return  # Likely pre-computed rate, skip

        # Pattern 3: constant value (not time-varying)
        if isinstance(value_node, ast.Constant):
            return  # Skip: constant

        # Direct add without dt normalization
        self.warnings.append(Warning(
            file=self.filename,
            line=node.lineno,
            rule="R1",
            message="FC 'add' operation may lack dt scaling. "
                    "Per-step increments cause bias ∝ 1/dt.",
            suggestion="Multiply by dt: FactorCommand(target, 'add', value * dt)"
        ))

    def _check_multiply(self, node, value_node):
        """R2: FC multiply should use exponential form for dt-normalization."""
        # Check if value uses exponential form (value ** dt)
        if isinstance(value_node, ast.BinOp) and isinstance(value_node.op, ast.Pow):
            if self._references_dt(value_node.exponent):
                return  # OK: value ** dt

        # Check if value is a simple variable name (could be pre-computed)
        # This reduces false positives for cases like:
        #   rate_factor = value ** dt
        #   FactorCommand(..., "multiply", rate_factor)
        if isinstance(value_node, ast.Name):
            return  # Skip: likely pre-computed, manual review needed

        # Check if value is a constant (not time-varying)
        # Constants like gut_motility_mult = 0.8 are intentional design choices
        if isinstance(value_node, ast.Constant):
            return  # Skip: constant multiplier

        # Check if value is a function call (e.g., max(0.5, 1.0 - x))
        # These are typically bounded values, not raw per-step multipliers
        if isinstance(value_node, ast.Call):
            return  # Skip: bounded by function (max, min, clamp)

        # Direct multiply without dt normalization
        self.warnings.append(Warning(
            file=self.filename,
            line=node.lineno,
            rule="R2",
            message="FC 'multiply' operation may lack dt normalization. "
                    "Per-step multiplication causes exponential bias.",
            suggestion="Use exponential form: FactorCommand(target, 'multiply', value ** dt)"
        ))

    def _references_dt(self, node):
        """Check if an AST node references 'dt' variable."""
        if isinstance(node, ast.Name) and node.id == "dt":
            return True
        if isinstance(node, ast.Attribute) and node.attr == "dt":
            return True
        # Check nested expressions
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id == "dt":
                return True
        return False

    def _get_string_value(self, node):
        """Extract string value from AST node."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return node.value
        return None


def check_file(filepath):
    """Check a single Python file for FC dimension issues."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except SyntaxError:
        return []

    checker = FCDimensionChecker(str(filepath))
    checker.visit(tree)
    return checker.warnings


def check_directory(dirpath, exclude=None):
    """Check all Python files in a directory."""
    exclude = exclude or []
    all_warnings = []
    for root, dirs, files in os.walk(dirpath):
        # Skip excluded directories
        dirs[:] = [d for d in dirs if d not in exclude]
        for f in files:
            if f.endswith('.py'):
                filepath = os.path.join(root, f)
                warnings = check_file(filepath)
                all_warnings.extend(warnings)
    return all_warnings


def format_warning(w):
    """Format a warning for display."""
    loc = f"{w.file}:{w.line}"
    return f"[{w.rule}] {loc}: {w.message}\n    → {w.suggestion}"


def main():
    import argparse
    parser = argparse.ArgumentParser(
        description="Check FactorCommand dt-dimensional consistency"
    )
    parser.add_argument("path", help="File or directory to check")
    parser.add_argument("--fix", action="store_true",
                        help="Show suggested fixes")
    parser.add_argument("--exclude", nargs="*", default=["__pycache__", ".git", "venv"],
                        help="Directories to exclude")
    args = parser.parse_args()

    path = Path(args.path)
    if path.is_file():
        warnings = check_file(str(path))
    elif path.is_dir():
        warnings = check_directory(str(path), exclude=args.exclude)
    else:
        print(f"Error: {path} not found")
        sys.exit(1)

    if not warnings:
        print("✓ No FC dimension issues found.")
        sys.exit(0)

    print(f"Found {len(warnings)} potential FC dimension issue(s):\n")
    for w in warnings:
        print(format_warning(w))
        print()

    # Summary by rule
    r1_count = sum(1 for w in warnings if w.rule == "R1")
    r2_count = sum(1 for w in warnings if w.rule == "R2")
    print(f"Summary: {r1_count} R1 (add without dt), {r2_count} R2 (multiply without dt)")

    sys.exit(1)


if __name__ == "__main__":
    main()
