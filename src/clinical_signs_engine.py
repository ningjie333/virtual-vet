"""
ClinicalSignsEngine — Observable clinical sign derivation from physiological parameters.

Responsibilities:
  - Evaluate sign rules against engine state every simulation step
  - Support species-aware thresholds (dog vs cat) via symptom_thresholds.json
  - Support three rule types: threshold, multi_parameter, and time-integrated
  - Track sign onset/offset with configurable delays to avoid flickering
  - Expose active signs to the report engine via get_sign_tags()

Rule types:
  - threshold:    single parameter comparison (e.g., bilirubin > 2.0 mg/dL)
  - multi_parameter: boolean expression over multiple params (OR/AND/comparison)
  - sustained:    threshold that must persist for a duration (for syncope etc.)

All thresholds are species-aware and loaded from data/symptom_thresholds.json.
Parameter resolution order: state (from get_state()) -> blood.* -> heart.* -> lung.*
"""

from __future__ import annotations

import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.clinical_state import extract_clinical_state

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Data types
# ──────────────────────────────────────────────


@dataclass
class SignInstance:
    """A clinical sign currently active on the creature."""
    sign_id: str
    display_name: str
    severity: str
    onset_time_s: float
    active: bool = True
    clue_id: str = ""


# ──────────────────────────────────────────────
# Unit conversion helpers
# ──────────────────────────────────────────────

def _mmol_to_mg_dL(mmol: float) -> float:
    """Convert mmol/L to mg/dL (for glucose)."""
    return mmol * 18.018


# ──────────────────────────────────────────────
# Main engine
# ──────────────────────────────────────────────


class ClinicalSignsEngine:
    """
    Evaluates observable clinical sign rules against the simulation engine state.

    Parameters
    ----------
    creature : VirtualCreature
        The simulation engine instance.
    definitions : dict
        Loaded content of symptom_definitions.json.
    species : str
        "dog" or "cat" — selects species-specific thresholds.
    """

    def __init__(
        self,
        creature: Any,
        definitions: dict,
        species: str = "dog",
    ):
        self._creature = creature
        self._defs = definitions
        self._species = species

        # Load species-specific thresholds
        thresholds_path = (
            Path(__file__).resolve().parents[1] / "data" / "symptom_thresholds.json"
        )
        with open(thresholds_path, "r", encoding="utf-8") as f:
            all_thresholds: dict = json.load(f)
        self._thresholds: dict = all_thresholds.get(
            species, all_thresholds.get("dog", {})
        )

        # Active sign instances
        self._active: dict[str, SignInstance] = {}

        # Onset/offset delay trackers (sign_id -> trigger timestamp)
        self._onset_delayed: dict[str, float] = {}
        self._offset_delayed: dict[str, float] = {}

        # Time-integrated accumulators (sign_id -> accumulated value)
        self._accumulators: dict[str, float] = {}

        # Sustained sign trackers (sign_id -> first trigger timestamp)
        self._sustained_since: dict[str, float] = {}

        # Conversion note: engine stores Glu in mmol/L; symptom rules use mg/dL
        self._glu_conversion_factor = 18.018  # mmol/L → mg/dL

    # ── Public API ────────────────────────────────────────────────

    def compute(self, current_time_s: float) -> dict[str, SignInstance]:
        """
        Evaluate all sign rules given current engine state.

        Called every engine step (dt = 0.1 s simulation time).

        Returns
        -------
        dict[sign_id -> SignInstance]
            All signs currently active (after onset delay elapsed).
        """
        state = self._get_engine_state()
        disease = getattr(self._creature, "disease", None)

        for sign_id, rule_def in self._defs.get("symptoms", {}).items():
            result = self._evaluate_sign(
                sign_id, rule_def, state, disease, current_time_s
            )

            eval_type = rule_def.get("evaluation_type", "instantaneous")
            onset_delay = rule_def.get("onset_delay_s", 0)

            if result["active"]:
                # Cancel any pending offset
                self._offset_delayed.pop(sign_id, None)

                # Sustained rule: check duration requirement
                if eval_type == "sustained":
                    duration_s = rule_def.get("duration_s", 0)
                    if sign_id not in self._sustained_since:
                        self._sustained_since[sign_id] = current_time_s
                    elapsed = current_time_s - self._sustained_since[sign_id]
                    if elapsed < duration_s:
                        # Not yet sustained long enough — don't activate
                        continue

                # Onset delay
                if sign_id not in self._onset_delayed:
                    self._onset_delayed[sign_id] = current_time_s
                elapsed_onset = current_time_s - self._onset_delayed[sign_id]
                if elapsed_onset < onset_delay:
                    continue

                severity = result.get("severity", "mild")
                if sign_id in self._active:
                    self._active[sign_id].severity = severity
                    self._active[sign_id].active = True
                else:
                    self._active[sign_id] = SignInstance(
                        sign_id=sign_id,
                        display_name=rule_def["display_name"],
                        severity=severity,
                        onset_time_s=self._onset_delayed[sign_id],
                        active=True,
                        clue_id=rule_def.get("clue_id", sign_id),
                    )
            else:
                # Cancel sustained tracking
                self._sustained_since.pop(sign_id, None)

                # Apply offset delay
                offset_delay = rule_def.get("offset_delay_s", 120)
                if sign_id not in self._offset_delayed:
                    self._offset_delayed[sign_id] = current_time_s
                elapsed_offset = current_time_s - self._offset_delayed[sign_id]
                if elapsed_offset >= offset_delay:
                    self._onset_delayed.pop(sign_id, None)
                    self._accumulators.pop(sign_id, None)
                    if sign_id in self._active:
                        self._active[sign_id].active = False

        return self._active

    def get_active_signs(self) -> list[SignInstance]:
        """Return currently active signs (for game layer)."""
        return [s for s in self._active.values() if s.active]

    def get_sign_tags(self) -> list[str]:
        """Return clue_ids of active signs (for report_engine tag injection)."""
        return [s.clue_id for s in self.get_active_signs() if s.clue_id]

    # ── Rule evaluation ────────────────────────────────────────

    def _evaluate_sign(
        self,
        sign_id: str,
        rule_def: dict,
        state: dict,
        disease: Any,
        current_time_s: float,
    ) -> dict:
        """Evaluate a single sign rule. Returns {"active": bool, "severity": str}."""
        rule_type = rule_def.get("rule_type", "threshold")
        eval_type = rule_def.get("evaluation_type", "instantaneous")

        if rule_type == "threshold":
            return self._eval_threshold(rule_def, state, disease)
        elif rule_type == "multi_parameter":
            return self._eval_multi(rule_def, state, disease)
        else:
            logger.warning("Unknown rule_type '%s' for sign '%s'", rule_type, sign_id)
            return {"active": False, "severity": ""}

    def _eval_threshold(self, rule_def: dict, state: dict, disease: Any) -> dict:
        """Single parameter threshold evaluation — delegates to _eval_boolean_expr."""
        rule_str = rule_def.get("rule", "")
        if not rule_str:
            return {"active": False, "severity": ""}
        active = self._eval_boolean_expr(rule_str, state, disease)
        severity = ""
        if active and "severity_mapping" in rule_def:
            param = rule_def.get("param", "")
            value = self._resolve_param(param, state, disease)
            if value is not None:
                severity = self._compute_severity(
                    rule_def["severity_mapping"], value, state, disease
                )
        return {"active": active, "severity": severity or "mild"}

    def _eval_multi(self, rule_def: dict, state: dict, disease: Any) -> dict:
        """Multi-parameter boolean rule evaluation."""
        rule_str = rule_def.get("rule", "")
        compound_str = rule_def.get("compound_rule", "")

        active = self._eval_boolean_expr(rule_str, state, disease)

        # Compound rule (e.g., Addisonian: Na:K ratio < 23 AND K > threshold)
        if not active and compound_str:
            active = self._eval_boolean_expr(compound_str, state, disease)

        severity = ""
        if active and "severity_spread" in rule_def:
            # Count how many individual conditions fired for severity
            severity = self._compute_spread_severity(rule_def, state, disease)

        return {"active": active, "severity": severity or "mild"}

    def _compute_severity(
        self, mapping: dict, value: float, state: dict, disease: Any
    ) -> str:
        """Compute severity level from a severity_mapping dict."""
        for level in ("severe", "moderate", "mild"):
            if level not in mapping:
                continue
            entry = mapping[level]
            if isinstance(entry, dict):
                lo = entry.get("min", -math.inf)
                hi = entry.get("max", math.inf)
                if lo <= value < hi:
                    return level
            elif isinstance(entry, (int, float)):
                if value >= entry:
                    return level
        return "mild"

    def _compute_spread_severity(self, rule_def: dict, state: dict, disease: Any) -> str:
        """Count how many OR-separated conditions are true for multi-factor severity."""
        rule_str = rule_def.get("rule", "")
        # Count individual comparisons that are True
        count = 0
        # Split by OR to count independent conditions
        or_parts = rule_str.split(" OR ")
        for part in or_parts:
            part = part.strip()
            if " AND " in part:
                # All AND conditions must be true to count as 1
                if self._eval_boolean_expr(part, state, disease):
                    count += 1
            else:
                if self._eval_boolean_expr(part, state, disease):
                    count += 1

        if count >= 4:
            return "severe"
        elif count >= 2:
            return "moderate"
        return "mild"

    # ── Parameter resolution ────────────────────────────────────

    def _resolve_param(self, param: str, state: dict, disease: Any) -> float | None:
        """
        Resolve a parameter reference to a numeric value.

        Resolution order:
          1. state key (from get_state())
          2. blood.* attribute on creature.blood
          3. heart.* attribute on creature.heart
          4. lung.* attribute on creature.lung
          5. kidney.* attribute on creature.kidney
          6. disease.* attribute on disease module
        """
        if not param or param == "None":
            return None

        # State-level parameters
        if param in state:
            raw = state[param]
            if raw is None:
                return None
            # Glu is stored in mmol/L in the engine but rules expect mg/dL
            if param == "Glu":
                return _mmol_to_mg_dL(float(raw))
            return float(raw)

        # blood.* path
        if param.startswith("blood."):
            attr = param.split(".", 1)[1]
            b = getattr(self._creature, "blood", None)
            if b is None:
                return None
            raw = getattr(b, attr, None)
            if raw is None:
                return None
            if attr == "glucose_mmol_L":
                return _mmol_to_mg_dL(float(raw))
            return float(raw)

        # heart.* path
        if param.startswith("heart."):
            attr = param.split(".", 1)[1]
            h = getattr(self._creature, "heart", None)
            if h is None:
                return None
            raw = getattr(h, attr, None)
            if raw is None:
                return None
            return float(raw)

        # lung.* path
        if param.startswith("lung."):
            attr = param.split(".", 1)[1]
            lg = getattr(self._creature, "lung", None)
            if lg is None:
                return None
            raw = getattr(lg, attr, None)
            if raw is None:
                return None
            return float(raw)

        # kidney.* path
        if param.startswith("kidney."):
            attr = param.split(".", 1)[1]
            k = getattr(self._creature, "kidney", None)
            if k is None:
                return None
            raw = getattr(k, attr, None)
            if raw is None:
                return None
            return float(raw)

        # disease.* path (disease module state variables)
        if param.startswith("disease."):
            attr = param.split(".", 1)[1]
            if disease is None:
                return None
            raw = getattr(disease, attr, None)
            if raw is None:
                # Try accessing internal _state_vars dict
                if hasattr(disease, "_state_vars"):
                    return disease._state_vars.get(attr)
                return None
            if hasattr(raw, "_state_vars"):
                # It's a sub-module; try to get the specific var
                return raw._state_vars.get(attr.split("_")[-1], 0.0) if hasattr(raw, "_state_vars") else float(raw)
            return float(raw)

        return None

    # ── Boolean expression engine ───────────────────────────────

    def _eval_boolean_expr(self, expr: str, state: dict, disease: Any) -> bool:
        """
        Evaluate a simple boolean expression string.

        Supports:
          - OR / AND chaining
          - Parentheses grouping
          - Comparisons: >=, <=, >, <, ==, !=
          - Threshold references (e.g., bun_uremia → resolved from species thresholds)

        Examples:
          "BUN > bun_uremia OR K > k_hyperkalemia"
          "HCT < hct_anemia OR (PaO2 < pao2_hypoxemia AND pH < ph_metabolic_acidosis)"
        """
        if not expr or not expr.strip():
            return False

        expr = expr.strip()

        # ── OR handling ───────────────────────────────────────────
        or_result = False
        any_or = False
        or_depth = 0
        part_start = 0
        i = 0
        while i < len(expr):
            # Lookahead: detect " OR " or "AND " at current position (before whitespace skip)
            if i + 4 <= len(expr) and expr[i:i+4] == " OR ":
                if or_depth == 0:
                    any_or = True
                    or_result = or_result or self._eval_boolean_expr(
                        expr[part_start:i], state, disease
                    )
                    i += 4  # skip " OR "
                    part_start = i
                    continue
            elif i + 5 <= len(expr) and expr[i:i+5] == " AND ":
                pass  # AND is handled below; don't consume here
            elif expr[i] == "(":
                or_depth += 1
            elif expr[i] == ")":
                or_depth -= 1
            i += 1

        if any_or:
            # Evaluate final segment and return
            if part_start < len(expr):
                or_result = or_result or self._eval_boolean_expr(
                    expr[part_start:], state, disease
                )
            return or_result

        # ── AND handling (only when no OR present) ────────────────
        and_result = True
        any_and = False
        and_depth = 0
        part_start = 0
        i = 0
        while i < len(expr):
            if i + 5 <= len(expr) and expr[i:i+5] == " AND ":
                if and_depth == 0:
                    any_and = True
                    and_result = and_result and self._eval_boolean_expr(
                        expr[part_start:i], state, disease
                    )
                    i += 5  # skip " AND "
                    part_start = i
                    continue
            elif expr[i] == "(":
                and_depth += 1
            elif expr[i] == ")":
                and_depth -= 1
            i += 1

        if any_and and part_start < len(expr):
            # Only evaluate final segment if we found at least one AND
            and_result = and_result and self._eval_boolean_expr(
                expr[part_start:], state, disease
            )
        elif not any_and:
            # Single term (no AND): evaluate as one comparison
            return self._eval_comparison_expr(expr, state, disease)

        return and_result

    def _eval_comparison_expr(self, expr: str, state: dict, disease: Any) -> bool:
        """Evaluate a single comparison expression like 'BUN > 80' or 'K < 6.5'."""
        # Split on comparison operators
        for op in (">=", "<=", "!=", "==", ">", "<"):
            idx = expr.find(op)
            if idx != -1:
                left = expr[:idx].strip()
                right = expr[idx + len(op):].strip()
                return self._eval_comparison(left, op, right, state, disease)
        # No operator found — treat as boolean literal
        if expr.strip() == "True":
            return True
        if expr.strip() == "False":
            return False
        return False

    def _eval_comparison(self, raw_left: str, op: str, raw_right: str, state: dict, disease: Any) -> bool:
        """Evaluate a single comparison: left op right."""
        left_val = self._resolve_comparison_operand(raw_left, state, disease)
        right_val = self._resolve_comparison_operand(raw_right, state, disease)

        if left_val is None or right_val is None:
            return False

        ops = {
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
        }
        if op not in ops:
            return False
        return ops[op](left_val, right_val)

    def _resolve_comparison_operand(self, operand: str, state: dict, disease: Any) -> float | None:
        """Resolve one side of a comparison to a float."""
        operand = operand.strip()

        # Boolean literals
        if operand == "True":
            return 1.0
        if operand == "False":
            return 0.0

        # Check if it's a threshold reference (e.g., "bun_uremia")
        if operand in self._thresholds:
            return float(self._thresholds[operand])

        # Check if it's a numeric literal
        try:
            return float(operand)
        except ValueError:
            pass

        # Otherwise resolve as a parameter
        return self._resolve_param(operand, state, disease)

    # ── Engine state snapshot ──────────────────────────────────

    def _get_engine_state(self) -> dict:
        """Get current engine state via the shared clinical-state adapter."""
        return extract_clinical_state(self._creature)
