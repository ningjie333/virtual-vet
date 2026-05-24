"""
Detailed trace: step-by-step, Sequential Euler, no hemorrhage
Track: MAP, HR, SVR, BV, CO at every step for first 20s
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

def make_vc():
    vc = VirtualCreature(body_weight_kg=20.0)
    vc._cached_inputs.clear()
    return vc

DT = 0.01
T_END = 20.0

vc = make_vc()
vc.dt = DT
n_steps = int(T_END / DT)
recs = []
for i in range(n_steps + 1):
    if i % 50 == 0:  # every 0.5s
        recs.append({
            't': i * DT,
            'MAP': float(vc.heart.mean_arterial_pressure),
            'HR': float(vc.heart.heart_rate),
            'SVR': float(vc.heart.SVR),
            'BV': float(vc.heart.circulating_volume_ml),
            'CO': float(vc.heart.heart_rate * vc.heart.stroke_volume_ml),
            'SV': float(vc.heart.stroke_volume_ml),
            'symp': float(getattr(vc.heart, 'sympathetic', -1)),
        })
    vc.step()

print('t[s]  MAP    HR    SVR   BV    CO    SV    symp')
for r in recs:
    print(f'{r["t"]:5.2f} {r["MAP"]:6.2f} {r["HR"]:5.1f} {r["SVR"]:5.3f} {r["BV"]:6.1f} {r["CO"]:6.1f} {r["SV"]:5.2f} {r["symp"]:5.3f}')

# Also run pure Euler for comparison
print('\n=== Pure Euler (same conditions) ===')
vc2 = make_vc()
y = vc2._pack_unified_state()
_ = vc2._unified_rhs(0.0, y)
recs2 = []
for i in range(n_steps + 1):
    if i % 50 == 0:
        vc2._cached_inputs.clear()
        vc2._unpack_unified_state(y)
        recs2.append({
            't': i * DT,
            'MAP': float(vc2.heart.mean_arterial_pressure),
            'HR': float(vc2.heart.heart_rate),
            'SVR': float(vc2.heart.SVR),
        })
    y = y + vc2._unified_rhs(i * DT, y) * DT

print('t[s]  MAP    HR    SVR')
for r in recs2:
    print(f'{r["t"]:5.2f} {r["MAP"]:6.2f} {r["HR"]:5.1f} {r["SVR"]:5.3f}')