"""
BDF reference for 400mL hemorrhage — no warmup needed, just pure Euler comparison
Use run_unified_ivp with dt_save to get sparse results quickly
"""
import os, sys, types, numpy as np
from scipy.integrate import solve_ivp
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

WEIGHT_KG = 20.0

# Use run_unified_ivp which has its own warmup handling
# and sparse dt_save for quick results
print('Building VC...')
vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc._cached_inputs.clear()
vc._blood_loss_config = {
    't_onset': 5.0,
    'total_ml': 400.0,
    'duration': 300.0,
    'width': 6.0,
    'k': 35.0,
}

# Pack state manually
y0 = vc._pack_unified_state()
print(f'State dim: {len(y0)}')
n = len(y0)

# Map indices
state_map = vc._build_unified_state_map()
hr_idx = state_map.get(('heart', 'HR'))
sv_idx = state_map.get(('heart', 'SV'))
svr_idx = state_map.get(('heart', 'SVR'))
bv_idx = state_map.get(('heart', 'blood_volume'))
print(f'Heart indices: HR={hr_idx}, SV={sv_idx}, SVR={svr_idx}, BV={bv_idx}')

# MAP formula from heart.py:156-160
def calc_map(HR, SV, SVR, BV, total_vol=1720.0):
    CO = HR * SV
    MAP_baseline = 60.0
    vol_ratio = BV / total_vol
    raw_MAP = MAP_baseline + (CO / 60.0) * SVR
    if vol_ratio < 0.7:
        raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)
    return max(30.0, min(180.0, raw_MAP))

# Quick test: single RHS call at t=10s with fresh VC
print()
print('Single RHS call test...')
vc3 = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc3._cached_inputs.clear()
vc3._blood_loss_config = {
    't_onset': 5.0, 'total_ml': 400.0, 'duration': 300.0, 'width': 6.0, 'k': 35.0,
}
y3 = vc3._pack_unified_state()
# Init state
dydt3 = vc3._unified_rhs(0.0, y3)
print(f'  t=0: HR={y3[hr_idx]:.1f}, SV={y3[sv_idx]:.1f}, SVR={y3[svr_idx]:.3f}, BV={y3[bv_idx]:.1f}')
print(f'  t=0: MAP_init={calc_map(y3[hr_idx], y3[sv_idx], y3[svr_idx], y3[bv_idx]):.3f}')

# Now advance to t=10 by stepping Euler (no solve_ivp needed for reference)
print()
print('=== Euler step reference (step() path) ===')
vc_e = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc_e.dt = 0.01
vc_e._cached_inputs.clear()
vc_e._blood_loss_config = {
    't_onset': 5.0, 'total_ml': 400.0, 'duration': 300.0, 'width': 6.0, 'k': 35.0,
}
N = int(30.0 / 0.01)  # just 30s
for i in range(N + 1):
    if i % 500 == 0:  # every 5s
        t = vc_e.current_time_s
        BV = vc_e.heart.circulating_volume_ml
        HR = vc_e.heart.heart_rate
        SV = vc_e.heart.stroke_volume
        SVR = vc_e.heart.SVR
        MAP = calc_map(HR, SV, SVR, BV)
        print(f'  t={t:6.1f}: HR={HR:.1f}, SV={SV:.2f}, SVR={SVR:.3f}, BV={BV:.1f}, MAP={MAP:.3f}')
    vc_e.step()

print(f'  After 30s: MAP={vc_e.heart.mean_arterial_pressure:.3f} (direct), BV={vc_e.heart.circulating_volume_ml:.1f}')