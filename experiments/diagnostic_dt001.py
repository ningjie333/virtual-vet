"""
Detailed diagnostic: SV and MAP at dt=0.01
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

print("=== Detailed diagnostic at step_dt=0.01 ===\n")

vc = VirtualCreature(body_weight_kg=20.0)
vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
vc._cached_inputs.clear()
vc.dt = 0.01
n_steps = 6000

# Snapshot at key times: t=0, 5, 25, 60
checkpoints = [0, 50, 250, 500, 2500, 6000]
for step_num in checkpoints:
    # Run steps silently
    for _ in range(step_num - (checkpoints[checkpoints.index(step_num)-1] if checkpoints.index(step_num) > 0 else 0)):
        vc.step()

    t = vc.current_time_s
    hr = vc.heart.heart_rate
    sv = vc.heart.stroke_volume
    co = hr * sv
    bv = vc.heart.circulating_volume_ml
    total_bv = vc.heart.total_BV
    vol_ratio = bv / total_bv
    svr = vc.heart.SVR
    sym = vc.heart.sympathetic
    para = vc.heart.parasympathetic
    raw_map = 60 + (co / 60.0) * svr
    filtered_map = vc.heart.mean_arterial_pressure
    pH = vc.heart.blood.arterial_pH
    K = vc.heart.blood.potassium_mEq_L

    print(f"Step {step_num}, t={t:.1f}s:")
    print(f"  BV={bv:.1f}mL, vol_ratio={vol_ratio:.3f}, base_SV={vc.heart.base_SV:.1f}")
    print(f"  target_SV={vc.heart.base_SV * (0.05 + 0.95 * vol_ratio ** 2.5):.2f} (normal) or {vc.heart.base_SV * 0.3:.2f} (emergency if vol<0.5)")
    print(f"  SV={sv:.4f}, HR={hr:.1f}, CO={co:.1f} mL/min")
    print(f"  SVR={svr:.4f}, sym={sym:.4f}, para={para:.4f}")
    print(f"  raw_MAP=60+(CO/60)*SVR={raw_map:.2f}, filtered_MAP={filtered_map:.2f}")
    print(f"  pH={pH:.4f}, K={K:.4f}")
    print()