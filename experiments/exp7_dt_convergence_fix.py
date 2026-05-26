#!/usr/bin/env python3
"""Experiment 7: dt convergence test — before/after HR FC fix."""
import sys, os, types, json

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
             os.path.join(SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in ["blood","fluid","cardiac_electrophysiology","noble_purkinje",
              "respiratory_rhythm","heart","lung","kidney","gut","liver",
              "endocrine","neuro","immune","coagulation","lymphatic",
              "lifecycle","toxicology","organ_health","pharmacology","simulation"]:
    _path = os.path.join(SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

from simulation import VirtualCreature
import numpy as np

DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
DC_VALUES = [25, 15, 12, 11, 10, 9, 8, 5]
T_END = 60.0

def run_at_dt(dc_value, dt, t_end=T_END):
    """Run simulation at a specific dt, return summary."""
    creature = VirtualCreature(body_weight_kg=20, age_days=1095)
    creature.lifecycle._original_baselines["lung.diffusion_coefficient"] = dc_value
    creature.dt = dt
    n = int(t_end / dt)

    for _ in range(int(30.0 / dt)):
        creature.step()

    fc_count = 0
    for i in range(n):
        creature.step()
        cd = creature.neuro.chemoreceptor_drive
        # Count actual FactorCommand emissions matching engine's threshold
        if cd * 10.0 > 0.1:
            fc_count += 1

    return {
        "MAP": creature.heart.mean_arterial_pressure,
        "HR": creature.heart.heart_rate,
        "PaO2": creature.blood.arterial_PO2_mmHg,
        "PaCO2": creature.blood.arterial_PCO2_mmHg,
        "chemo_drive": creature.neuro.chemoreceptor_drive,
        "fc_count": fc_count,
        "fc_count_x_dt": round(fc_count * dt, 6),
    }

print("=" * 110)
print("  Experiment 7: dt Convergence — After HR FC dt-scaling fix")
print("  Engine: neuro.py gain=10, FC × dt scaled (rate-based)")
print("=" * 110)

all_results = {}
for dc in DC_VALUES:
    print(f"\n{'='*60}")
    print(f"  DC = {dc}")
    print(f"{'='*60}")
    print(f"{'dt':>7} {'MAP':>8} {'HR':>7} {'PaO2':>7} {'PaCO2':>7} "
          f"{'CD':>10} {'FC_cnt':>7} {'FC×dt':>10}")
    print("-" * 65)

    dc_results = []
    for dt in DT_SWEEP:
        r = run_at_dt(dc, dt)
        dc_results.append(r)
        print(f"{dt:>7.3f} {r['MAP']:>8.2f} {r['HR']:>7.2f} {r['PaO2']:>7.1f} "
              f"{r['PaCO2']:>7.1f} {r['chemo_drive']:>10.6f} "
              f"{r['fc_count']:>7d} {r['fc_count_x_dt']:>10.6f}")

    all_results[str(dc)] = dc_results

# Check convergence: MAP range across dt sweep
print("\n" + "=" * 65)
print("  Convergence summary")
print("=" * 65)
print(f"{'DC':>5} {'MAP_range':>10} {'MAP_last':>9} {'HR_last':>8} {'FC×dt_range':>12}")
print("-" * 50)
for dc in DC_VALUES:
    maps = [r["MAP"] for r in all_results[str(dc)]]
    fc_dt_vals = [r["fc_count_x_dt"] for r in all_results[str(dc)]]
    print(f"{dc:>5.1f} {max(maps)-min(maps):>10.2f} {maps[-1]:>9.2f} "
          f"{all_results[str(dc)][-1]['HR']:>8.2f} "
          f"{max(fc_dt_vals)-min(fc_dt_vals):>12.6f}")

# Save
out = {
    "engine_state": "FIXED: neuro.py gain=10, FC HR × dt scaled",
    "dt_sweep": DT_SWEEP,
    "t_end": T_END,
    "results": all_results,
}
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "exp7_fixed_results.json"), "w") as f:
    json.dump(out, f, indent=2)
print("\nSaved to experiments/exp7_fixed_results.json")
