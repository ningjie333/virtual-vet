def test_phase5_modifiers_defaults_are_neutral():
    from bioflow.engine.physiology.modifiers import apply_modifiers_passthrough

    mods = apply_modifiers_passthrough(resolved_parameters={})
    assert mods.posture == "supine"
    assert mods.vascular_tone_factor == 1.0
    assert mods.blood_volume_factor == 1.0
    assert mods.bed_v0_shift_ml is None
