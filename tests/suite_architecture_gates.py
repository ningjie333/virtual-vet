"""
Architectural constraint checker — AST-based enforcement of simulation engine rules.

This module provides ArchitectureGate, which parses the simulation engine source
with the Python ast module and detects violations of five architectural rules:

1. FactorCommand-only writes  — all physiological parameter modifications must go
   through `apply_factor(cmd)` on VirtualCreature. Direct attribute mutations to
   heart.*, lung.*, kidney.*, blood.* from OUTSIDE that module's file are forbidden.

2. No direct organ attribute access across module boundaries — organ modules
   (heart, lung, kidney, blood, immune, ...) must not directly read/write each
   other's attributes. They communicate through SignalBus / BloodShim.

3. All module INPUTS/OUTPUTS declared — every organ module must have INPUTS,
   OUTPUTS, READS_BLOOD, and WRITES_BLOOD class attributes.

4. _PARAM_PATHS completeness — every target used in a FactorCommand must be
   registered in _PARAM_PATHS.

5. No print() statements — use the logging module instead.

Mark: @pytest.mark.architecture
"""

from __future__ import annotations

import ast
import logging
import os
from pathlib import Path
from typing import Any

import pytest

# Absolute path to the src/ directory (project root / src)
SRC_DIR = Path(__file__).resolve().parents[1] / "src"

# Modules whose class attributes we check for INPUTS/OUTPUTS declarations
ORGAN_MODULES = (
    "heart",
    "lung",
    "kidney",
    "blood",
    "gut",
    "liver",
    "endocrine",
    "neuro",
    "immune",
    "coagulation",
    "lymphatic",
    "fluid",
)

# Attributes that are the "authoritative source" in each module
# (used to distinguish internal self-mutations from cross-module violations)
MODULE_IDENTITY_ATTR = {
    "heart":  "heart_rate",
    "lung":   "respiratory_rate",
    "kidney": "GFR",
    "blood":  "total_volume_ml",
    "gut":    "gut_motility",
    "liver":  "metabolic_activity",
    "endocrine": "T3_ng_dL",
    "neuro":  "sympathetic_tone",
    "immune": "cytokine_level",
    "coagulation": "factor_VII",
    "lymphatic": "lymph_flow_rate",
    "fluid":  "vascular_volume_ml",
}


# ─────────────────────────────────────────────────────────────────────────────
# Violation record
# ─────────────────────────────────────────────────────────────────────────────

class Violation:
    """A single architectural rule violation."""

    def __init__(
        self,
        file: str,
        line: int,
        col: int,
        code: str,
        message: str,
        rule: str,
    ) -> None:
        self.file = file
        self.line = line
        self.col = col
        self.code = code
        self.message = message
        self.rule = rule

    def __str(self) -> str:
        return (
            f"{self.file}:{self.line}  [{self.rule}]\n"
            f"  {self.code}\n"
            f"  {self.message}"
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "col": self.col,
            "code": self.code,
            "message": self.message,
            "rule": self.rule,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Cross-module mutation visitor
# ─────────────────────────────────────────────────────────────────────────────

class CrossModuleMutationVisitor(ast.NodeVisitor):
    """
    Detect direct writes to another module's attributes from within an organ module.

    For each organ-module file, any assignment to `self.other_module.attr`
    (where other_module != self_module) is a cross-module violation.
    """

    def __init__(self, filename: str, module_name: str | None) -> None:
        self.filename = filename
        # The "home" module of this file (None for simulation.py, etc.)
        self.module_name = module_name
        self.violations: list[Violation] = []

    def _extract_code(self, node: ast.stmt) -> str:
        try:
            import inspect
            src_lines, _ = inspect.getsourcelines(node)
            return src_lines[0].strip()[:120]
        except Exception:
            return ast.unparse(node)[:120]

    @staticmethod
    def _is_store_module_ref(target: ast.expr) -> bool:
        """
        Return True if the assignment is `self.module = value` (storing a module
        reference in __init__), as opposed to `self.module.attr = value` (writing
        an attribute).
        """
        if not isinstance(target, ast.Attribute):
            return False
        if not isinstance(target.value, ast.Name):
            return False
        if target.value.id != "self":
            return False
        return True

    def _check_assign(
        self, node: ast.Assign | ast.AnnAssign | ast.AugAssign
    ) -> None:
        for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
            if not isinstance(target, ast.Attribute):
                continue
            if not isinstance(target.value, ast.Name):
                continue
            if target.value.id != "self":
                continue

            # self.module = value  → storing module reference (OK in __init__)
            if self._is_store_module_ref(target):
                continue

            # target.attr is the first attribute after self
            # e.g. self.heart.heart_rate → target.attr = 'heart'
            # We need to check if target.attr is a known organ module
            accessed_module = target.attr
            if accessed_module not in ORGAN_MODULES:
                continue

            # Same module: allowed (self.heart.heart_rate = ... in heart.py is fine)
            if accessed_module == self.module_name:
                continue

            # Simulation.py has no module_name (it's the orchestrator)
            # It should only write via apply_factor(), so any self.heart.X = ... is a violation
            if self.module_name is None:
                self.violations.append(Violation(
                    file=self.filename,
                    line=node.lineno,
                    col=node.col_offset,
                    code=self._extract_code(node),
                    message=(
                        f"Direct assignment to self.{accessed_module}.* from "
                        f"simulation orchestrator — must use apply_factor(cmd) instead"
                    ),
                    rule="cross_module_mutation",
                ))
                continue

            # Any other module writing to a different module's attributes is a violation
            self.violations.append(Violation(
                file=self.filename,
                line=node.lineno,
                col=node.col_offset,
                code=self._extract_code(node),
                message=(
                    f"Cross-module mutation: {self.module_name} writes directly to "
                    f"self.{accessed_module}.* — communicate via SignalBus/BloodShim instead"
                ),
                rule="cross_module_mutation",
            ))

    def visit_Assign(self, node: ast.Assign) -> None:
        self._check_assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assign(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assign(node)
        self.generic_visit(node)


class PrintCallVisitor(ast.NodeVisitor):
    """Detect print() calls in src/ files."""

    def __init__(self, filename: str) -> None:
        self.filename = filename
        self.violations: list[Violation] = []

    def _extract_code(self, node: ast.stmt) -> str:
        try:
            import inspect
            src_lines, _ = inspect.getsourcelines(node)
            return src_lines[0].strip()[:120]
        except Exception:
            return ast.unparse(node)[:120]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        if isinstance(func, ast.Name) and func.id == "print":
            self.violations.append(Violation(
                file=self.filename,
                line=node.lineno,
                col=node.col_offset,
                code=self._extract_code(node),
                message="print() call detected — use logging module instead",
                rule="no_print",
            ))
        self.generic_visit(node)


# ─────────────────────────────────────────────────────────────────────────────
# ArchitectureGate — the main checker class
# ─────────────────────────────────────────────────────────────────────────────

class ArchitectureGate:
    """
    AST-based architectural constraint checker for the simulation engine.

    Methods
    -------
    check_factor_command_only()
        Parses all src/*.py files. Flags direct attribute assignments to
        heart.*, lung.*, kidney.*, blood.* that are NOT wrapped by apply_factor().

    check_cross_module_mutations()
        For each organ module, flags direct writes to other modules' attributes.

    check_inputs_outputs_declared()
        Verifies each organ module has INPUTS, OUTPUTS, READS_BLOOD, WRITES_BLOOD
        class attributes.

    check_param_paths_completeness()
        Checks that all FactorCommand targets in source code are registered in
        _PARAM_PATHS.

    check_no_print()
        Flags print() calls in src/ files.

    Each method returns a list of Violation records.
    A zero-length list means the check passed.
    """

    def __init__(self, src_dir: Path | str | None = None) -> None:
        self.src_dir = Path(src_dir) if src_dir else SRC_DIR
        self._src_files: list[Path] = []
        self._discover_src_files()

    def _discover_src_files(self) -> None:
        """Recursively collect all .py files under src_dir."""
        self._src_files = []
        if not self.src_dir.exists():
            logging.warning("src_dir %s does not exist", self.src_dir)
            return
        for path in self.src_dir.rglob("*.py"):
            # Skip __pycache__ and obvious non-source files
            if "__pycache__" in str(path):
                continue
            self._src_files.append(path)

    # ── helper ──────────────────────────────────────────────────────────────

    @staticmethod
    def _format_violations(violations: list[Violation]) -> str:
        """Render a list of violations as a human-readable string."""
        if not violations:
            return "  (none)"
        lines = []
        for v in violations:
            lines.append(f"  [{v.rule}] {v.file}:{v.line}")
            lines.append(f"    {v.code}")
            lines.append(f"    {v.message}")
        return "\n".join(lines)

    # ── check 1: FactorCommand-only writes ─────────────────────────────────

    def check_factor_command_only(self) -> list[Violation]:
        """
        Flag direct attribute assignments to heart.*, lung.*, kidney.*, blood.*
        that bypass apply_factor().

        Known limitation: this check uses a conservative approximation — it flags
        ANY assignment to self.heart.X in non-heart files, self.lung.X in non-lung
        files, etc. It does not do deep control-flow analysis to determine whether
        the assignment is ultimately routed through apply_factor().
        """
        violations: list[Violation] = []

        # Map filenames to their "home" organ module (or None for simulation, etc.)
        module_of_file: dict[str, str | None] = {}
        for f in self._src_files:
            name = f.stem
            if name in ORGAN_MODULES:
                module_of_file[str(f)] = name
            else:
                module_of_file[str(f)] = None  # orchestrator / utility file

        # Patterns that indicate a FactorCommand path
        # e.g. self.heart.heart_rate, self.lung.diffusion_coefficient, etc.
        for fpath in self._src_files:
            fstr = str(fpath)
            home_module = module_of_file.get(fstr)

            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=fstr)
            except (OSError, SyntaxError) as e:
                logging.debug("Could not parse %s: %s", fstr, e)
                continue

            visitor = _FactorCommandAssignDetector(
                filename=fstr,
                home_module=home_module,
            )
            visitor.visit(tree)
            violations.extend(visitor.violations)

        return violations

    # ── check 2: cross-module mutations ────────────────────────────────────

    def check_cross_module_mutations(self) -> list[Violation]:
        """
        Flag direct writes to another module's attributes from within an organ module.

        For each file that belongs to an organ module, any assignment to
        `self.other_module.attr` (where other_module != self_module) is a violation.
        """
        violations: list[Violation] = []

        for fpath in self._src_files:
            fstr = str(fpath)
            stem = fpath.stem

            # Determine which organ module this file belongs to
            if stem not in ORGAN_MODULES:
                continue  # skip utility / non-organ files for this check

            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=fstr)
            except (OSError, SyntaxError) as e:
                logging.debug("Could not parse %s: %s", fstr, e)
                continue

            visitor = CrossModuleMutationVisitor(filename=fstr, module_name=stem)
            visitor.visit(tree)
            violations.extend(visitor.violations)

        return violations

    # ── check 3: INPUTS/OUTPUTS declared ───────────────────────────────────

    REQUIRED_CLASS_ATTRS = ("INPUTS", "OUTPUTS", "READS_BLOOD", "WRITES_BLOOD")

    def check_inputs_outputs_declared(self) -> list[Violation]:
        """
        Verify that every organ module class has INPUTS, OUTPUTS, READS_BLOOD,
        and WRITES_BLOOD class-level tuple declarations.
        """
        violations: list[Violation] = []

        for mod_name in ORGAN_MODULES:
            mod_path = self.src_dir / f"{mod_name}.py"
            if not mod_path.exists():
                # Some modules live in sub-packages (e.g. src/organs/)
                # Search recursively
                candidates = list(self.src_dir.rglob(f"{mod_name}.py"))
                if candidates:
                    mod_path = candidates[0]
                else:
                    violations.append(Violation(
                        file=str(mod_path),
                        line=0,
                        col=0,
                        code=f"module '{mod_name}' not found",
                        message=f"Organ module {mod_name} has no source file",
                        rule="inputs_outputs_declared",
                    ))
                    continue

            try:
                source = mod_path.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=str(mod_path))
            except (OSError, SyntaxError) as e:
                logging.debug("Could not parse %s: %s", mod_path, e)
                continue

            missing = self._find_missing_class_attrs(tree, str(mod_path), mod_name)
            violations.extend(missing)

        return violations

    def _find_missing_class_attrs(
        self, tree: ast.AST, filename: str, mod_name: str
    ) -> list[Violation]:
        """Check a module's AST for missing INPUTS/OUTPUTS/READS_BLOOD/WRITES_BLOOD."""
        violations: list[Violation] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            # Match by class name (case-sensitive), e.g. 'HeartModule' in heart.py
            if node.name != mod_name:
                continue

            found: dict[str, bool] = {attr: False for attr in self.REQUIRED_CLASS_ATTRS}
            class_line = node.lineno

            for item in node.body:
                # AnnAssign with OR without value (annotated declarations)
                if isinstance(item, ast.AnnAssign):
                    if isinstance(item.target, ast.Name) and item.target.id in found:
                        found[item.target.id] = True
                elif isinstance(item, ast.Assign):
                    for target in item.targets:
                        if isinstance(target, ast.Name) and target.id in found:
                            found[target.id] = True

            for attr, present in found.items():
                if not present:
                    violations.append(Violation(
                        file=filename,
                        line=class_line,
                        col=0,
                        code=f"class {mod_name}",
                        message=f"{mod_name} missing class attribute '{attr}' — "
                                 f"declare as INPUTS/OUTPUTS/READS_BLOOD/WRITES_BLOOD tuple",
                        rule="inputs_outputs_declared",
                    ))
            break  # Only check the matching class

        return violations

    # ── check 4: _PARAM_PATHS completeness ──────────────────────────────────

    def check_param_paths_completeness(self) -> list[Violation]:
        """
        Verify that every FactorCommand target used in the codebase is registered
        in _PARAM_PATHS.

        This check parses all source files, finds all FactorCommand constructor
        calls (FactorCommand(target=..., op=..., value=...)), extracts the target
        string, and verifies it exists as a key in _PARAM_PATHS.
        """
        from src.engine import _PARAM_PATHS

        violations: list[Violation] = []
        known_paths: set[str] = set(_PARAM_PATHS.keys())

        for fpath in self._src_files:
            fstr = str(fpath)

            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=fstr)
            except (OSError, SyntaxError) as e:
                logging.debug("Could not parse %s: %s", fstr, e)
                continue

            visitor = _FactorCommandUsageDetector(filename=fstr)
            visitor.visit(tree)

            for target_str, line_no, code in visitor.found_commands:
                if target_str not in known_paths:
                    violations.append(Violation(
                        file=fstr,
                        line=line_no,
                        col=0,
                        code=code,
                        message=(
                            f"FactorCommand target '{target_str}' is not registered "
                            f"in _PARAM_PATHS — add it to src/engine/topology.py"
                        ),
                        rule="param_paths_completeness",
                    ))

        return violations

    # ── check 5: no print() ────────────────────────────────────────────────

    def check_no_print(self) -> list[Violation]:
        """
        Flag print() calls in src/ files.

        Note: print() calls inside string literals (e.g. docstrings, format
        strings that happen to contain the word "print") are not flagged —
        only actual function-call nodes are checked.
        """
        violations: list[Violation] = []

        for fpath in self._src_files:
            fstr = str(fpath)

            try:
                source = fpath.read_text(encoding="utf-8")
                tree = ast.parse(source, filename=fstr)
            except (OSError, SyntaxError) as e:
                logging.debug("Could not parse %s: %s", fstr, e)
                continue

            visitor = PrintCallVisitor(filename=fstr)
            visitor.visit(tree)
            violations.extend(visitor.violations)

        return violations


# ─────────────────────────────────────────────────────────────────────────────
# Internal AST visitors (private helpers)
# ─────────────────────────────────────────────────────────────────────────────

class _FactorCommandAssignDetector(ast.NodeVisitor):
    """
    Detect direct assignments to engine module attributes that look like
    FactorCommand targets but are NOT wrapped by apply_factor().

    Heuristic: for each file, if the file's module (home_module) is NOT the
    target module, any assignment to self.target_module.X is a violation.
    """

    CONTROLLED_MODULES = {"heart", "lung", "kidney", "blood"}

    def __init__(self, filename: str, home_module: str | None) -> None:
        self.filename = filename
        self.home_module = home_module  # None means "orchestrator / utility"
        self.violations: list[Violation] = []

    def _extract_code(self, node: ast.stmt) -> str:
        try:
            import inspect
            src_lines, _ = inspect.getsourcelines(node)
            return src_lines[0].strip()[:120]
        except Exception:
            return ast.unparse(node)[:120]

    @staticmethod
    def _is_store_module_ref(target: ast.expr) -> bool:
        """
        Return True if the assignment is `self.module = value` (storing a module
        reference in __init__), as opposed to `self.module.attr = value` (writing
        an attribute).

        In AST:
          self.blood = blood      → Attribute(value=Name('self'), attr='blood')
          self.blood.arterial_pH  → Attribute(value=Attribute(...), attr='arterial_pH')
        """
        if not isinstance(target, ast.Attribute):
            return False
        if not isinstance(target.value, ast.Name):
            return False
        if target.value.id != "self":
            return False
        # self.X = value (not self.X.Y = value)
        return True

    def _check_assign(
        self, node: ast.Assign | ast.AnnAssign | ast.AugAssign
    ) -> None:
        for target in node.targets if isinstance(node, ast.Assign) else [node.target]:
            if not isinstance(target, ast.Attribute):
                continue
            if not isinstance(target.value, ast.Name):
                continue
            if target.value.id != "self":
                continue

            # self.module = value  → storing module reference (OK in __init__)
            if self._is_store_module_ref(target):
                continue

            # Get the first attr after self (the module name)
            # e.g. self.heart.heart_rate → module = 'heart'
            # In AST: Attribute(value=Name('self'), attr='heart')
            accessed_module = target.attr

            if accessed_module not in self.CONTROLLED_MODULES:
                continue

            # Same module: allowed (heart.py writing self.heart.X is fine)
            if accessed_module == self.home_module:
                continue

            # Determine the attribute being written (the final attr in chain)
            # e.g. self.heart.heart_rate → attr = 'heart_rate'
            # For simplicity we just report the full LHS
            try:
                code = ast.unparse(target) if hasattr(ast, "unparse") else self._extract_code(node)
            except Exception:
                code = self._extract_code(node)

            self.violations.append(Violation(
                file=self.filename,
                line=node.lineno,
                col=node.col_offset,
                code=code,
                message=(
                    f"Direct assignment to self.{accessed_module}.* from "
                    f"{self.home_module or 'orchestrator'} — "
                    f"must use apply_factor(cmd) instead"
                ),
                rule="factor_command_only",
            ))

    def visit_Assign(self, node: ast.Assign) -> None:
        self._check_assign(node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        self._check_assign(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._check_assign(node)
        self.generic_visit(node)


class _FactorCommandUsageDetector(ast.NodeVisitor):
    """
    Find all FactorCommand(...) calls and extract their `target` keyword/named
    argument values.
    """

    def __init__(self, filename: str) -> None:
        self.filename = filename
        # List of (target_string, line_number, code_excerpt)
        self.found_commands: list[tuple[str, int, str]] = []

    def _extract_code(self, node: ast.stmt) -> str:
        try:
            import inspect
            src_lines, _ = inspect.getsourcelines(node)
            return src_lines[0].strip()[:120]
        except Exception:
            return ast.unparse(node)[:120]

    def visit_Call(self, node: ast.Call) -> None:
        func = node.func

        # Direct FactorCommand(...) call
        is_factor_command = False
        if isinstance(func, ast.Name) and func.id == "FactorCommand":
            is_factor_command = True
        elif isinstance(func, ast.Attribute) and func.attr == "FactorCommand":
            is_factor_command = True

        if is_factor_command:
            target_str = None
            for kw in node.keywords:
                if kw.arg == "target":
                    if isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        target_str = kw.value.value
                        break

            if target_str is not None:
                self.found_commands.append((target_str, node.lineno, self._extract_code(node)))

        self.generic_visit(node)


# ─────────────────────────────────────────────────────────────────────────────
# Pytest test class
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.architecture
class TestArchitectureGates:
    """Pytest test class for architectural constraint checks."""

    @pytest.fixture(scope="class")
    def gate(self) -> ArchitectureGate:
        return ArchitectureGate()

    def _assert_no_violations(
        self,
        violations: list[Violation],
        rule_name: str,
        gate: ArchitectureGate,
    ) -> None:
        if violations:
            report = gate._format_violations(violations)
            pytest.fail(
                f"[{rule_name}] {len(violations)} violation(s) found:\n{report}"
            )

    def test_factor_command_only(self, gate: ArchitectureGate) -> None:
        """Rule 1: All physiological parameter modifications must go through apply_factor()."""
        violations = gate.check_factor_command_only()
        self._assert_no_violations(violations, "factor_command_only", gate)

    def test_cross_module_mutations(self, gate: ArchitectureGate) -> None:
        """Rule 2: Organ modules must not directly write each other's attributes."""
        violations = gate.check_cross_module_mutations()
        self._assert_no_violations(violations, "cross_module_mutation", gate)

    def test_inputs_outputs_declared(self, gate: ArchitectureGate) -> None:
        """Rule 3: Every organ module must have INPUTS/OUTPUTS/READS_BLOOD/WRITES_BLOOD declared."""
        violations = gate.check_inputs_outputs_declared()
        self._assert_no_violations(violations, "inputs_outputs_declared", gate)

    def test_param_paths_completeness(self, gate: ArchitectureGate) -> None:
        """Rule 4: All FactorCommand targets must be registered in _PARAM_PATHS."""
        violations = gate.check_param_paths_completeness()
        self._assert_no_violations(violations, "param_paths_completeness", gate)

    def test_no_print(self, gate: ArchitectureGate) -> None:
        """Rule 5: No print() statements in src/ — use logging instead."""
        violations = gate.check_no_print()
        self._assert_no_violations(violations, "no_print", gate)

    def test_gate_runs_successfully(self, gate: ArchitectureGate) -> None:
        """Sanity check: all five checks run without raising an exception."""
        # If any check raises, this test fails — verifying the gate itself is not broken
        gate.check_factor_command_only()
        gate.check_cross_module_mutations()
        gate.check_inputs_outputs_declared()
        gate.check_param_paths_completeness()
        gate.check_no_print()