"""
Short-horizon no-intervention deterioration checks.

This file intentionally does not claim true survival or death-window validation.
It verifies that, over 60 seconds of physical time, untreated disease cases
diverge from matched healthy controls in clinically relevant directions.
"""
import os
import sys

import pytest

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, os.path.join(_PROJECT_ROOT, "src"))

from src.diseases import create_disease
from src.simulation import VirtualCreature

pytestmark = pytest.mark.slower


@pytest.fixture(params=[
    {"title": "呕吐与嗜睡", "disease": "pneumonia", "weight_kg": 20.0},
    {"title": "无尿与呕吐", "disease": "acute_renal_failure", "weight_kg": 30.0},
    {"title": "运动不耐受与咳嗽", "disease": "dilated_cardiomyopathy", "weight_kg": 35.0},
])
def disease_case(request):
    return request.param


@pytest.mark.slower
def test_no_intervention_short_horizon_deterioration(disease_case):
    """Over 60 s, untreated disease should diverge from a matched healthy control."""
    disease_name = disease_case["disease"]
    weight = disease_case["weight_kg"]

    healthy = VirtualCreature(weight, dt=0.1)
    vc = VirtualCreature(weight, dt=0.1)
    disease = create_disease(disease_name)
    vc.attach_disease(disease)

    for _ in range(600):
        healthy.step()
        vc.step()

    assert healthy.current_time_s == pytest.approx(60.0, abs=1e-6)
    assert vc.current_time_s == pytest.approx(60.0, abs=1e-6)

    if disease_name == "pneumonia":
        assert vc.blood.arterial_PO2_mmHg <= healthy.blood.arterial_PO2_mmHg - 10.0, (
            f"pneumonia should materially worsen PaO2 over 60 s without intervention: "
            f"healthy={healthy.blood.arterial_PO2_mmHg:.2f}, disease={vc.blood.arterial_PO2_mmHg:.2f}"
        )
        assert vc.blood.arterial_saturation <= healthy.blood.arterial_saturation - 0.01, (
            f"pneumonia should worsen oxygenation saturation over 60 s without intervention: "
            f"healthy={healthy.blood.arterial_saturation:.4f}, disease={vc.blood.arterial_saturation:.4f}"
        )
    elif disease_name == "acute_renal_failure":
        assert vc.kidney.GFR <= healthy.kidney.GFR * 0.5, (
            f"ARF should materially reduce GFR over 60 s without intervention: "
            f"healthy={healthy.kidney.GFR:.2f}, disease={vc.kidney.GFR:.2f}"
        )
        assert vc.blood.bun_mg_dL >= healthy.blood.bun_mg_dL * 1.3, (
            f"ARF should materially raise BUN over 60 s without intervention: "
            f"healthy={healthy.blood.bun_mg_dL:.2f}, disease={vc.blood.bun_mg_dL:.2f}"
        )
        assert vc.blood.potassium_mEq_L >= healthy.blood.potassium_mEq_L + 0.05, (
            f"ARF should worsen hyperkalemia risk over 60 s without intervention: "
            f"healthy={healthy.blood.potassium_mEq_L:.3f}, disease={vc.blood.potassium_mEq_L:.3f}"
        )
        assert vc.blood.arterial_pH <= healthy.blood.arterial_pH - 0.01, (
            f"ARF should worsen acidemia over 60 s without intervention: "
            f"healthy={healthy.blood.arterial_pH:.4f}, disease={vc.blood.arterial_pH:.4f}"
        )
    elif disease_name == "dilated_cardiomyopathy":
        assert vc.heart.contractility_factor <= healthy.heart.contractility_factor - 0.08, (
            f"DCM should reduce contractility over 60 s without intervention: "
            f"healthy={healthy.heart.contractility_factor:.4f}, disease={vc.heart.contractility_factor:.4f}"
        )
