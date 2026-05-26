"""
Experiment 4: Body-weight sweep — test weight-independence of MAP saturation.

For each body weight in [5, 10, 20, 30, 40, 60] kg:
  - Create VirtualCreature(body_weight_kg=W)
  - Set creature.dt = 0.01
  - Run 6000 steps (60 s)
  - Record final MAP, HR, SVR, SV, chemo_drive, FC_count

Key prediction:
  HR_max = 180 (constant, not scaled by weight)
  base_SV = 1.0 * W  (mL)
  SVR_baseline = (100-60) / (85*W/60) = 2400/(85*W)
  base_SV * SVR_baseline = W * 2400/(85*W) = 2400/85 ≈ 28.235  → weight-INDEPENDENT
  → MAP_sat_pred = 60 + (180 * 28.235) / 60 ≈ 144.7 for ALL weights
"""
import sys
import os
import types

SRC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"
)
sys.path.insert(0, SRC_DIR)


def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")


# ---- 1. Monkey-patch all src modules to remove "from src." ----
sys.modules["parameters"] = types.ModuleType("parameters")
exec(
    compile(
        _read_patched(os.path.join(SRC_DIR, "parameters.py")),
        os.path.join(SRC_DIR, "parameters.py"),
        "exec",
    ),
    sys.modules["parameters"].__dict__,
)

for _name in [
    "blood",
    "fluid",
    "cardiac_electrophysiology",
    "noble_purkinje",
    "respiratory_rhythm",
    "heart",
    "lung",
    "kidney",
    "gut",
    "liver",
    "endocrine",
    "neuro",
    "immune",
    "coagulation",
    "lymphatic",
    "lifecycle",
    "toxicology",
    "organ_health",
    "pharmacology",
    "simulation",
]:
    _path = os.path.join(SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

# ---- 2. Imports ----
from simulation import VirtualCreature
from parameters import (
    HEART_RATE_REST_BPM,
    HEART_RATE_STRESS_BPM,
    MEAN_ARTERIAL_PRESSURE_MMHG,
    stroke_volume_ml,
)


# ---- 3. Sweep weights ----
WEIGHTS = [5, 10, 20, 30, 40, 60]
DT = 0.01
STEPS = 6000  # 60 s

print("=" * 120)
print("  Experiment 4: Body-weight sweep — weight independence of MAP saturation")
print("=" * 120)
print(f"  dt = {DT} s,  steps = {STEPS}  ({STEPS * DT:.0f} s simulated)")
print(f"  HR_rest = {HEART_RATE_REST_BPM} bpm,  HR_max = {HEART_RATE_STRESS_BPM} bpm")
print()
print(
    f"  {'Weight':>6s}  {'HR':>6s}  {'MAP':>6s}  {'SVR':>7s}  {'SV':>6s}  "
    f"{'CO':>8s}  {'Chemo':>6s}  {'FC':>4s}  "
    f"{'base_SV':>7s}  {'SVR_bl':>7s}  {'MAP_pred':>8s}  {'MAP_err':>7s}"
)
print("  " + "-" * 114)

for W in WEIGHTS:
    # Create creature
    creature = VirtualCreature(body_weight_kg=W)
    creature.dt = DT

    # Compute theoretical baselines
    base_SV = stroke_volume_ml(W)  # = 1.0 * W
    # SVR baseline (same formula as HeartModule.__init__)
    CO_baseline_ml_min = HEART_RATE_REST_BPM * base_SV
    SVR_baseline = (MEAN_ARTERIAL_PRESSURE_MMHG - 60.0) / (CO_baseline_ml_min / 60.0)
    # Predicted MAP at HR_max saturation
    MAP_sat_pred = 60.0 + (HEART_RATE_STRESS_BPM * base_SV * SVR_baseline) / 60.0

    # Monkey-patch apply_factor to count FCs
    original_apply = creature.apply_factor
    fc_count = [0]  # list for closure mutation

    def counting_apply(cmd, _orig=original_apply, _cnt=fc_count):
        _cnt[0] += 1
        return _orig(cmd)

    creature.apply_factor = counting_apply

    # Run simulation
    for _ in range(STEPS):
        result = creature.step()

    # Read final values from step return
    heart_state = result["heart"]
    neuro_state = result["neuro"]

    final_HR = heart_state["heart_rate_bpm"]
    final_MAP = heart_state["MAP_mmHg"]
    final_SVR = heart_state["SVR"]
    final_SV = heart_state["stroke_volume_ml"]
    final_CO = heart_state["cardiac_output_ml_min"]
    final_chemo = neuro_state["chemoreceptor_drive"]
    final_FC = fc_count[0]

    # Compute prediction error
    MAP_err = final_MAP - MAP_sat_pred

    print(
        f"  {W:>6.0f}  {final_HR:>6.1f}  {final_MAP:>6.1f}  {final_SVR:>7.3f}  "
        f"{final_SV:>6.2f}  {final_CO:>8.1f}  {final_chemo:>6.3f}  {final_FC:>4d}  "
        f"{base_SV:>7.2f}  {SVR_baseline:>7.3f}  {MAP_sat_pred:>8.2f}  {MAP_err:>+7.2f}"
    )

# Footer
print()
print("  base_SV = 1.0 * W  (mL)")
print("  SVR_bl = (100-60) / (85 * W / 60) = 2400/(85*W)")
print("  MAP_pred = 60 + (180 * base_SV * SVR_bl) / 60")
print(f"  base_SV * SVR_bl = W * 2400/(85*W) = 2400/85 ≈ {2400/85:.3f}  (weight-INDEPENDENT)")
print(f"  MAP_pred = {MAP_sat_pred:.2f} for ALL weights (if assumption holds)")
print("=" * 120)
