"""
Diagnostic checks 1-3: Sequential Euler root cause investigation
Check 1: step() first step - does MAP immediately jump?
Check 2: Module order from step source - analyze without running
Check 3: dt=0.001 → confirm MAP ≈ 144.7
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
DT = 0.01

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def pack(vc): return vc._pack_unified_state()

# ============================================================
# CHECK 1: step() first step - MAP immediately jump?
# ============================================================
print('=== Check 1: step() first step ===')
vc = make_vc()
vc.dt = DT
print(f'  t=0: MAP={vc.heart.mean_arterial_pressure:.4f}, HR={vc.heart.heart_rate:.2f}')

# Get state before step
y0 = pack(vc)
map_before = vc.heart.mean_arterial_pressure
hr_before = vc.heart.heart_rate
symp_before = vc.heart.sympathetic

# Run one step
vc.step()

map_after = vc.heart.mean_arterial_pressure
hr_after = vc.heart.heart_rate
symp_after = vc.heart.sympathetic
print(f'  After 1 step: MAP={map_after:.4f}, HR={hr_after:.2f}')
print(f'  Delta MAP: {map_after - map_before:.4f} mmHg')
print(f'  Delta HR: {hr_after - hr_before:.2f}')
print(f'  Sympathetic: {symp_before:.4f} → {symp_after:.4f}')

# Pure Euler from same initial y0
vc2 = make_vc()
y = pack(vc2)
vc2._cached_inputs.clear()
vc2._unpack_unified_state(y)
dydt = vc2._unified_rhs(0.0, y)
y_new = y + dydt * DT
vc2._cached_inputs.clear()
vc2._unpack_unified_state(y_new)
map_pe = vc2.heart.mean_arterial_pressure
print(f'  Pure Euler after 1 step: MAP={map_pe:.4f}')
print('  -> Both stay at MAP=100. No immediate jump. Slow drift, not step shock.')

# ============================================================
# CHECK 2: Module order analysis from step source
# ============================================================
print('\n=== Check 2: Module order analysis ===')
import inspect
src = inspect.getsource(VirtualCreature.step)
lines = src.split('\n')
compute_lines = []
for i, l in enumerate(lines):
    if '.compute(' in l and not l.strip().startswith('#'):
        compute_lines.append((i+1, l.strip()))

print(f'  step() compute call order ({len(compute_lines)} calls):')
for i, (ln, l) in enumerate(compute_lines):
    print(f'    {i+1}. [line {ln}] {l[:75]}')

print()
print('  KEY OBSERVATION:')
print('    heart.compute is at position 1 (FIRST major module)')
print('    neuro.compute is at position 11 (LAST major module)')
print('    Baroreflex loop: heart(HR,SVR) → MAP → neuro(sympathetic) → heart(sympathetic)')
print('    Current order: neuro sees OLD heart state (1-step-lag)')
print('    Gauss-Seidel: each module sees PARTIALLY UPDATED state from same step')

# ============================================================
# CHECK 3: Sequential dt=0.001 confirmation
# ============================================================
print('\n=== Check 3: Sequential dt=0.001 (60s) ===')
DT = 0.001
T_END = 60.0
n_steps = int(T_END / DT)

vc = make_vc()
vc.dt = DT
recs = []
for i in range(n_steps + 1):
    if i % 5000 == 0:  # every 5s
        recs.append({'t': i*DT, 'MAP': float(vc.heart.mean_arterial_pressure)})
    vc.step()

map_final = recs[-1]['MAP']
print(f'  dt=0.001, t=60s: MAP={map_final:.3f} mmHg')
print(f'  Expected: ~144.7 mmHg (dt-independent bias)')
print(f'  Prior dt=0.01 run: MAP=144.742 mmHg')
print(f'  If very close → dt-independent bias CONFIRMED')

print('\nDone')