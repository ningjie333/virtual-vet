#!/usr/bin/env python3
"""Experiment 6: diffusion coefficient sweep — FC_count × dt constant vs pathology severity."""
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

DT = 0.01
T_END = 120.0

FC_THRESHOLD = 0.1
DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]

def run_dc(dc_value, chemo_gain, dt=DT, t_end=T_END):
    """Run simulation with a specific diffusion coefficient and chemo gain."""
    creature = VirtualCreature(body_weight_kg=20, age_days=1095)
    creature.lifecycle._original_baselines["lung.diffusion_coefficient"] = dc_value
    creature.dt = dt
    n = int(t_end / dt)

    for _ in range(int(30.0 / dt)):
        creature.step()

    traces = {
        "t": np.zeros(n),
        "MAP": np.zeros(n),
        "HR": np.zeros(n),
        "PaO2": np.zeros(n),
        "PaCO2": np.zeros(n),
        "chemo_drive": np.zeros(n),
        "FC": np.zeros(n, dtype=bool),
    }
    fc_count = 0

    for i in range(n):
        creature.step()
        traces["t"][i] = creature.current_time_s
        traces["MAP"][i] = creature.heart.mean_arterial_pressure
        traces["HR"][i] = creature.heart.heart_rate
        traces["PaO2"][i] = creature.blood.arterial_PO2_mmHg
        traces["PaCO2"][i] = creature.blood.arterial_PCO2_mmHg
        cd = creature.neuro.chemoreceptor_drive
        traces["chemo_drive"][i] = cd
        emitted = (cd * chemo_gain > FC_THRESHOLD)
        traces["FC"][i] = emitted
        if emitted:
            fc_count += 1

    return traces, fc_count

def dt_sweep_at_dc(dc_value, chemo_gain):
    """Sweep dt at a fixed DC and gain to verify O(1) constancy."""
    results = []
    for dt in DT_SWEEP:
        traces, fc_count = run_dc(dc_value, chemo_gain, dt=dt, t_end=60.0)
        fc_dt = fc_count * dt
        mean_po2 = np.mean(traces["PaO2"])
        mean_map = np.mean(traces["MAP"])
        mean_cd = np.mean(traces["chemo_drive"])
        results.append({
            "dt": dt,
            "fc_count": fc_count,
            "fc_count_x_dt": round(fc_dt, 6),
            "mean_PaO2": round(mean_po2, 1),
            "mean_MAP": round(mean_map, 1),
            "mean_chemo_drive": round(mean_cd, 6),
        })
    return results

def classify_fc(fc_count, t_end, map_final):
    """Classify FC regime based on count and MAP."""
    if fc_count == 0:
        return "健康"
    max_possible = t_end / DT
    duty = fc_count / max_possible
    if duty > 0.99:
        return "饱和"
    if duty < 0.01:
        return "微量FC"
    return f"间歇FC({duty:.1%})"

# ================================================================
# 2D sweep: DC × CHEMO_GAIN
# ================================================================
print("=" * 100)
print("  Experiment 6: 2D DC × CHEMO_GAIN Sweep — FC Regime Mapping")
print("=" * 100)

DC_VALUES = [25, 20, 15, 14, 13, 12, 11, 10, 9, 8, 7, 5]
CHEMO_GAINS = [15, 12, 10, 8, 6, 5, 4, 3]

all_results = {}
for gain in CHEMO_GAINS:
    threshold = FC_THRESHOLD / gain
    print(f"\n{'='*60}")
    print(f"  CHEMO_GAIN={gain} (threshold={threshold:.4f})")
    print(f"{'='*60}")
    gain_results = {}
    for dc in DC_VALUES:
        traces, fc_count = run_dc(dc, gain, dt=DT, t_end=T_END)
        fc_dt = fc_count * DT
        duty = fc_count / (T_END / DT)

        mean_po2 = np.mean(traces["PaO2"])
        mean_map = np.mean(traces["MAP"])
        mean_cd = np.mean(traces["chemo_drive"])
        po2_min = np.min(traces["PaO2"][-500:])
        po2_max = np.max(traces["PaO2"][-500:])
        map_final = traces["MAP"][-1]
        hr_final = traces["HR"][-1]
        cd_min = np.min(traces["chemo_drive"][-500:])
        cd_max = np.max(traces["chemo_drive"][-500:])

        status = classify_fc(fc_count, T_END, map_final)
        print(f"  DC={dc:>5.1f}: PaO2={mean_po2:>6.1f} ({po2_min:.1f}-{po2_max:.1f}) "
              f"MAP={map_final:>6.1f} CD={mean_cd:.6f} [{cd_min:.6f}-{cd_max:.6f}] "
              f"FC={fc_count:>6d} duty={duty:.4f} {status:>12}")

        gain_results[str(dc)] = {
            "PaO2_mean": round(mean_po2, 1),
            "PaO2_min": round(po2_min, 1),
            "PaO2_max": round(po2_max, 1),
            "MAP_mean": round(mean_map, 1),
            "MAP_final": round(map_final, 1),
            "HR_final": round(hr_final, 1),
            "chemo_drive_mean": round(mean_cd, 6),
            "chemo_drive_min": round(cd_min, 6),
            "chemo_drive_max": round(cd_max, 6),
            "FC_count": fc_count,
            "duty_cycle": round(duty, 6),
            "FC_count_x_dt": round(fc_dt, 6),
            "status": status,
        }
    all_results[str(gain)] = gain_results

# ================================================================
# DT sweep at intermittent zone points
# ================================================================
print("\n" + "=" * 100)
print("  DT Sweep verification at intermittent zone points")
print("=" * 100)
dt_sweep_results = {}
for gain, dc in [(10, 10), (8, 10), (8, 9), (6, 9), (5, 9)]:
    print(f"\n--- gain={gain}, DC={dc} ---")
    results = dt_sweep_at_dc(dc, gain)
    print(f"{'dt':>7} {'FC_cnt':>8} {'FC×dt':>10} {'PaO2':>7} {'MAP':>7} {'chemo':>10}")
    print("-" * 55)
    for r in results:
        print(f"{r['dt']:>7.3f} {r['fc_count']:>8d} {r['fc_count_x_dt']:>10.6f} "
              f"{r['mean_PaO2']:>7.1f} {r['mean_MAP']:>7.1f} {r['mean_chemo_drive']:>10.6f}")
    dt_sweep_results[f"gain{gain}_dc{dc}"] = results

# Save
with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "exp6_results.json"), "w") as f:
    json.dump({
        "fc_threshold": FC_THRESHOLD,
        "dt": DT,
        "t_end": T_END,
        "dc_sweep_2d": all_results,
        "dt_sweep": dt_sweep_results,
    }, f, indent=2)
print("\nResults saved to experiments/exp6_results.json")
