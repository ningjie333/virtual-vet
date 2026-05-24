"""
Diagnostic: Radau RHS behavior at t=5,10,20,30s
"""
import os, sys, types, numpy as np
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

vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc._cached_inputs.clear()
vc._blood_loss_config = {
    't_onset': 5.0,
    'total_ml': 400.0,
    'duration': 300.0,
    'width': 6.0,
    'k': 35.0,
}

y0 = vc._pack_unified_state()
print(f'State dim: {len(y0)}')

# Init RHS cache
vc._unified_rhs(0.0, y0)
print('RHS warmup OK')

state_map = vc._get_state_map()
map_idx = state_map.get(('heart', 'mean_arterial_pressure'), None)
bv_idx = state_map.get(('heart', 'circulating_volume_ml'), None)
print(f'MAP idx: {map_idx}, BV idx: {bv_idx}')

# Test RHS at several time points
for t_test in [0.0, 4.9, 5.0, 5.1, 10.0, 20.0, 30.0]:
    # fresh vc each time
    vc2 = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc2._cached_inputs.clear()
    vc2._blood_loss_config = {
        't_onset': 5.0, 'total_ml': 400.0, 'duration': 300.0, 'width': 6.0, 'k': 35.0,
    }
    y = vc2._pack_unified_state()
    vc2._unified_rhs(0.0, y)  # warmup
    dydt = vc2._unified_rhs(t_test, y)
    if map_idx is not None and bv_idx is not None:
        # bv is index of blood_volume in y
        print(f't={t_test:5.1f}: MAP={y[map_idx]:.3f}, BV={y[bv_idx]:.1f}, dMAP_dt={dydt[map_idx]:.4f}, dBV_dt={dydt[bv_idx]:.4f}')
    else:
        print(f't={t_test:5.1f}: MAP_idx={map_idx}, BV_idx={bv_idx}')
        # Print first 10 non-zero dydt
        nonzero = [(i, dydt[i]) for i in range(len(dydt)) if abs(dydt[i]) > 1e-6]
        print(f'  nonzero dydt: {nonzero[:10]}')

print()
print('=== Now try actual solve_ivp with tiny window ===')
from scipy.integrate import solve_ivp

vc3 = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc3._cached_inputs.clear()
vc3._blood_loss_config = {
    't_onset': 5.0, 'total_ml': 400.0, 'duration': 300.0, 'width': 6.0, 'k': 35.0,
}
y0 = vc3._pack_unified_state()
vc3._unified_rhs(0.0, y0)  # warmup

t_eval = np.array([0.0, 5.0, 10.0])
sol = solve_ivp(
    lambda t, y: vc3._unified_rhs(t, y),
    [0.0, 10.0],
    y0,
    method='Radau',
    rtol=1e-8, atol=1e-10,
    t_eval=t_eval,
    max_step=0.5,
)
print(f'Success: {sol.success}, msg: {sol.message}')
if sol.success:
    times = sol.t
    maps = sol.y[map_idx]
    bvs = sol.y[bv_idx]
    for i in range(len(times)):
        print(f'  t={times[i]:6.2f}: MAP={maps[i]:.3f}, BV={bvs[i]:.1f}')
    print(f'  MAP_min: {maps.min():.3f} at t={times[maps.argmin()]:.2f}')