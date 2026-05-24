"""
Diagnostic: Why does Sequential Euler RMSE increase as step_dt decreases?

Hypothesis: _respiratory_compensation() calls _vdp.update() 30 times per step,
making dynamics depend on step count (not physical time).

This script verifies:
1. Does changing vc.dt change the number of VDP updates per physical second?
2. What is the dominant dt-dependent component in step()?
"""
import os, sys, types
import numpy as np

EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

sys.modules['parameters'] = types.ModuleType('parameters')
exec(compile(_read_patched(os.path.join(SRC_DIR, 'parameters.py')),
             os.path.join(SRC_DIR, 'parameters.py'), 'exec'),
     sys.modules['parameters'].__dict__)

for _name in ['blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
    'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
    'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
    'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

VirtualCreature = sys.modules['simulation'].VirtualCreature

print("=== Diagnostic: step() dt-dependence root cause ===\n")

# ── Test 1: VDP update count per second ──────────────────────────
print("[1] VDP updates per physical second at different step_dt")
print("    (30 calls per step × steps/second)")

for step_dt in [0.1, 0.05, 0.025, 0.01]:
    vc = VirtualCreature(body_weight_kg=20.0)
    # Reset VDP to known state
    vc.lung._vdp.x = 2.0
    vc.lung._vdp.v = 0.0
    vc.lung._vdp.amplitude = 2.0
    vc.dt = step_dt
    vc._cached_inputs.clear()

    # Record initial VDP state
    x_before = vc.lung._vdp.x
    amp_before = vc.lung._vdp.amplitude

    # Run 1 physical second
    n_steps = int(1.0 / step_dt)
    for _ in range(n_steps):
        vc.step()

    updates_per_sec = 30 * n_steps
    x_after = vc.lung._vdp.x
    amp_after = vc.lung._vdp.amplitude
    print(f"  step_dt={step_dt:.3f}: {n_steps} steps, {updates_per_sec} VDP updates/s")
    print(f"    VDP x: {x_before:.4f} → {x_after:.4f}, amp: {amp_before:.4f} → {amp_after:.4f}")

print()

# ── Test 2: Heart rate vs step_dt at same physical time ──────────
print("[2] HR/MAP at t=60s with different step_dt")
for step_dt in [0.1, 0.05, 0.025, 0.01]:
    vc = VirtualCreature(body_weight_kg=20.0)
    vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
    vc._cached_inputs.clear()
    n_steps = int(60.0 / step_dt)
    for _ in range(n_steps):
        vc.step()
    print(f"  step_dt={step_dt:.3f}: {n_steps} steps → MAP={vc.heart.mean_arterial_pressure:.2f}, HR={vc.heart.heart_rate:.1f}, BV={vc.heart.circulating_volume_ml:.1f}")

print()

# ── Test 3: Isolated VDP convergence (30-step vs 3-step) ─────────
print("[3] VDP convergence: 30 iterations vs 3 iterations (dt=0.01)")
vc1 = VirtualCreature(body_weight_kg=20.0)
vc1._cached_inputs.clear()
vc1.lung._vdp.x = 2.0
vc1.lung._vdp.v = 0.0

vc2 = VirtualCreature(body_weight_kg=20.0)
vc2._cached_inputs.clear()
vc2.lung._vdp.x = 2.0
vc2.lung._vdp.v = 0.0

# Simulate 30 VDP iterations (current behavior)
for _ in range(30):
    vc1.lung._vdp.update(pco2=40.0, po2=95.0, ph=7.40)

# Simulate 3 VDP iterations (proposed fix)
for _ in range(3):
    vc2.lung._vdp.update(pco2=40.0, po2=95.0, ph=7.40)

print(f"  After 30 iterations: x={vc1.lung._vdp.x:.4f}, amp={vc1.lung._vdp.amplitude:.4f}, RR={vc1.lung._vdp.respiratory_rate:.2f}")
print(f"  After 3 iterations:  x={vc2.lung._vdp.x:.4f}, amp={vc2.lung._vdp.amplitude:.4f}, RR={vc2.lung._vdp.respiratory_rate:.2f}")
print(f"  Difference: x={abs(vc1.lung._vdp.x - vc2.lung._vdp.x):.4f}, amp={abs(vc1.lung._vdp.amplitude - vc2.lung._vdp.amplitude):.4f}")

print()

# ── Test 4: Same physical time, same total VDP calls, different step count ──
print("[4] Same physical time (1s), same total VDP updates (30), different step_dt")
for step_dt in [0.1, 0.05, 0.025, 0.01]:
    vc = VirtualCreature(body_weight_kg=20.0)
    vc._cached_inputs.clear()
    vc.dt = step_dt
    n_steps = int(1.0 / step_dt)
    target_vdp_calls = 30  # total VDP updates we want
    calls_per_step = 30   # _respiratory_compensation does 30 calls

    # We need to achieve exactly 30 total VDP calls — but with n_steps:
    # - step_dt=0.1: n_steps=10, VDP calls = 10*30 = 300 (wrong)
    # - step_dt=0.01: n_steps=100, VDP calls = 100*30 = 3000 (wrong)
    # The ratio of VDP calls per physical second:
    vdp_calls_per_sec = (30 / step_dt)  # 30 per step × 1/step_dt steps
    print(f"  step_dt={step_dt:.3f}: n_steps={n_steps}, VDP calls/s = {vdp_calls_per_sec:.0f}")

print()
print("KEY INSIGHT: VDP calls per physical second = 30/step_dt")
print("  step_dt=0.1  → 300 calls/s (over-converged)")
print("  step_dt=0.01 → 3000 calls/s (extremely over-converged)")
print("  → This is the root cause of dt-dependent behavior")