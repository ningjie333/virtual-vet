"""
Diagnostic checks for Sequential Euler bias:
1. Does step() k=1 equal one explicit Euler step on unified RHS?
2. Does different module order give different steady state?
3. Does dt→0 eliminate the bias?
"""
import os, sys, types, json, numpy as np
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
T_END = 60.0
DT = 0.01

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def pack(vc): return vc._pack_unified_state()
def record(vc, y, t):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return {'t': float(t), 'MAP': float(vc.heart.mean_arterial_pressure),
            'HR': float(vc.heart.heart_rate)}

# ============================================================
# CHECK 1: step() k=1 vs explicit Euler on _unified_rhs
# ============================================================
print('=== Check 1: step() k=1 vs explicit Euler on unified RHS ===')
T_SHORT = 2.0  # just 2 seconds to compare initial transient

# Pure Euler on unified RHS (k=1 style)
vc1 = make_vc()
y1 = pack(vc1)
_ = vc1._unified_rhs(0.0, y1)
n = int(T_SHORT / DT)
recs1 = []
for i in range(n + 1):
    if i % 10 == 0:
        recs1.append(record(vc1, y1, i * DT))
    dydt = vc1._unified_rhs(i * DT, y1)
    y1 = y1 + dydt * DT
map1 = np.array([r['MAP'] for r in recs1])
print(f'  Pure Euler (k=1 style): MAP final = {map1[-1]:.4f}')

# Sequential step()
vc2 = make_vc()
vc2.dt = DT
recs2 = []
for i in range(n + 1):
    if i % 10 == 0:
        recs2.append({'t': i*DT, 'MAP': float(vc2.heart.mean_arterial_pressure)})
    vc2.step()
map2 = np.array([r['MAP'] for r in recs2])
print(f'  Sequential step():        MAP final = {map2[-1]:.4f}')
print(f'  → Are they the same? {np.allclose(map1[-5:], map2[-5:], atol=0.1)}')

# ============================================================
# CHECK 2: What does step() internals look like?
# ============================================================
print('\n=== Check 2: step() internals ===')
vc = make_vc()
vc.dt = DT
# Inspect step() order
import inspect
src = inspect.getsource(vc.step)
# Count compute() calls in step
lines = [l.strip() for l in src.split('\n')]
compute_lines = [l for l in lines if 'compute(' in l or '.compute(' in l]
print(f'  step() has {len(compute_lines)} compute() calls')
print('  Module call order (first 10):')
for i, l in enumerate(compute_lines[:10]):
    print(f'    {i+1}. {l}')
if len(compute_lines) > 10:
    print(f'    ... ({len(compute_lines)-10} more)')

# ============================================================
# CHECK 3: Does dt→0 eliminate bias?
# ============================================================
print('\n=== Check 3: dt sensitivity of Sequential step() ===')
DT_GRID = [0.01, 0.005, 0.001, 0.0005]
T_SHORT2 = 30.0

for dt in DT_GRID:
    vc = make_vc()
    vc.dt = dt
    n_steps = int(T_SHORT2 / dt)
    recs = []
    for i in range(n_steps + 1):
        if i % 500 == 0:  # record at ~1.5s intervals
            recs.append({'t': i*dt, 'MAP': float(vc.heart.mean_arterial_pressure)})
        vc.step()
    map_final = recs[-1]['MAP']
    t_final = recs[-1]['t']
    print(f'  dt={dt:.5f}: MAP(t={t_final:.1f}) = {map_final:.3f}')

# ============================================================
# CHECK 4: Pure Euler at dt=0.0005 (to compare)
# ============================================================
print('\n=== Check 4: Pure Euler at dt=0.0005 (30s) ===')
vc = make_vc()
y = pack(vc)
_ = vc._unified_rhs(0.0, y)
dt = 0.0005
n_steps = int(T_SHORT2 / dt)
recs = []
for i in range(n_steps + 1):
    if i % 2000 == 0:
        recs.append({'t': i*dt, 'MAP': record(vc, y, i*dt)['MAP']})
    y = y + vc._unified_rhs(i * dt, y) * dt
print(f'  Pure Euler dt=0.0005: MAP final = {recs[-1]["MAP"]:.3f}')

print('\nDone')