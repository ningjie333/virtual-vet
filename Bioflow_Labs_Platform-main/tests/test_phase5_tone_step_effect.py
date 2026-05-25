import json
from pathlib import Path


def _load_baseline_template() -> dict:
    p = Path(__file__).parent / "fixtures" / "template_valid_baseline.json"
    return json.loads(p.read_text(encoding="utf-8"))


def _derive_baseline_flows(*, rp: dict, beds):
    from bioflow.engine.physiology.algebraic import compute_bed_flows

    baseline = rp["baseline"]
    baseline_results = compute_bed_flows(
        P_art_mmHg=float(baseline["P_art_mmHg"]),
        P_ven_mmHg=float(baseline["P_ven_mmHg"]),
        beds=beds,
        baseline_flows_ml_per_s={b.bed_id: 1.0 for b in beds},
    )
    return {r.bed_id: r.Q_ml_per_s for r in baseline_results}


def test_phase5_tone_higher_resistance_changes_next_state():
    """
    If we increase vascular_tone_factor (>1), beds have higher effective R,
    which should change Q_out and therefore volumes/pressures after one step.
    """
    from bioflow.engine.state import GlobalState
    from bioflow.engine.physiology.algebraic import BedParameters
    from bioflow.engine.physiology.compliance import CompartmentParameters, step_phase41_compliance

    template = _load_baseline_template()
    rp = template["resolved_parameters"]

    beds = [BedParameters(**b) for b in rp["beds"]]
    baseline_flows = _derive_baseline_flows(rp=rp, beds=beds)

    pump_Q = float(rp["pump"]["Q_ml_per_s"])
    art = CompartmentParameters(**rp["compartments"]["arterial"])
    ven = CompartmentParameters(**rp["compartments"]["venous"])

    init = template["initial_state"]
    prev = GlobalState(
        t_s=0.0,
        V_art_ml=float(init["V_art_ml"]),
        V_ven_ml=float(init["V_ven_ml"]),
        P_art_mmHg=0.0,
        P_ven_mmHg=0.0,
        bed_Q_ml_per_s={},
        bed_perfusion_index={},
    )

    dt_s = 0.1

    next_neutral, _ = step_phase41_compliance(
        prev_state=prev,
        dt_s=dt_s,
        beds=beds,
        baseline_flows_ml_per_s=baseline_flows,
        pump_Q_ml_per_s=pump_Q,
        art=art,
        ven=ven,
        resolved_parameters={"vascular_tone_factor": 1.0},
    )

    next_tone, _ = step_phase41_compliance(
        prev_state=prev,
        dt_s=dt_s,
        beds=beds,
        baseline_flows_ml_per_s=baseline_flows,
        pump_Q_ml_per_s=pump_Q,
        art=art,
        ven=ven,
        resolved_parameters={"vascular_tone_factor": 1.25},
    )

    # We don't assume direction of pressure change here (depends on your clamp/limiters),
    # but the state should not be identical.
    assert next_tone != next_neutral


def test_phase5_tone_step_is_deterministic():
    """
    Same inputs must give identical outputs (determinism guarantee).
    """
    from bioflow.engine.state import GlobalState
    from bioflow.engine.physiology.algebraic import BedParameters
    from bioflow.engine.physiology.compliance import CompartmentParameters, step_phase41_compliance

    template = _load_baseline_template()
    rp = template["resolved_parameters"]

    beds = [BedParameters(**b) for b in rp["beds"]]
    baseline_flows = _derive_baseline_flows(rp=rp, beds=beds)

    pump_Q = float(rp["pump"]["Q_ml_per_s"])
    art = CompartmentParameters(**rp["compartments"]["arterial"])
    ven = CompartmentParameters(**rp["compartments"]["venous"])

    init = template["initial_state"]
    prev = GlobalState(
        t_s=0.0,
        V_art_ml=float(init["V_art_ml"]),
        V_ven_ml=float(init["V_ven_ml"]),
        P_art_mmHg=0.0,
        P_ven_mmHg=0.0,
        bed_Q_ml_per_s={},
        bed_perfusion_index={},
    )

    args = dict(
        prev_state=prev,
        dt_s=0.1,
        beds=beds,
        baseline_flows_ml_per_s=baseline_flows,
        pump_Q_ml_per_s=pump_Q,
        art=art,
        ven=ven,
        resolved_parameters={"vascular_tone_factor": 1.25},
    )

    a, ma = step_phase41_compliance(**args)
    b, mb = step_phase41_compliance(**args)

    assert a == b
    assert ma == mb
