"""
Picard iteration: within each dt, iterate k times (Gauss-Seidel)
Same time point, same dt, k successive updates per step
"""
import os, sys, types, json
import numpy as np
from scipy.integrate import solve_ivp
from scipy.interpolate import interp1d

EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

sys.modules['parameters'] = types.ModuleType('parameters')
exec(compile(_read_patched(os.path.join(SRC_DIR, 'parameters.py')), os.path.join(SRC_DIR, 'parameters.py'), 'exec'), sys.modules['parameters'].__dict__)
for _name in ['blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje', 'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver', 'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic', 'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_read_patched(os.path.join(SRC_DIR, f'{_name}.py')), os.path.join(SRC_DIR, f'{_name}.py'), 'exec'), _mod.__dict__)

VirtualCreature = sys.modules['simulation'].VirtualCreature

WEIGHT_KG = 20.0
T_END = 60.0
SAVE_DT = 0.5
DT = 0.01
K_GRID = [1, 2, 3, 5, 10]

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
    vc._cached_inputs.clear()
    return vc

def pack(vc): return vc._pack_unified_state()
def record(vc, y, t):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return {'t': float(t), 'MAP': float(vc.heart.mean_arterial_pressure), 'HR': float(vc.heart.heart_rate)}

# BDF reference
print('Computing BDF reference...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
sol = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0, method='BDF', rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
t_ref = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_ref = sol.sol(t_ref).T
ref = [record(vc, y_ref[i], t_ref[i]) for i in range(len(t_ref))]
map_ref = np.array([p['MAP'] for p in ref])
print(f'BDF: MAP [{map_ref.min():.2f}, {map_ref.max():.2f}], final={map_ref[-1]:.2f}')

# Picard: within each dt, do k Gauss-Seidel iterations
print('\n=== Picard Iteration (Gauss-Seidel on _unified_rhs) ===')
results = []
for k in K_GRID:
    vc = make_vc()
    y = pack(vc)
    _ = vc._unified_rhs(0.0, y)

    n_steps = int(T_END / DT)
    save_interval = int(SAVE_DT / DT)
    recs = []
    for i in range(n_steps + 1):
        if i % save_interval == 0:
            recs.append(record(vc, y, i * DT))
        # Picard: k Gauss-Seidel iterations at same time point
        for _ in range(k):
            dydt = vc._unified_rhs(i * DT, y)
            y = y + dydt * DT

    t_seq = np.array([p['t'] for p in recs])
    map_seq = np.array([p['MAP'] for p in recs])
    f = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    rmse = np.sqrt(np.mean((map_ref - f(t_ref))**2))
    results.append({'k': k, 'rmse': rmse, 'map_t60': map_seq[-1], 'hr_t60': recs[-1]['HR']})
    print(f'  k={k}: RMSE={rmse:.4f}, MAP={map_seq[-1]:.2f}, HR={recs[-1]["HR"]:.1f}')

out = {'bdf_t': t_ref.tolist(), 'bdf_map': map_ref.tolist(),
       'picard_results': [{'k': r['k'], 'rmse': r['rmse'], 'map_t60': r['map_t60']} for r in results]}
with open('experiments/picard_data.json', 'w') as f:
    json.dump(out, f, indent=2)

print('\n=== Summary ===')
print(f'BDF reference: MAP_final={map_ref[-1]:.2f}')
print(f'{"k":>4}  {"RMSE":>8}  {"delta":>10}  {"MAP_t60":>8}  {"verdict":>15}')
prev = None
for r in results:
    delta = r['rmse'] - prev if prev else 0
    if r['k'] == 1:
        label = 'baseline (Sequential)'
    elif r['rmse'] < 0.5:
        label = '✓ near ref'
    elif r['rmse'] < 5:
        label = '~ moderate'
    elif delta < -1.0:
        label = '↓ improving'
    elif delta > 1.0:
        label = '↑ degrading'
    else:
        label = '~ stable'
    print(f'{r["k"]:>4}  {r["rmse"]:>8.4f}  {delta:>+10.4f}  {r["map_t60"]:>8.2f}  {label}')
    prev = r['rmse']
print('\nConclusion: k=1 is Sequential Euler. Does k>1 converge to reference?')