"""
Parameter Literature References — lookup utility.

Provides access to literature provenance for all tunable engine parameters
and coupling coefficients. Reference format mirrors ode_diseases.json
meta.references (PMIDs + textbooks).

Usage:
    from src.parameter_refs import get_param_ref, get_coupling_ref, ALL_REFS

    ref = get_param_ref("heart.heart_rate")
    if ref:
        for r in ref["references"]:
            print(r["id"], r["text"])
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Singleton cache
# ---------------------------------------------------------------------------

_REFS: dict | None = None


def _load() -> dict:
    global _REFS
    if _REFS is None:
        path = Path(__file__).parent.parent / "data" / "parameter_references.json"
        try:
            with open(path, encoding="utf-8") as f:
                _REFS = json.load(f)
            logger.debug("Loaded %d parameter reference entries", len(_REFS))
        except FileNotFoundError:
            logger.warning("parameter_references.json not found at %s", path)
            _REFS = {"_schema": "parameter_references v1"}
    return _REFS


def get_param_ref(path: str) -> dict | None:
    """
    Get literature reference for an engine parameter path.

    Args:
        path: Parameter path matching _PARAM_PATHS key (e.g., "heart.heart_rate")

    Returns:
        Reference dict with 'references' and optional 'notes' keys, or None if not found.
    """
    refs = _load()
    entry = refs.get(path)
    if entry is None:
        logger.debug("No reference found for parameter: %s", path)
    return entry


def get_coupling_ref(loop: str, rule_name: str) -> dict | None:
    """
    Get literature reference for a coupling rule.

    Args:
        loop: Loop category (e.g., "kidney_cv", "pulmonary_cv")
        rule_name: Exact rule name string from coupling_rules.json

    Returns:
        Reference dict or None.
    """
    from src.organs.coupling import CouplingEngine

    engine = CouplingEngine()
    for rule in engine.rules:
        if rule.loop == loop and rule.name == rule_name:
            if rule.references:
                return {"references": rule.references, "notes": rule.notes}
            return None
    return None


def all_param_refs() -> dict:
    """Return the full parameter_references.json contents."""
    return _load()


def report_unverified(param_paths: list[str]) -> list[str]:
    """
    Return list of parameter paths that lack literature references.

    Args:
        param_paths: List of _PARAM_PATHS keys to check

    Returns:
        List of paths with no entry in parameter_references.json
    """
    refs = _load()
    return [p for p in param_paths if p not in refs]