"""
src.organs — multi-organ coupling package.

Exports:
    OrganContext  — per-organ signal bus (publish/subscribe)
    PhysiologicalSignal — immutable signal value container
    CouplingEngine     — resolves inter-organ couplings from coupling_rules.json
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

__all__ = [
    "OrganContext",
    "PhysiologicalSignal",
    "CouplingEngine",
]
