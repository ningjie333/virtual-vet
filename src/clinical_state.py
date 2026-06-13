from __future__ import annotations

from typing import Any

from src.clinical_snapshot import ClinicalSnapshot
from src.parameters import NORMAL_HB_CANINE, NORMAL_HB_FELINE, NORMAL_HB_EQUINE


def _hb_from_hct(hct_pct: float, species: str) -> float:
    """从 HCT% 推算 Hb (g/dL)。HCT/Hb ≈ 3（犬）、≈ 2.8（猫）、≈ 3.1（马）。"""
    if hct_pct <= 0:
        return NORMAL_HB_CANINE
    if species == "cat":
        return hct_pct / 2.8
    elif species == "horse":
        return hct_pct / 3.1
    else:
        # 犬：HCT normal ≈ 45%, Hb normal ≈ 14.5 → ratio ≈ 3.1
        return hct_pct / 3.1


def extract_clinical_state(creature: Any) -> dict:
    """
    Extract the current clinically relevant state from the physiology kernel.

    This is the canonical adapter for interpretation-layer consumers that still
    rely on the historical dict-style state representation.
    """
    hist = creature.history

    def _last(key: str, fallback):
        vals = hist.get(key, [])
        return vals[-1] if vals else fallback

    h = creature.heart
    b = creature.blood

    hr = _last("HR_bpm", h.heart_rate)
    pa_o2 = _last("art_PO2", b.arterial_PO2_mmHg)
    pa_co2 = _last("art_PCO2", b.arterial_PCO2_mmHg)
    sat = _last("saturation", b.arterial_saturation)
    ph = _last("pH", b.arterial_pH)
    gfr = _last("GFR", creature.kidney.GFR)
    bun = _last("BUN", b.bun_mg_dL)
    rr = _last("RR", creature.lung.respiratory_rate)
    co = _last("CO_ml_min", h.cardiac_output)
    map_val = _last("MAP_mmHg", h.mean_arterial_pressure)
    cvp = _last("CVP_mmHg", h.central_venous_pressure)
    bv = _last("blood_volume_ml", h.circulating_volume_ml)
    ctr = _last("contractility_factor", h.contractility_factor)
    urine = _last("urine_ml_min", creature.kidney.urine_output)

    state = {
        "HR": hr,
        "MAP": map_val,
        "CVP": cvp,
        "CO": co,
        "RR": rr,
        "SpO2": sat * 100,
        "PaO2": pa_o2,
        "PaCO2": pa_co2,
        "pH": ph,
        "GFR": gfr,
        "BUN": bun,
        "Na": b.sodium_mEq_L,
        "K": b.potassium_mEq_L,
        "Glu": b.glucose_mmol_L,
        "Lactate": b.lactate_mmol_L,
        "HCT": (b.red_cell_volume_ml / b.total_volume_ml) * 100,
        "HCO3": creature.fluid.vascular_hco3_meq_l
        if hasattr(creature, "fluid")
        else 24.0,
        "Temp": b.core_temperature_C,
        "BV": bv,
        "contractility": ctr,
        "Urine": urine,
        "PT": _last("coag_PT", b.PT_sec),
        "aPTT": _last("coag_aPTT", b.aPTT_sec),
        "Fibrinogen": _last("coag_fibrinogen", b.fibrinogen_mg_dL),
        "pain_level": creature.neuro.pain_level,
    }

    if hasattr(creature, "coagulation") and creature.coagulation is not None:
        state["coagulation_state"] = creature.coagulation.coagulation_state

    if hasattr(creature.heart, "hh") and creature.heart.hh is not None:
        hh = creature.heart.hh
        ecg_interp = hh.get_ecg_interpretation(b.potassium_mEq_L)
        state["hh_heart_rate"] = round(hh.heart_rate, 1)
        state["hh_k_toxicity"] = round(hh.k_toxicity_factor, 3)
        state["hh_h_inf"] = round(hh._h_inf, 3)
        state["hh_e_k"] = round(hh._nernst_k(b.potassium_mEq_L), 1)
        state["T波"] = ecg_interp.get("t_wave_amplitude", "normal")
        state["QRS宽度"] = ecg_interp.get("qrs_width", "normal")
        state["P波"] = ecg_interp.get("p_wave", "present")
        state["K_toxicity_stage"] = ecg_interp.get("k_toxicity_stage", "none")

        from src.noble_purkinje import NoblePurkinjeFiber

        if isinstance(hh, NoblePurkinjeFiber):
            av_interp = hh.get_av_interpretation(b.potassium_mEq_L)
            state["PR间期"] = av_interp.get("pr_interval_ms", 80.0)
            state["AV传导"] = av_interp.get("av_block_description", "normal_conduction")
            state["传导速度"] = av_interp.get("conduction_velocity", 4.0)
            state["逸搏心率"] = av_interp.get("purkinje_intrinsic_rate_bpm", 30.0)

    return state


def build_clinical_snapshot(creature: Any) -> ClinicalSnapshot:
    """Build the stable snapshot model used by the clinical interpreter."""
    state = extract_clinical_state(creature)
    disease = getattr(creature, "disease", None)
    disease_state = None
    if disease is not None and hasattr(disease, "_state_vars"):
        disease_state = dict(disease._state_vars)

    return ClinicalSnapshot(
        time_s=creature.current_time_s,
        species=str(getattr(creature, "species", "dog")),
        weight_kg=creature.w,
        hr_bpm=float(state["HR"]),
        map_mmhg=float(state["MAP"]),
        cvp_mmhg=float(state["CVP"]),
        rr_bpm=float(state["RR"]),
        spo2_pct=float(state["SpO2"]),
        pao2_mmhg=float(state["PaO2"]),
        paco2_mmhg=float(state["PaCO2"]),
        ph=float(state["pH"]),
        gfr_ml_min=float(state["GFR"]),
        urine_ml_min=float(state["Urine"]),
        bun_mg_dl=float(state["BUN"]),
        lactate_mmol_l=float(state["Lactate"]),
        temperature_c=float(state["Temp"]),
        co_ml_min=float(state["CO"]),
        blood_volume_ml=float(state["BV"]),
        contractility_factor=float(state["contractility"]),
        diffusion_coefficient=float(creature.lung.diffusion_coefficient),
        sodium_meq_l=float(state["Na"]),
        potassium_meq_l=float(state["K"]),
        glucose_mmol_l=float(state["Glu"]),
        hct_pct=float(state["HCT"]),
        hco3_meq_l=float(state["HCO3"]),
        hb_g_dL=_hb_from_hct(float(state["HCT"]), str(getattr(creature, "species", "dog"))),
        disease_name=type(disease).__name__ if disease is not None else None,
        disease_active=bool(disease is not None and getattr(disease, "active", False)),
        disease_state=disease_state,
    )
