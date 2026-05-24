"""Isolate solve_ivp hang"""
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
from scipy.integrate import solve_ivp
import time

print('Building VC...')
vc = VirtualCreature(body_weight_kg=20.0)
vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
vc._cached_inputs.clear()
y0 = vc._pack_unified_state()
dydt0 = vc._unified_rhs(0.0, y0)
print(f'y0 shape={y0.shape}, dydt0 shape={dydt0.shape}')
print(f'y0[:5] = {y0[:5]}')
print(f'dydt0[:5] = {dydt0[:5]}')

# Try a TINY solve_ivp step first
print('\nTrying solve_ivp Radau on (0→0.1)...')
t0 = time.time()
sol = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, 0.1), y0,
               method='Radau', rtol=1e-6, atol=1e-8,
               max_step=0.05)
t1 = time.time()
print(f'solve_ivp(0→0.1) done in {t1-t0:.3f}s, success={sol.success}, nfev={sol.nfev}')
if sol.success:
    print(f'  y(0.1)[:3] = {sol.y[:,0][:3]}')
    print(f'  y final[:3] = {sol.y[:,-1][:3]}')

print('\nTrying solve_ivp BDF on (0→0.1)...')
t0 = time.time()
sol2 = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, 0.1), y0,
                method='BDF', rtol=1e-6, atol=1e-8,
                max_step=0.05)
t1 = time.time()
print(f'solve_ivp BDF(0→0.1) done in {t1-t0:.3f}s, success={sol2.success}, nfev={sol2.nfev}')
if sol2.success:
    print(f'  y(0.1)[:3] = {sol2.y[:,0][:3]}')

print('\nDone')