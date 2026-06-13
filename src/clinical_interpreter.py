from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Protocol, Sequence

from src.clinical_state import build_clinical_snapshot, extract_clinical_state
from src.clinical_snapshot import ClinicalSnapshot
from src.parameters import (
    HUFNER_CONSTANT,
    LUNG_DIFFUSION_COEFFICIENT,
    base_cardiac_output_ml_min,
    base_DO2_normal_ml_min,
)
from src.report_engine import generate_report


class ClinicalInterpreterProtocol(Protocol):
    def snapshot(self, engine: Any) -> ClinicalSnapshot: ...

    def active_signs(self, engine: Any) -> Sequence[Any]: ...

    def sign_tags(self, engine: Any) -> list[str]: ...

    def report(self, test_type: str, engine: Any) -> dict: ...

    def phase(self, snapshot: ClinicalSnapshot) -> str: ...

    def summary(self, snapshot: ClinicalSnapshot, elapsed_min: int) -> dict: ...


class DefaultClinicalInterpreter:
    """Compatibility interpreter that wraps existing reporting logic."""

    def __init__(
        self,
        signs_engine_resolver: Callable[[Any], Any | None] | None = None,
    ) -> None:
        self._signs_engine_resolver = signs_engine_resolver or _default_signs_engine_resolver

    def snapshot(self, engine: Any) -> ClinicalSnapshot:
        return build_clinical_snapshot(engine)

    def active_signs(self, engine: Any) -> Sequence[Any]:
        signs_engine = self._signs_engine_resolver(engine)
        if signs_engine is None:
            return []
        return signs_engine.get_active_signs()

    def sign_tags(self, engine: Any) -> list[str]:
        signs_engine = self._signs_engine_resolver(engine)
        if signs_engine is None:
            return []
        return list(signs_engine.get_sign_tags())

    def report(self, test_type: str, engine: Any) -> dict:
        state = extract_clinical_state(engine)
        sign_tags = self.sign_tags(engine)
        return generate_report(test_type, engine, state=state, sign_tags=sign_tags)

    def phase(self, snapshot: ClinicalSnapshot) -> str:
        threshold_score = max(
            self._score(snapshot.map_mmhg, "MAP"),
            self._score(snapshot.spo2_pct, "SpO2"),
            self._score(snapshot.hr_bpm, "HR"),
            self._score(snapshot.ph, "pH"),
        )

        aa_gradient = 10.0 + (
            1.0 - snapshot.diffusion_coefficient / LUNG_DIFFUSION_COEFFICIENT
        ) * 30.0
        if aa_gradient >= 45:
            aa_score = 3
        elif aa_gradient >= 35:
            aa_score = 2
        elif aa_gradient >= 25:
            aa_score = 1
        else:
            aa_score = 0

        disease_score = self._disease_score(snapshot.disease_state, snapshot.disease_active)
        threshold_score = max(threshold_score, aa_score, disease_score)

        do2 = self._compute_do2(snapshot)
        if do2 <= _DO2_MORIB:
            do2_score = 3
        elif do2 <= _DO2_CRIT:
            do2_score = 2
        elif do2 <= _DO2_WARN:
            do2_score = 1
        else:
            do2_score = 0

        if snapshot.lactate_mmol_l >= _LACTATE_CRIT:
            lactate_score = 2
        elif snapshot.lactate_mmol_l >= _LACTATE_WARN:
            lactate_score = 1
        else:
            lactate_score = 0

        urine_per_kg = (
            snapshot.urine_ml_min / snapshot.weight_kg if snapshot.weight_kg > 0 else 0.0
        )
        if urine_per_kg < _URINE_ANURIA:
            urine_score = 3
        elif urine_per_kg < _URINE_OLIGURIA:
            urine_score = 2
        else:
            urine_score = 0

        if threshold_score >= 3 or do2_score >= 3 or urine_score >= 3:
            return "moribund"

        if snapshot.hr_bpm < 60 and urine_per_kg < _URINE_ANURIA:
            return "moribund"

        crit_count = sum(
            [
                threshold_score >= 2,
                do2_score >= 2,
                lactate_score >= 2,
                urine_score >= 2,
            ]
        )
        if crit_count >= 2 or do2_score >= 2:
            return "critical"

        if (
            threshold_score >= 1
            or do2_score >= 1
            or lactate_score >= 1
            or urine_score >= 1
        ):
            return "worsening"

        return "stable"

    def summary(self, snapshot: ClinicalSnapshot, elapsed_min: int) -> dict:
        return {
            "HR_bpm": round(snapshot.hr_bpm, 1),
            "MAP_mmHg": round(snapshot.map_mmhg, 1),
            "SpO2": round(snapshot.spo2_pct, 1),
            "art_PO2": round(snapshot.pao2_mmhg, 1),
            "art_PCO2": round(snapshot.paco2_mmhg, 1),
            "pH": round(snapshot.ph, 3),
            "GFR": round(snapshot.gfr_ml_min, 1),
            "RR": round(snapshot.rr_bpm, 1),
            "game_time": _format_game_time(elapsed_min),
            "is_night": _is_night_time(elapsed_min),
        }

    def _compute_do2(self, snapshot: ClinicalSnapshot) -> float:
        """DO2 ratio = DO2 / DO2_normal；DO2 = CO(L/min) × Hb(g/dL) × SaO2 × 1.34"""
        do2_normal = base_DO2_normal_ml_min(snapshot.weight_kg, snapshot.species)
        co_L_min = snapshot.co_ml_min / 1000.0
        sao2 = snapshot.spo2_pct / 100.0 if snapshot.spo2_pct > 1.0 else snapshot.spo2_pct
        if do2_normal <= 0:
            return 0.0
        do2 = co_L_min * snapshot.hb_g_dL * sao2 * HUFNER_CONSTANT
        return max(0.0, min(1.0, do2 / do2_normal))

    def _score(self, value: float, param: str) -> int:
        lo_mor, lo_crit, lo_warn, hi_warn, hi_crit, hi_mor = _THRESHOLDS[param]
        if value <= lo_mor or value >= hi_mor:
            return 3
        if value <= lo_crit or value >= hi_crit:
            return 2
        if value <= lo_warn or value >= hi_warn:
            return 1
        return 0

    def _disease_score(
        self, disease_state: dict[str, Any] | None, disease_active: bool
    ) -> int:
        if not disease_active or not disease_state:
            return 0

        damage_vars = {
            "alveolar_exudate": (0.5, 0.75, 0.9),
            "tissue_hypoxia": (0.4, 0.6, 0.85),
            "renal_injury": (0.3, 0.6, 0.85),
            "myocardial_depression": (0.3, 0.6, 0.85),
            "nephron_damage": (0.3, 0.6, 0.85),
            "gfr_decline": (0.3, 0.6, 0.85),
        }
        score = 0
        for var_name, (warn, crit, moribund) in damage_vars.items():
            value = float(disease_state.get(var_name, 0.0))
            if value >= moribund:
                score = max(score, 3)
            elif value >= crit:
                score = max(score, 2)
            elif value >= warn:
                score = max(score, 1)
        return score

_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


def _load_interpretation_policy() -> dict[str, Any]:
    with open(_DATA_DIR / "game_config.json", "r", encoding="utf-8") as f:
        return json.load(f)


_POLICY = _load_interpretation_policy()
_TIME = _POLICY["time"]
_PT = _POLICY["phase_thresholds"]

_THRESHOLDS = {
    "MAP": (
        _PT["MAP"]["low_moribund"],
        _PT["MAP"]["low_critical"],
        _PT["MAP"]["low_worsening"],
        _PT["MAP"]["high_worsening"],
        _PT["MAP"]["high_critical"],
        _PT["MAP"]["high_moribund"],
    ),
    "SpO2": (
        _PT["SpO2"]["low_moribund"],
        _PT["SpO2"]["low_critical"],
        _PT["SpO2"]["low_worsening"],
        _PT["SpO2"]["high_worsening"],
        _PT["SpO2"]["high_critical"],
        _PT["SpO2"]["high_moribund"],
    ),
    "HR": (
        _PT["HR"]["low_moribund"],
        _PT["HR"]["low_critical"],
        _PT["HR"]["low_worsening"],
        _PT["HR"]["high_worsening"],
        _PT["HR"]["high_critical"],
        _PT["HR"]["high_moribund"],
    ),
    "pH": (
        _PT["pH"]["low_moribund"],
        _PT["pH"]["low_critical"],
        _PT["pH"]["low_worsening"],
        _PT["pH"]["high_worsening"],
        _PT["pH"]["high_critical"],
        _PT["pH"]["high_moribund"],
    ),
}

_DO2_WARN = _PT["DO2"]["warn"]
_DO2_CRIT = _PT["DO2"]["critical"]
_DO2_MORIB = _PT["DO2"]["moribund"]

_LACTATE_WARN = _PT["lactate"]["warn"]
_LACTATE_CRIT = _PT["lactate"]["critical"]

_URINE_OLIGURIA = _PT["urine"]["oliguria"]
_URINE_ANURIA = _PT["urine"]["anuria"]

_GAME_START_HOUR = _TIME["start_hour"]
_NIGHT_START_HOUR = _TIME["night_start_hour"]
_NIGHT_END_HOUR = _TIME["night_end_hour"]
_MINUTES_PER_HOUR = 60


def _game_time_to_hour(game_time_min: float) -> float:
    start_minutes = _GAME_START_HOUR * _MINUTES_PER_HOUR
    current_minutes = start_minutes + game_time_min
    return (current_minutes / _MINUTES_PER_HOUR) % 24.0


def _is_night_time(game_time_min: float) -> bool:
    hour = _game_time_to_hour(game_time_min)
    return hour >= _NIGHT_START_HOUR or hour < _NIGHT_END_HOUR


def _format_game_time(game_time_min: float) -> str:
    total_minutes = int(
        (_GAME_START_HOUR * _MINUTES_PER_HOUR + game_time_min)
        % (24 * _MINUTES_PER_HOUR)
    )
    hours = total_minutes // _MINUTES_PER_HOUR
    minutes = total_minutes % _MINUTES_PER_HOUR
    return f"{hours:02d}:{minutes:02d}"


def _default_signs_engine_resolver(engine: Any) -> Any | None:
    return getattr(engine, "clinical_signs_engine", None)
