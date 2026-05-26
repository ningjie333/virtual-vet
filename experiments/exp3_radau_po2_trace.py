"""
exp3_radau_po2_trace.py — Run unified RHS Radau solver and trace PO2 + chemoreceptor_drive.

Key question: does the unified RHS path produce oscillating PO2 (62-74 mmHg range)?

- If YES: unified path also has chemoreceptor activation but no FC mechanism
          → proves FC mechanism is NOT needed for oscillation
- If NO: unified path avoids bias because PO2 doesn't oscillate
          → proves FC mechanism IS the root cause of bias

In the unified RHS path:
  - neuro.derivatives() computes chemoreceptor_drive but neither issues FactorCommands
    nor routes the output to heart module
  - heart.derivatives() does NOT receive chemoreceptor_drive as input
  - So the neuro→HR→CO→lung→PO2 feedback loop (Loop B) is absent
"""

import os, sys, types, json, time, signal, threading
import numpy as np

# ── Monkey-patch: strip "from src." prefixes ──────────────────────────────────
EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(EXPERIMENTS_DIR)
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    src = open(path, encoding='utf-8').read()
    src = src.replace('from src.', 'from ')
    src = src.replace('import src.', 'import ')
    return src

# parameters module first (no src. references initially)
sys.modules['parameters'] = types.ModuleType('parameters')
exec(compile(_read_patched(os.path.join(SRC_DIR, 'parameters.py')),
             os.path.join(SRC_DIR, 'parameters.py'), 'exec'),
     sys.modules['parameters'].__dict__)

# all other modules
for _name in ['blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
              'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
              'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
              'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

from simulation import VirtualCreature

# ── Settings ──────────────────────────────────────────────────────────────────
T_END = 60.0        # seconds
DT_SAVE = 0.5       # seconds (save every 0.5s)
TIMEOUT = 300.0     # 5-minute timeout for Radau

# ── Create creature ───────────────────────────────────────────────────────────
creature = VirtualCreature(body_weight_kg=20.0)
print("=== VirtualCreature initialized ===")
print(f"  body_weight = {creature.w} kg")
print(f"  initial arterial_PO2 = {creature.blood.arterial_PO2_mmHg:.1f} mmHg")
print(f"  initial arterial_PCO2 = {creature.blood.arterial_PCO2_mmHg:.1f} mmHg")
print(f"  initial heart_rate = {creature.heart.heart_rate:.1f} bpm")
print(f"  initial MAP = {creature.heart.mean_arterial_pressure:.1f} mmHg")
print(f"  initial neuro.chemoreceptor_drive = {creature.neuro.chemoreceptor_drive:.4f}")
print()

# ── Run Radau solver with timeout ────────────────────────────────────────────
result = {"status": "unknown"}
sol = None

def run_solver():
    global sol, result
    try:
        sol = creature.run_unified_ivp(t_end=T_END, dt_save=DT_SAVE)
        result["status"] = "success"
        result["nfev"] = getattr(sol, 'nfev', None)
        result["success"] = getattr(sol, 'success', None)
        result["message"] = getattr(sol, 'message', None)
        result["n_steps"] = len(getattr(sol, 't', []))
    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)

thread = threading.Thread(target=run_solver, daemon=True)
thread.start()
thread.join(timeout=TIMEOUT)

if thread.is_alive():
    print(f"WARNING: Solver timed out after {TIMEOUT}s!")
    result["status"] = "timeout"
else:
    print(f"Solver finished: status={result['status']}")
    if result.get("success") is not None:
        print(f"  solve_ivp success={result['success']}, nfev={result.get('nfev')}")
        print(f"  message: {result.get('message')}")

print()

# ── If solver succeeded, extract and analyze time series ─────────────────────
if sol is not None and hasattr(sol, 't') and len(sol.t) > 1:
    t_arr = sol.t
    n_steps = len(t_arr)
    print(f"Radau returned {n_steps} time points")

    # After each save point, _unpack_unified_state was called by _unified_rhs.
    # But solve_ivp only returns t_eval points and calls rhs at internal steps.
    # We need to get the state at each t_eval point.
    # sol.y has shape (n_vars, n_timesteps).
    # We can reconstruct the state at each timestep.

    # Extract series for our target variables
    # Build state map to find indices
    state_map = creature._build_unified_state_map()

    # Find indices for the variables we care about
    hr_idx = state_map.get(("heart", "HR"))
    sv_idx = state_map.get(("heart", "SV"))
    svr_idx = state_map.get(("heart", "SVR"))
    bv_idx = state_map.get(("heart", "blood_volume"))
    rr_idx = state_map.get(("lung", "RR"))
    tv_idx = state_map.get(("lung", "TV"))
    vq_idx = state_map.get(("lung", "VQ"))

    print(f"\nState vector indices:")
    print(f"  HR={hr_idx}, SV={sv_idx}, SVR={svr_idx}, BV={bv_idx}")
    print(f"  RR={rr_idx}, TV={tv_idx}, VQ={vq_idx}")

    # For each save point, unpack the state so we can read blood gases,
    # MAP, and other non-state variables
    print(f"\nUnpacking state at save points to read blood gases...")

    po2_series = []
    pco2_series = []
    hr_series = []
    map_series = []
    rr_series = []
    chemo_series = []
    sat_series = []
    ph_series = []

    # The save points are exactly t_eval points
    # But we need to be careful: solve_ivp returns y at t_eval points
    # Let's extract y
    y_arr = sol.y  # shape (n_vars, n_steps)

    for i in range(n_steps):
        t_i = t_arr[i]
        y_i = y_arr[:, i]

        # Unpack into creature's module attributes
        creature._unpack_unified_state(y_i)

        # Now read the blood gases and other derived values
        po2_series.append({
            't': float(t_i),
            'arterial_PO2_mmHg': float(creature.blood.arterial_PO2_mmHg),
            'arterial_PCO2_mmHg': float(creature.blood.arterial_PCO2_mmHg),
            'arterial_saturation': float(creature.blood.arterial_saturation),
            'arterial_pH': float(creature.blood.arterial_pH),
            'HR_bpm': float(creature.heart.heart_rate),
            'MAP_mmHg': float(creature.heart.mean_arterial_pressure),
            'SV_ml': float(creature.heart.stroke_volume),
            'SVR': float(creature.heart.SVR),
            'blood_volume_ml': float(creature.heart.circulating_volume_ml),
            'RR_bpm': float(creature.lung.respiratory_rate),
            'tidal_volume_ml': float(creature.lung.tidal_volume),
            'chemoreceptor_drive': float(creature.neuro.chemoreceptor_drive),
            'sympathetic_tone': float(creature.neuro.sympathetic_tone),
            'parasympathetic_tone': float(creature.neuro.parasympathetic_tone),
        })

    # Print summary statistics
    po2_vals = np.array([s['arterial_PO2_mmHg'] for s in po2_series])
    pco2_vals = np.array([s['arterial_PCO2_mmHg'] for s in po2_series])
    hr_vals = np.array([s['HR_bpm'] for s in po2_series])
    map_vals = np.array([s['MAP_mmHg'] for s in po2_series])
    chemo_vals = np.array([s['chemoreceptor_drive'] for s in po2_series])

    print("\n" + "=" * 70)
    print("  Unified RHS Radau Trace Results")
    print("=" * 70)

    print(f"\nTime points: {t_arr[0]:.1f} to {t_arr[-1]:.1f} s, step={DT_SAVE}s")
    print(f"Total points: {n_steps}")

    print(f"\n{'Variable':<25} {'Initial':>10} {'Final':>10} {'Mean':>10} {'Std':>10} {'Min':>10} {'Max':>10}")
    print("-" * 85)
    print(f"{'arterial_PO2 (mmHg)':<25} {po2_vals[0]:>10.2f} {po2_vals[-1]:>10.2f} {np.mean(po2_vals):>10.2f} {np.std(po2_vals):>10.2f} {np.min(po2_vals):>10.2f} {np.max(po2_vals):>10.2f}")
    print(f"{'arterial_PCO2 (mmHg)':<25} {pco2_vals[0]:>10.2f} {pco2_vals[-1]:>10.2f} {np.mean(pco2_vals):>10.2f} {np.std(pco2_vals):>10.2f} {np.min(pco2_vals):>10.2f} {np.max(pco2_vals):>10.2f}")
    print(f"{'HR (bpm)':<25} {hr_vals[0]:>10.2f} {hr_vals[-1]:>10.2f} {np.mean(hr_vals):>10.2f} {np.std(hr_vals):>10.2f} {np.min(hr_vals):>10.2f} {np.max(hr_vals):>10.2f}")
    print(f"{'MAP (mmHg)':<25} {map_vals[0]:>10.2f} {map_vals[-1]:>10.2f} {np.mean(map_vals):>10.2f} {np.std(map_vals):>10.2f} {np.min(map_vals):>10.2f} {np.max(map_vals):>10.2f}")
    print(f"{'chemoreceptor_drive':<25} {chemo_vals[0]:>10.4f} {chemo_vals[-1]:>10.4f} {np.mean(chemo_vals):>10.4f} {np.std(chemo_vals):>10.4f} {np.min(chemo_vals):>10.4f} {np.max(chemo_vals):>10.4f}")

    # Check PO2 range
    po2_range = np.max(po2_vals) - np.min(po2_vals)
    if po2_range > 5.0:
        print(f"\n>>> PO2 oscillates: range = {po2_range:.2f} mmHg (in {np.min(po2_vals):.0f}-{np.max(po2_vals):.0f} range)")
        print(f">>> CONCLUSION: unified RHS ALSO produces oscillating PO2")
    else:
        print(f"\n>>> PO2 is STABLE: range = {po2_range:.2f} mmHg")
        print(f">>> CONCLUSION: unified RHS does NOT produce oscillating PO2")

    # Chemoreceptor drive analysis
    if np.max(chemo_vals) > 0.05:
        print(f">>> Chemoreceptor IS activated (max={np.max(chemo_vals):.4f})")
    else:
        print(f">>> Chemoreceptor is NOT activated (max={np.max(chemo_vals):.4f})")

    # Print full time series
    print("\n\nFull time series (every save point):")
    print(f"{'t(s)':>6} {'PO2':>7} {'PCO2':>7} {'HR':>7} {'MAP':>7} {'RR':>7} {'Chemo':>7} {'Sat':>7} {'pH':>6}")
    print("-" * 62)
    for s in po2_series:
        print(f"{s['t']:>6.1f} {s['arterial_PO2_mmHg']:>7.1f} {s['arterial_PCO2_mmHg']:>7.1f} "
              f"{s['HR_bpm']:>7.1f} {s['MAP_mmHg']:>7.1f} {s['RR_bpm']:>7.1f} "
              f"{s['chemoreceptor_drive']:>7.4f} {s['arterial_saturation']:>7.4f} "
              f"{s['arterial_pH']:>6.3f}")

    # Save to JSON
    output = {
        "solver_status": result,
        "summary": {
            "PO2_mean": float(np.mean(po2_vals)),
            "PO2_std": float(np.std(po2_vals)),
            "PO2_min": float(np.min(po2_vals)),
            "PO2_max": float(np.max(po2_vals)),
            "PO2_range": float(po2_range),
            "PCO2_mean": float(np.mean(pco2_vals)),
            "PCO2_std": float(np.std(pco2_vals)),
            "HR_mean": float(np.mean(hr_vals)),
            "MAP_mean": float(np.mean(map_vals)),
            "chemo_max": float(np.max(chemo_vals)),
        },
        "time_series": po2_series,
    }
    out_path = os.path.join(EXPERIMENTS_DIR, "exp3_radau_po2_trace.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nData saved to {out_path}")

elif result["status"] == "timeout":
    print(f"\nRadau solver timed out after {TIMEOUT}s.")
    print("Falling back to manual Euler stepping with _unified_rhs...")

    # ── Manual Euler fallback ────────────────────────────────────────────
    DT = 0.001
    SAVE_INTERVAL = int(0.5 / DT)

    creature2 = VirtualCreature(body_weight_kg=20.0)
    y = creature2._pack_unified_state()

    # Warmup
    _ = creature2._unified_rhs(0.0, y)

    t = 0.0
    step = 0
    save_step = 0
    po2_series = []

    print(f"Manual Euler stepping with dt={DT}s, saving every {0.5}s...")

    while t <= T_END:
        if step % SAVE_INTERVAL == 0:
            po2_series.append({
                't': float(t),
                'arterial_PO2_mmHg': float(creature2.blood.arterial_PO2_mmHg),
                'arterial_PCO2_mmHg': float(creature2.blood.arterial_PCO2_mmHg),
                'arterial_saturation': float(creature2.blood.arterial_saturation),
                'arterial_pH': float(creature2.blood.arterial_pH),
                'HR_bpm': float(creature2.heart.heart_rate),
                'MAP_mmHg': float(creature2.heart.mean_arterial_pressure),
                'SV_ml': float(creature2.heart.stroke_volume),
                'SVR': float(creature2.heart.SVR),
                'blood_volume_ml': float(creature2.heart.circulating_volume_ml),
                'RR_bpm': float(creature2.lung.respiratory_rate),
                'tidal_volume_ml': float(creature2.lung.tidal_volume),
                'chemoreceptor_drive': float(creature2.neuro.chemoreceptor_drive),
            })
            save_step += 1

        dydt = creature2._unified_rhs(t, y)
        y = y + DT * dydt
        t += DT
        step += 1

        if step % 10000 == 0 and step > 0:
            print(f"  t={t:.1f}s, PO2={creature2.blood.arterial_PO2_mmHg:.1f}, "
                  f"HR={creature2.heart.heart_rate:.1f}, chemo={creature2.neuro.chemoreceptor_drive:.4f}")

    print(f"\nManual Euler completed: {step} steps, {save_step} save points")

    # Analyze
    po2_vals = np.array([s['arterial_PO2_mmHg'] for s in po2_series])
    pco2_vals = np.array([s['arterial_PCO2_mmHg'] for s in po2_series])
    hr_vals = np.array([s['HR_bpm'] for s in po2_series])
    map_vals = np.array([s['MAP_mmHg'] for s in po2_series])
    chemo_vals = np.array([s['chemoreceptor_drive'] for s in po2_series])

    print("\n" + "=" * 70)
    print("  Manual Euler (using _unified_rhs) Trace Results")
    print("=" * 70)
    print(f"\n{'Variable':<25} {'Initial':>10} {'Final':>10} {'Mean':>10} {'Std':>10} {'Min':>10} {'Max':>10}")
    print("-" * 85)
    print(f"{'arterial_PO2 (mmHg)':<25} {po2_vals[0]:>10.2f} {po2_vals[-1]:>10.2f} {np.mean(po2_vals):>10.2f} {np.std(po2_vals):>10.2f} {np.min(po2_vals):>10.2f} {np.max(po2_vals):>10.2f}")
    print(f"{'arterial_PCO2 (mmHg)':<25} {pco2_vals[0]:>10.2f} {pco2_vals[-1]:>10.2f} {np.mean(pco2_vals):>10.2f} {np.std(pco2_vals):>10.2f} {np.min(pco2_vals):>10.2f} {np.max(pco2_vals):>10.2f}")
    print(f"{'HR (bpm)':<25} {hr_vals[0]:>10.2f} {hr_vals[-1]:>10.2f} {np.mean(hr_vals):>10.2f} {np.std(hr_vals):>10.2f} {np.min(hr_vals):>10.2f} {np.max(hr_vals):>10.2f}")
    print(f"{'MAP (mmHg)':<25} {map_vals[0]:>10.2f} {map_vals[-1]:>10.2f} {np.mean(map_vals):>10.2f} {np.std(map_vals):>10.2f} {np.min(map_vals):>10.2f} {np.max(map_vals):>10.2f}")
    print(f"{'chemoreceptor_drive':<25} {chemo_vals[0]:>10.4f} {chemo_vals[-1]:>10.4f} {np.mean(chemo_vals):>10.4f} {np.std(chemo_vals):>10.4f} {np.min(chemo_vals):>10.4f} {np.max(chemo_vals):>10.4f}")

    po2_range = np.max(po2_vals) - np.min(po2_vals)
    if po2_range > 5.0:
        print(f"\n>>> PO2 oscillates: range = {po2_range:.2f} mmHg")
    else:
        print(f"\n>>> PO2 is stable: range = {po2_range:.2f} mmHg")

    if np.max(chemo_vals) > 0.05:
        print(f">>> Chemoreceptor IS activated (max={np.max(chemo_vals):.4f})")
    else:
        print(f">>> Chemoreceptor is NOT activated (max={np.max(chemo_vals):.4f})")

    # Print full time series (every 5th save point to avoid spam)
    print(f"\n\nTime series (every 5th save point):")
    print(f"{'t(s)':>6} {'PO2':>7} {'PCO2':>7} {'HR':>7} {'MAP':>7} {'RR':>7} {'Chemo':>7} {'Sat':>7} {'pH':>6}")
    print("-" * 62)
    for i, s in enumerate(po2_series):
        if i % 5 == 0:
            print(f"{s['t']:>6.1f} {s['arterial_PO2_mmHg']:>7.1f} {s['arterial_PCO2_mmHg']:>7.1f} "
                  f"{s['HR_bpm']:>7.1f} {s['MAP_mmHg']:>7.1f} {s['RR_bpm']:>7.1f} "
                  f"{s['chemoreceptor_drive']:>7.4f} {s['arterial_saturation']:>7.4f} "
                  f"{s['arterial_pH']:>6.3f}")

    output = {
        "solver": "manual_euler_fallback",
        "dt": DT,
        "summary": {
            "PO2_mean": float(np.mean(po2_vals)),
            "PO2_std": float(np.std(po2_vals)),
            "PO2_min": float(np.min(po2_vals)),
            "PO2_max": float(np.max(po2_vals)),
            "PO2_range": float(po2_range),
            "PCO2_mean": float(np.mean(pco2_vals)),
            "HR_mean": float(np.mean(hr_vals)),
            "MAP_mean": float(np.mean(map_vals)),
            "chemo_max": float(np.max(chemo_vals)),
        },
        "time_series": po2_series,
    }
    out_path = os.path.join(EXPERIMENTS_DIR, "exp3_radau_po2_trace.json")
    with open(out_path, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nData saved to {os.path.join('experiments', 'exp3_radau_po2_trace.json')}")

else:
    print(f"Solver failed or returned no data: {result}")
