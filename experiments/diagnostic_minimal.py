"""Minimal diagnostic - just module load test"""
import os, sys, types
EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

print('Loading parameters...')
sys.modules['parameters'] = types.ModuleType('parameters')
exec(compile(_read_patched(os.path.join(SRC_DIR, 'parameters.py')),
             os.path.join(SRC_DIR, 'parameters.py'), 'exec'),
     sys.modules['parameters'].__dict__)
print('parameters OK')

for _name in ['blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje',
    'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver',
    'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic',
    'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    print(f'Loading {_name}...')
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)
    print(f'  {_name} OK')

print('All modules loaded')
VirtualCreature = sys.modules['simulation'].VirtualCreature
print(f'VirtualCreature = {VirtualCreature}')

import numpy as np
print('Creating VirtualCreature...')
vc = VirtualCreature(body_weight_kg=20.0)
print('VC created')

# Check if step() works (non-ODE path)
import time
t0 = time.time()
for _ in range(10):
    vc.step()
t1 = time.time()
print(f'10 step() calls done in {t1-t0:.3f}s')

# Check ODE eval speed
print('Packing state...')
y0 = vc._pack_unified_state()
print(f'y0 shape={y0.shape}')

# Check RHS eval speed
print('Testing _unified_rhs speed...')
t0 = time.time()
dydt = vc._unified_rhs(0.0, y0)
t1 = time.time()
print(f'_unified_rhs eval in {t1-t0:.3f}s, dydt shape={dydt.shape}')

print('DIAGNOSTIC COMPLETE')