"""
src.organs — multi-organ coupling package.

Exports:
    OrganContext  — per-organ signal bus (publish/subscribe)
    PhysiologicalSignal — immutable signal value container
    CouplingEngine     — resolves inter-organ couplings from coupling_rules.json
    ModuleContract    — declared I/O surface (Phase 5)
    has_contract / collect_contract — introspection helpers
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .contracts import ModuleContract, has_contract, collect_contract

__all__ = [
    "OrganContext",
    "PhysiologicalSignal",
    "CouplingEngine",
    "ModuleContract",
    "has_contract",
    "collect_contract",
]