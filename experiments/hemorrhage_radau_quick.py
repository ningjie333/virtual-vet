"""
Radau reference for 400mL hemorrhage — quick diagnostic
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

# Pack state
y0 = vc._pack_unified_state()
print(f'State dim: {len(y0)}')

# Init RHS
print('Warming up RHS...')
vc._unified_rhs(0.0, y0)
print('RHS warmup done')

# Quick 30s test with sparse save
print('Solving 30s Radau...')
t_eval = np.array([0, 10, 20, 30])
sol = solve_ivp(
    vc._unified_rhs,
    [0.0, 30.0],
    y0,
    method='Radau',
    rtol=1e-8, atol=1e-10,
    t_eval=t_eval,
    max_step=1.0,
)
print(f'Success: {sol.success}, message: {sol.message}')
print(f'Shape: {sol.y.shape}')

# Get state map
state_map = vc._get_state_map()
map_idx = state_map.get(('heart', 'mean_arterial_pressure'), None)
bv_idx = state_map.get(('heart', 'circulating_volume_ml'), None)
print(f'MAP idx: {map_idx}, BV idx: {bv_idx}')

if sol.success and map_idx is not None:
    times = sol.t
    maps = sol.y[map_idx]
    bvs = sol.y[bv_idx]
    print()
    print('=== Radau 400mL Hemorrhage (30s) ===')
    print(f'{"t":>6}  {"MAP":>10}  {"BV":>10}')
    for i in range(len(times)):
        print(f'{times[i]:6.1f}  {maps[i]:10.3f}  {bvs[i]:10.1f}')

    print()
    print(f'MAP_min in first 30s: {maps.min():.3f} at t={times[maps.argmin()]:.1f}s')
else:
    print(f'Failed: {sol.message}')