def test_phase5_tone_increases_resistance_reduces_bed_flows_for_same_pressures():
    """
    compute_bed_flows is pure algebra: Q = deltaP / R.
    So scaling R up must scale Q down when pressures are the same.
    """
    from bioflow.engine.physiology.algebraic import BedParameters, compute_bed_flows
    from bioflow.engine.physiology.modifiers import apply_vascular_tone_to_beds

    beds = [
        BedParameters(bed_id="a", R_mmHg_s_per_ml=2.0),
        BedParameters(bed_id="b", R_mmHg_s_per_ml=4.0),
    ]
    baseline = {"a": 1.0, "b": 1.0}

    res0 = compute_bed_flows(
        P_art_mmHg=100.0, P_ven_mmHg=0.0, beds=beds, baseline_flows_ml_per_s=baseline)

    beds_hi = apply_vascular_tone_to_beds(beds=beds, vascular_tone_factor=2.0)
    res1 = compute_bed_flows(P_art_mmHg=100.0, P_ven_mmHg=0.0,
                             beds=beds_hi, baseline_flows_ml_per_s=baseline)

    # Each flow should be exactly halved (same deltaP, double R).
    assert res1[0].Q_ml_per_s == res0[0].Q_ml_per_s / 2.0
    assert res1[1].Q_ml_per_s == res0[1].Q_ml_per_s / 2.0
