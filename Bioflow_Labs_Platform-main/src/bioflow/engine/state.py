# src/bioflow/engine/state.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict


@dataclass
class GlobalState:
    t_s: float

    # Volumes (ml) — Phase 4.1 state
    V_art_ml: float
    V_ven_ml: float

    # Pressures (mmHg) — derived each step from volumes
    P_art_mmHg: float
    P_ven_mmHg: float

    # Derived outputs (recorded for samples)
    bed_Q_ml_per_s: Dict[str, float]
    bed_perfusion_index: Dict[str, float]

    def to_json(self) -> dict:
        return asdict(self)
