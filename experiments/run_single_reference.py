"""Single-solver reference test - Radau only, ultra-relaxed tolerances"""
import os, sys, types, json
import numpy as np
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
T_END = 10.0
SAVE_DT = 0.5

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
    vc._cached_inputs.clear()
    return vc

def pack(vc):
    return vc._pack_unified_state()

def unpack_and_record(vc, y, t):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return {'t': float(t), 'MAP': float(vc.heart.mean_arterial_pressure),
            'HR': float(vc.heart.heart_rate)}

# Radau ultra-relaxed
print('Radau IIA (rtol=1e-4, atol=1e-6, max_step=2.0) on 0→10s...')
import time
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
t0 = time.time()
sol = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0,
                method='Radau', rtol=1e-4, atol=1e-6,
                max_step=2.0, dense_output=True)
t1 = time.time()
print(f'Radau done in {t1-t0:.1f}s, nfev={sol.nfev}, success={sol.success}')

t_common = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_interp = sol.sol(t_common).T
recs = [unpack_and_record(vc, y_interp[i], t_common[i]) for i in range(len(t_common))]
map_vals = np.array([p['MAP'] for p in recs])
print(f'MAP [{map_vals.min():.4f}, {map_vals.max():.4f}], final={map_vals[-1]:.4f}')

out = {'t': t_common.tolist(), 'map': map_vals.tolist(), 'nfev': int(sol.nfev)}
with open('experiments/radau_reference_10s.json', 'w') as f:
    json.dump(out, f, indent=2)
print('Saved: experiments/radau_reference_10s.json')