from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClinicalSnapshot:
    """Stable clinical read model derived from the physiology kernel."""

    time_s: float
    species: str
    weight_kg: float

    hr_bpm: float
    map_mmhg: float
    cvp_mmhg: float
    rr_bpm: float
    spo2_pct: float
    pao2_mmhg: float
    paco2_mmhg: float
    ph: float
    gfr_ml_min: float
    urine_ml_min: float
    bun_mg_dl: float
    lactate_mmol_l: float
    temperature_c: float

    co_ml_min: float
    blood_volume_ml: float
    contractility_factor: float
    diffusion_coefficient: float

    sodium_meq_l: float
    potassium_meq_l: float
    glucose_mmol_l: float
    hct_pct: float
    hco3_meq_l: float
    hb_g_dL: float

    disease_name: str | None
    disease_active: bool
    disease_state: dict[str, Any] | None

