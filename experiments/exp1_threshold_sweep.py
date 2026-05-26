"""Experiment 1: FC threshold sweep — find critical threshold and bias scaling.

For each threshold, monkey-patches NeuroModule.compute to gate baroreflex HR
FCs at the given |net_HR_add| threshold.  Runs 60 s of a healthy 20 kg dog
(Euler, dt=0.01) and records final MAP, HR, FC count, and chemo drive.
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
from neuro import NeuroModule, FactorCommand

ORIG_COMPUTE = NeuroModule.compute


def make_patched_compute(threshold: float):
    """Return a NeuroModule.compute that only fires the HR FC when
    |net_HR_add| > `threshold`.  Non-HR FCs (SVR, RR, gut) pass
    through unchanged."""

    def patched_compute(self, dt, heart_state, lung_state):
        result = ORIG_COMPUTE(self, dt, heart_state, lung_state)
        net_HR_add = result.get("net_HR_add", 0.0)
        # Keep everything except the HR FC
        kept = [
            fc
            for fc in result.get("factor_commands", [])
            if fc.target != "heart.heart_rate"
        ]
        # Re-add HR FC only if above threshold
        if abs(net_HR_add) > threshold:
            kept.append(FactorCommand("heart.heart_rate", "add", net_HR_add))
        result["factor_commands"] = kept
        return result

    return patched_compute


# ---- 3. Threshold sweep ----
THRESHOLDS = [0.01, 0.02, 0.05, 0.1, 0.12, 0.15, 0.2, 0.3, 0.5, 1.0]
N_STEPS = 6000  # 60 s at dt = 0.01

results = []

for thr in THRESHOLDS:
    NeuroModule.compute = make_patched_compute(thr)

    creature = VirtualCreature(body_weight_kg=20)
    creature.dt = 0.01
    fc_count = 0
    for _ in range(N_STEPS):
        creature.step()
        chemo_drive = creature.neuro.chemoreceptor_drive
        net_HR_add = chemo_drive * 15.0
        if net_HR_add > thr:
            fc_count += 1

    results.append(
        {
            "threshold": thr,
            "MAP": round(creature.heart.mean_arterial_pressure, 3),
            "HR": round(creature.heart.heart_rate, 3),
            "fc_count": fc_count,
            "chemo_drive": round(creature.neuro.chemoreceptor_drive, 6),
        }
    )
    print(
        f"thr={thr:5.3f}  MAP={results[-1]['MAP']:7.2f}  "
        f"HR={results[-1]['HR']:7.1f}  FCs={fc_count:5d}  "
        f"chemo={results[-1]['chemo_drive']:8.6f}"
    )

# ---- 4. No-neuro baseline (completely disable neuro) ----
print("\n--- No-neuro baseline (neuro.compute → no FCs) ---")
NeuroModule.compute = ORIG_COMPUTE  # restore normal compute first, then override


def noop_compute(self, dt, heart_state, lung_state):
    """NeuroModule.compute that produces no factor_commands at all."""
    return {
        "sympathetic_tone": self.sympathetic_tone,
        "parasympathetic_tone": self.parasympathetic_tone,
        "consciousness": self.consciousness,
        "seizure": self.seizure,
        "pain_level": self.pain_level,
        "chemoreceptor_drive": self.chemoreceptor_drive,
        "net_HR_add": 0.0,
        "net_SVR_mult": 1.0,
        "factor_commands": [],
    }


NeuroModule.compute = noop_compute

creature = VirtualCreature(body_weight_kg=20)
creature.dt = 0.01
for _ in range(N_STEPS):
    creature.step()

print(
    f"No-neuro baseline:  MAP={creature.heart.mean_arterial_pressure:.1f}  "
    f"HR={creature.heart.heart_rate:.1f}  "
    f"chemo={creature.neuro.chemoreceptor_drive:.6f}"
)

# ---- 5. Restore original ----
NeuroModule.compute = ORIG_COMPUTE

# ---- 6. Print summary ----
print()
print("=" * 75)
print("  FC THRESHOLD SWEEP  —  healthy 20 kg dog, 60 s Euler (dt = 0.01)")
print("=" * 75)
print(f"{'threshold':>10} {'MAP':>8} {'HR':>8} {'FC_count':>9} {'chemo_drive':>12}")
print("-" * 75)
for r in results:
    print(
        f"{r['threshold']:10.3f} {r['MAP']:8.2f} {r['HR']:8.1f} "
        f"{r['fc_count']:9d} {r['chemo_drive']:12.6f}"
    )
print("-" * 75)

# Find transition point(s)
fc_vals = [r["fc_count"] for r in results]
baseline_fc = fc_vals[0]
for i in range(1, len(fc_vals)):
    if fc_vals[i] != baseline_fc:
        print(
            f"\nTransition at threshold = {results[i]['threshold']:.3f}: "
            f"FCs changed from {baseline_fc} to {fc_vals[i]}"
        )
        baseline_fc = fc_vals[i]

if all(fc == 0 for fc in fc_vals):
    print(
        "\nNo FCs fired at any threshold — the simulation is at a "
        "healthy steady state with zero chemoreceptor drive."
    )

print("\nDone.")
