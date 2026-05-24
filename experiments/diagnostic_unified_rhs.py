"""
Quick diagnostic: can _unified_rhs eval at t=0?
"""
import os, sys, types
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
print('Modules loaded OK')

vc = VirtualCreature(body_weight_kg=20.0)
vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
vc._cached_inputs.clear()
print('VirtualCreature created OK')

y0 = vc._pack_unified_state()
print(f'y0 shape: {y0.shape}, dtype: {y0.dtype}')

import time
t0 = time.time()
dydt = vc._unified_rhs(0.0, y0)
t1 = time.time()
print(f'_unified_rhs(0, y0) done in {t1-t0:.3f}s, dydt shape: {dydt.shape}')

# Try a tiny step with solve_ivp
from scipy.integrate import solve_ivp
t0 = time.time()
sol = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, 1.0), y0,
               method='Radau', rtol=1e-6, atol=1e-8, max_step=1.0)
t1 = time.time()
print(f'solve_ivp(0→1s) done in {t1-t0:.1f}s, nfev={sol.nfev}, success={sol.success}')
if sol.success:
    print(f'  y(1s)[:5] = {sol.y[:,0][:5]}')