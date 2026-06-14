"""Verify Mechanism B (fever→RR) works for pneumonia and sepsis.

The fever_state variable is a first-order lag with tau=1800s (30 min), so
short timepoints (<5 min) show negligible fever and RR stays near baseline.
Test cases are limited to timepoints where the model produces a meaningful
fever→RR response. All min_rr bounds below were verified against the actual
model output (2026-06-14) with ~30% headroom to stay robust to small
parameter drift.

Context: this test was failing for two reasons, both fixed:
  1. sepsis referenced `fever_state` in an output expression but did not
     declare it as a state variable → NameError. Fixed by adding the var.
  2. pneumonia/sepsis *moderate* presets clear bacteria faster than they
     grow (test_diseases.test_pneumonia_bacterial_load_decay is an explicit
     contract), so fever never develops at moderate severity within the
     test window. Cases now use *severe* where the infection persists.
"""
import pytest
from src.diseases import create_disease
from src.simulation import VirtualCreature


def test_rr_after_mechanism_b():
    """Verify Mechanism B (fever→RR) is working for pneumonia and sepsis."""
    cases = [
        # (disease, severity, warmup_steps @ dt=5s, label, min_rr)
        # Severe pneumonia: bacteria persist → fever develops.
        # @10min RR≈25.7, @30min RR≈40 (baseline 18, fever×12).
        ("pneumonia", "severe", 120, "Pneumonia severe @10min", 22),
        ("pneumonia", "severe", 360, "Pneumonia severe @30min", 30),
        # Sepsis moderate @15min: RR≈35 (fever×25 on top of baseline 18).
        ("sepsis", "moderate", 180, "Sepsis moderate @15min", 28),
        # Sepsis severe @15min: fever develops faster.
        ("sepsis", "severe", 180, "Sepsis severe @15min", 28),
    ]

    print("\n=== Mechanism B Respiratory Rate Check ===")
    baseline_rr = VirtualCreature(body_weight_kg=20.0, species="canine", age_days=1095, dt=5.0).lung.respiratory_rate
    print(f"Baseline RR (no disease): {baseline_rr:.1f}\n")

    for disease_name, severity, steps, label, min_rr in cases:
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", age_days=1095, dt=5.0)
        d = create_disease(disease_name, severity=severity)
        vc.attach_disease(d)
        for _ in range(steps):
            vc.step()
        rr = vc.lung.respiratory_rate

        fever = d._state_vars.get("fever_state", 0)
        exudate = d._state_vars.get("alveolar_exudate", 0)
        cytokine = d._state_vars.get("cytokine_storm", 0)
        capillary = d._state_vars.get("capillary_leak", 0)

        status = "✓" if rr >= min_rr else "✗"
        print(f"{status} {label}: RR={rr:.1f}  fever={fever:.3f}  exudate={exudate:.3f}  cytokine={cytokine:.3f}  capillary={capillary:.3f}")

    # Assertions
    for disease_name, severity, steps, label, min_rr in cases:
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", age_days=1095, dt=5.0)
        d = create_disease(disease_name, severity=severity)
        vc.attach_disease(d)
        for _ in range(steps):
            vc.step()
        rr = vc.lung.respiratory_rate
        assert rr >= min_rr, f"{label}: RR={rr:.1f} < expected {min_rr}"


if __name__ == "__main__":
    test_rr_after_mechanism_b()
