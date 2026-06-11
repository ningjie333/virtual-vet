import math


def assert_engine_state_finite(vc, step_idx: int) -> None:
    """Assert key engine state remains finite without relying on history buffers."""
    values = {
        "time_s": vc.current_time_s,
        "heart_rate": vc.heart.heart_rate,
        "cardiac_output": vc.heart.cardiac_output,
        "map": vc.heart.mean_arterial_pressure,
        "cvp": vc.heart.central_venous_pressure,
        "contractility": vc.heart.contractility_factor,
        "svr": vc.heart.SVR,
        "resp_rate": vc.lung.respiratory_rate,
        "po2": vc.blood.arterial_PO2_mmHg,
        "pco2": vc.blood.arterial_PCO2_mmHg,
        "saturation": vc.blood.arterial_saturation,
        "ph": vc.blood.arterial_pH,
        "gfr": vc.kidney.GFR,
        "urine_output": vc.kidney.urine_output,
        "bun": vc.blood.bun_mg_dL,
        "creatinine": vc.blood.creatinine_mg_dL,
        "glucose": vc.blood.glucose_mmol_L,
        "blood_volume": vc.heart.circulating_volume_ml,
        "vascular_fluid": vc.fluid.vascular_volume_ml,
        "isf_fluid": vc.fluid.isf_volume_ml,
        "icf_fluid": vc.fluid.icf_volume_ml,
        "temperature": vc.blood.core_temperature_C,
        "gut_motility": vc.gut.gut_motility,
        "liver_activity": vc.liver.metabolic_activity,
    }
    for name, value in values.items():
        assert math.isfinite(float(value)), f"{name} became non-finite at step {step_idx}: {value!r}"
