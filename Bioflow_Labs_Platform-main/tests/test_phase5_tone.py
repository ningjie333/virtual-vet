def test_phase5_tone_factor_neutral_is_identical():
    from bioflow.engine.physiology.modifiers import apply_vascular_tone_to_beds
    from bioflow.engine.physiology.algebraic import BedParameters

    beds = [BedParameters(bed_id="a", R_mmHg_s_per_ml=2.0)]
    beds2 = apply_vascular_tone_to_beds(beds=beds, vascular_tone_factor=1.0)

    # Neutral fast-path: return the exact same list object (nice and strict)
    assert beds2 is beds


def test_phase5_tone_scales_resistance():
    from bioflow.engine.physiology.modifiers import apply_vascular_tone_to_beds
    from bioflow.engine.physiology.algebraic import BedParameters

    beds = [BedParameters(bed_id="a", R_mmHg_s_per_ml=2.0)]
    beds2 = apply_vascular_tone_to_beds(beds=beds, vascular_tone_factor=1.5)

    assert beds2[0].R_mmHg_s_per_ml == 3.0
    # Purity: original unchanged
    assert beds[0].R_mmHg_s_per_ml == 2.0
