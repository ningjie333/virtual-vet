"""Reference solution cross-validation — quick version (T_END=10s)"""
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

print('Computing reference solutions with three solvers (T_END=10s)...')

# Radau IIA
print('  [1/3] Radau IIA (rtol=1e-8, atol=1e-10, max_step=1.0)...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
sol_radau = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0,
                      method='Radau', rtol=1e-8, atol=1e-10,
                      max_step=1.0, dense_output=True)
t_common = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_radau = sol_radau.sol(t_common).T
recs_radau = [unpack_and_record(vc, y_radau[i], t_common[i]) for i in range(len(t_common))]
map_radau = np.array([p['MAP'] for p in recs_radau])
print(f'    Radau: MAP [{map_radau.min():.4f}, {map_radau.max():.4f}], final={map_radau[-1]:.4f}, nfev={sol_radau.nfev}')

# BDF
print('  [2/3] BDF (rtol=1e-6, atol=1e-8, max_step=1.0)...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
sol_bdf = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0,
                    method='BDF', rtol=1e-6, atol=1e-8,
                    max_step=1.0, dense_output=True)
y_bdf = sol_bdf.sol(t_common).T
recs_bdf = [unpack_and_record(vc, y_bdf[i], t_common[i]) for i in range(len(t_common))]
map_bdf = np.array([p['MAP'] for p in recs_bdf])
print(f'    BDF:   MAP [{map_bdf.min():.4f}, {map_bdf.max():.4f}], final={map_bdf[-1]:.4f}, nfev={sol_bdf.nfev}')

# Radau tighter
print('  [3/3] Radau IIA tight (rtol=1e-10, atol=1e-12, max_step=0.5)...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
sol_radau_tight = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0,
                            method='Radau', rtol=1e-10, atol=1e-12,
                            max_step=0.5, dense_output=True)
y_radau_tight = sol_radau_tight.sol(t_common).T
recs_radau_tight = [unpack_and_record(vc, y_radau_tight[i], t_common[i]) for i in range(len(t_common))]
map_radau_tight = np.array([p['MAP'] for p in recs_radau_tight])
print(f'    Radau_tight: MAP [{map_radau_tight.min():.4f}, {map_radau_tight.max():.4f}], final={map_radau_tight[-1]:.4f}, nfev={sol_radau_tight.nfev}')

# Max differences
max_diff_radau_bdf = np.max(np.abs(map_radau - map_bdf))
max_diff_radau_tight = np.max(np.abs(map_radau - map_radau_tight))
max_diff_bdf_tight = np.max(np.abs(map_bdf - map_radau_tight))
max_diff_all = max(max_diff_radau_bdf, max_diff_radau_tight, max_diff_bdf_tight)

print(f'\n=== Reference Cross-Validation (T_END=10s) ===')
print(f'{"Pair":<25}  {"Max Diff (mmHg)":>15}')
print(f'{"Radau vs BDF":<25}  {max_diff_radau_bdf:>15.6f}')
print(f'{"Radau vs Radau_tight":<25}  {max_diff_radau_tight:>15.6f}')
print(f'{"BDF vs Radau_tight":<25}  {max_diff_bdf_tight:>15.6f}')
print(f'{"MAX DIFF (any pair)":<25}  {max_diff_all:>15.6f}')

if max_diff_all < 0.01:
    verdict = 'PASS — reference credible (max_diff < 0.01 mmHg)'
else:
    verdict = f'FAIL — max_diff = {max_diff_all:.4f} mmHg >= 0.01 mmHg'
print(f'\nVerdict: {verdict}')

out = {
    't': t_common.tolist(),
    'radau': {'map': map_radau.tolist()},
    'bdf':   {'map': map_bdf.tolist()},
    'radau_tight': {'map': map_radau_tight.tolist()},
    'max_diff_radau_bdf': max_diff_radau_bdf,
    'max_diff_radau_tight': max_diff_radau_tight,
    'max_diff_bdf_tight': max_diff_bdf_tight,
    'max_diff_all': max_diff_all,
    'verdict': verdict,
}
with open('experiments/reference_validation.json', 'w') as f:
    json.dump(out, f, indent=2)
print('\nSaved: experiments/reference_validation.json')