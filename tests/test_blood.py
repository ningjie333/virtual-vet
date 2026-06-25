"""
Unit tests for BloodCompartment class in src/blood.py
"""

from src.blood import BloodCompartment


# Hb derived from HCT: default plasma_fraction=0.55 → HCT=45% → Hb=45/3.1≈14.52

def test_arterial_O2_content_normal():
    """Normal arterial: PO2=95, sat=0.97, Hb from HCT → ~19.07 mL O2/100mL"""
    blood = BloodCompartment(total_volume_ml=1000)
    hct = (blood.red_cell_volume_ml / blood.total_volume_ml) * 100  # 45%
    hb = hct / 3.1
    result = blood.get_arterial_O2_content()
    expected = hb * 1.34 * 0.97 + 0.003 * 95.0
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"


def test_venous_O2_content_normal():
    """Normal venous: PO2=40, sat=0.70, Hb from HCT → ~13.36 mL O2/100mL"""
    blood = BloodCompartment(total_volume_ml=1000)
    hct = (blood.red_cell_volume_ml / blood.total_volume_ml) * 100
    hb = hct / 3.1
    result = blood.get_venous_O2_content()
    expected = hb * 1.34 * 0.70 + 0.003 * 40.0
    assert abs(result - expected) < 0.01, f"Expected {expected}, got {result}"


def test_O2_content_hypoxia():
    """Low PO2 (40) and low sat (0.50) should give lower O2 content than normal"""
    blood = BloodCompartment(total_volume_ml=1000)
    # Hypoxia values
    hypoxia_content = blood.calculate_O2_content(PO2_mmHg=40, saturation=0.50)
    # Normal arterial
    normal_content = blood.get_arterial_O2_content()
    assert hypoxia_content < normal_content, (
        f"Hypoxia content ({hypoxia_content}) should be less than normal ({normal_content})"
    )


def test_O2_content_hyperoxia():
    """High PO2 (110) and high sat (0.99) should give higher O2 content than normal"""
    blood = BloodCompartment(total_volume_ml=1000)
    # Hyperoxia values
    hyperoxia_content = blood.calculate_O2_content(PO2_mmHg=110, saturation=0.99)
    # Normal arterial
    normal_content = blood.get_arterial_O2_content()
    assert hyperoxia_content > normal_content, (
        f"Hyperoxia content ({hyperoxia_content}) should be greater than normal ({normal_content})"
    )


def test_O2_content_formula():
    """Verify the formula: Hb(from HCT) * 1.34 * sat + 0.003 * PO2"""
    blood = BloodCompartment(total_volume_ml=1000)
    hct = (blood.red_cell_volume_ml / blood.total_volume_ml) * 100
    hb = hct / 3.1
    result = blood.calculate_O2_content(PO2_mmHg=95.0, saturation=0.97)
    expected = hb * 1.34 * 0.97 + 0.003 * 95.0
    assert abs(result - expected) < 1e-6, f"Expected {expected}, got {result}"


def test_arterial_venous_difference():
    """Arterial O2 content should be higher than venous with default values"""
    blood = BloodCompartment(total_volume_ml=1000)
    art = blood.get_arterial_O2_content()
    ven = blood.get_venous_O2_content()
    assert art > ven, (
        f"Arterial O2 content ({art}) should be higher than venous ({ven})"
    )


def test_summary_returns_dict():
    """summary() should return a dict with all expected keys"""
    blood = BloodCompartment(total_volume_ml=1000)
    s = blood.summary()
    expected_keys = {
        "arterial_PO2", "arterial_PCO2", "venous_PO2", "venous_PCO2",
        "saturation_art", "saturation_ven",
        "glucose", "lactate", "sodium", "potassium", "temperature_C",
        # Liver/gut markers
        "albumin", "ammonia", "ALT", "AST", "ALP", "GGT", "bile_acids",
        # Endocrine
        "T3", "insulin", "cortisol", "calcium",
        # Neurological
        "consciousness", "seizure", "pain", "chemoreceptor_drive",
        # Immune
        "WBC", "CRP", "cytokine", "acute_phase", "immune_suppression", "coagulation",
        # Coagulation
        "PT", "aPTT", "fibrinogen",
        # Lymphatic/Spleen
        "splenic_reserve", "lymph_flow", "interstitial_fluid",
    }
    assert isinstance(s, dict), f"Expected dict, got {type(s)}"
    assert set(s.keys()) == expected_keys, (
        f"Keys mismatch.\nMissing: {expected_keys - set(s.keys())}\nExtra: {set(s.keys()) - expected_keys}"
    )


def test_initial_values_in_normal_range():
    """Default constructor values within canine physiological normals"""
    blood = BloodCompartment(total_volume_ml=1000)
    # PO2: 90-100 mmHg
    assert 90 <= blood.arterial_PO2_mmHg <= 100, (
        f"Arterial PO2 {blood.arterial_PO2_mmHg} outside normal range 90-100"
    )
    # PCO2: 35-45 mmHg
    assert 35 <= blood.arterial_PCO2_mmHg <= 45, (
        f"Arterial PCO2 {blood.arterial_PCO2_mmHg} outside normal range 35-45"
    )
    # pH: 7.35-7.45
    assert 7.35 <= blood.arterial_pH <= 7.45, (
        f"Arterial pH {blood.arterial_pH} outside normal range 7.35-7.45"
    )


def test_canine_default_arterial_blood_gases_match_merck_reference_ranges():
    """Merck canine arterial blood gas reference windows should hold at baseline.

    Source:
    - Merck Veterinary Manual, blood gas analysis reference ranges
      https://www.merckvetmanual.com/multimedia/table/blood-gas-analysis-reference-ranges
    """
    blood = BloodCompartment(total_volume_ml=86.0 * 20.0)

    assert 85.0 <= blood.arterial_PO2_mmHg <= 95.0, (
        f"PaO2 {blood.arterial_PO2_mmHg} outside Merck canine arterial range 85-95 mmHg"
    )
    assert 29.0 <= blood.arterial_PCO2_mmHg <= 42.0, (
        f"PaCO2 {blood.arterial_PCO2_mmHg} outside Merck canine arterial range 29-42 mmHg"
    )
    assert 7.35 <= blood.arterial_pH <= 7.46, (
        f"pH {blood.arterial_pH} outside Merck canine arterial range 7.35-7.46"
    )


def test_custom_volume():
    """Custom total_volume_ml should set plasma/red_cell volumes (55/45 split)"""
    blood = BloodCompartment(total_volume_ml=2000)
    assert blood.total_volume_ml == 2000, (
        f"Expected total_volume_ml=2000, got {blood.total_volume_ml}"
    )
    assert abs(blood.plasma_volume_ml - 1100.0) < 1e-6, (
        f"Expected plasma_volume_ml=1100.0 (55%), got {blood.plasma_volume_ml}"
    )
    assert abs(blood.red_cell_volume_ml - 900.0) < 1e-6, (
        f"Expected red_cell_volume_ml=900.0 (45%), got {blood.red_cell_volume_ml}"
    )
