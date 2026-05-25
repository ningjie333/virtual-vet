import json
from pathlib import Path


def _load_baseline_template() -> dict:
    p = Path(__file__).parent / "fixtures" / "template_valid_baseline.json"
    return json.loads(p.read_text(encoding="utf-8"))


def test_phase5_tone_neutral_produces_identical_step():
    """
    This locks in the contract:
    If vascular_tone_factor is neutral (or missing), Phase 5 wiring must not change Phase 4.1.
    """
    from bioflow.engine.state import GlobalState
    from bioflow.engine.physiology.algebraic import BedParameters, compute_bed_flows
    from bioflow.engine.physiology.compliance import CompartmentParameters, step_phase41_compliance

    template = _load_baseline_template()

    # These keys may differ in your template. Adjust if needed.
    beds_raw = template["resolved_parameters"]["beds"]
    rp = template["resolved_parameters"]

    beds = [BedParameters(**b) for b in rp["beds"]]

    # baseline_flows_ml_per_s is not stored in this fixture.
    # Derive it deterministically from baseline pressures + bed resistances.
    baseline = template["resolved_parameters"]["baseline"]
    baseline_results = compute_bed_flows(
        P_art_mmHg=float(baseline["P_art_mmHg"]),
        P_ven_mmHg=float(baseline["P_ven_mmHg"]),
        beds=beds,
        # perfusion_index computation needs a dict; values don't matter for Q extraction here
        baseline_flows_ml_per_s={b.bed_id: 1.0 for b in beds},
    )
    baseline_flows = {r.bed_id: r.Q_ml_per_s for r in baseline_results}

    pump_Q = float(template["resolved_parameters"]["pump"]["Q_ml_per_s"])

    art = CompartmentParameters(
        **template["resolved_parameters"]["compartments"]["arterial"])
    ven = CompartmentParameters(
        **template["resolved_parameters"]["compartments"]["venous"])

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

    # Run with knobs missing (neutral by default)
    next1, m1 = step_phase41_compliance(
        prev_state=prev,
        dt_s=0.1,
        beds=beds,
        baseline_flows_ml_per_s=baseline_flows,
        pump_Q_ml_per_s=pump_Q,
        art=art,
        ven=ven,
        resolved_parameters=None,
    )

    # Run with explicit neutral knob
    next2, m2 = step_phase41_compliance(
        prev_state=prev,
        dt_s=0.1,
        beds=beds,
        baseline_flows_ml_per_s=baseline_flows,
        pump_Q_ml_per_s=pump_Q,
        art=art,
        ven=ven,
        resolved_parameters={"vascular_tone_factor": 1.0},
    )

    assert next1 == next2
    assert m1 == m2
