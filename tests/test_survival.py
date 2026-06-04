"""
Test: run disease cases without intervention to see if creature 'dies'.
Run with: python -m pytest tests/test_survival.py -v -s
"""
import pytest
from src.simulation import VirtualCreature
from game.action_system import GameState
from src.diseases import create_disease


@pytest.fixture(params=[
    {"title": "呕吐与嗜睡", "disease": "pneumonia", "weight_kg": 20.0},
    {"title": "无尿与呕吐", "disease": "acute_renal_failure", "weight_kg": 30.0},
    {"title": "运动不耐受与咳嗽", "disease": "dilated_cardiomyopathy", "weight_kg": 35.0},
])
def disease_case(request):
    return request.param


@pytest.mark.slower
def test_no_intervention_survival(disease_case):
    """Run 60 min simulation without any intervention. Does the creature die?"""
    title = disease_case["title"]
    disease_name = disease_case["disease"]
    weight = disease_case["weight_kg"]

    vc = VirtualCreature(weight)
    state = GameState(engine=vc, disease_name=disease_name)
    disease = create_disease(disease_name)
    vc.attach_disease(disease)

    init_map = vc.heart.mean_arterial_pressure
    init_hh = vc.organ_health.heart_health
    init_lh = vc.organ_health.lung_health
    init_kh = vc.organ_health.kidney_health

    print(f"\n{'='*60}")
    print(f"{title} ({disease_name}) — 无干预 60 分钟")
    print(f"  0s  MAP={init_map:6.1f}  心={init_hh:.3f}  肺={init_lh:.3f}  肾={init_kh:.3f}  phase={state.phase}")

    checkpoints = {60: 60, 120: 120, 300: 300, 600: 600}
    for step in range(600):
        state.engine.step()
        t = (step + 1) * 0.1
        if step + 1 in checkpoints:
            hh = vc.organ_health.heart_health
            lh = vc.organ_health.lung_health
            kh = vc.organ_health.kidney_health
            mp = vc.heart.mean_arterial_pressure
            print(f"  {t:5.0f}s  MAP={mp:6.1f}  心={hh:.3f}  肺={lh:.3f}  肾={kh:.3f}  phase={state.phase}")

    final_map = vc.heart.mean_arterial_pressure
    final_hh = vc.organ_health.heart_health
    final_lh = vc.organ_health.lung_health
    final_kh = vc.organ_health.kidney_health

    print(f"  60s  MAP={final_map:6.1f}  心={final_hh:.3f}  肺={final_lh:.3f}  肾={final_kh:.3f}  phase={state.phase}")
    print(f"  变化  MAP={final_map-init_map:+6.1f}  心={final_hh-init_hh:+.3f}  肺={final_lh-init_lh:+.3f}  肾={final_kh-init_kh:+.3f}")

    assert state.phase in ("playing", "won", "lost"), f"Unexpected phase: {state.phase}"
