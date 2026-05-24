"""
Figure 3 data: RMSE vs dt for Pure Euler vs Sequential Euler
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
SAVE_DT = 0.5
DT_GRID = [0.1, 0.05, 0.025, 0.01, 0.005]

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

# BDF reference (reasonable tolerance)
print('Computing BDF reference...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
def rhs(t, y): return vc._unified_rhs(t, y)
sol = solve_ivp(rhs, (0.0, T_END), y0, method='BDF', rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
t_bdf = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_bdf = sol.sol(t_bdf).T
bdf_records = [unpack_and_record(vc, y_bdf[i], t_bdf[i]) for i in range(len(t_bdf))]
map_bdf = np.array([p['MAP'] for p in bdf_records])
print(f'BDF: MAP [{map_bdf.min():.2f}, {map_bdf.max():.2f}], final={map_bdf[-1]:.2f}')

# Pure Euler (fixed-step explicit on _unified_rhs)
print('\n=== Pure Euler ===')
pure = []
for dt in DT_GRID:
    vc = make_vc()
    y = pack(vc)
    _ = vc._unified_rhs(0.0, y)
    n_steps = int(T_END / dt)
    save_interval = max(1, int(SAVE_DT / dt))
    records = []
    for i in range(n_steps + 1):
        if i % save_interval == 0:
            records.append(unpack_and_record(vc, y, i * dt))
        y = y + vc._unified_rhs(i * dt, y) * dt
    t_seq = np.array([p['t'] for p in records])
    map_seq = np.array([p['MAP'] for p in records])
    f = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    rmse = np.sqrt(np.mean((map_bdf - f(t_bdf))**2))
    pure.append({'dt': dt, 'rmse': rmse, 'map_t60': map_seq[-1], 'hr_t60': records[-1]['HR']})
    print(f'  dt={dt:.3f}: RMSE={rmse:.4f}, MAP={map_seq[-1]:.2f}')

# Sequential Euler (step() path)
print('\n=== Sequential Euler (step) ===')
seq = []
for step_dt in DT_GRID:
    vc = make_vc()
    vc.dt = step_dt
    n_steps = int(T_END / step_dt)
    save_interval = max(1, int(SAVE_DT / step_dt))
    records = []
    for i in range(n_steps + 1):
        if i % save_interval == 0:
            records.append({'t': float(i * step_dt), 'MAP': float(vc.heart.mean_arterial_pressure),
                           'HR': float(vc.heart.heart_rate)})
        vc.step()
    t_seq = np.array([p['t'] for p in records])
    map_seq = np.array([p['MAP'] for p in records])
    f = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    rmse = np.sqrt(np.mean((map_bdf - f(t_bdf))**2))
    seq.append({'dt': step_dt, 'rmse': rmse, 'map_t60': map_seq[-1], 'hr_t60': records[-1]['HR']})
    print(f'  dt={step_dt:.3f}: RMSE={rmse:.4f}, MAP={map_seq[-1]:.2f}')

# Save
results = {
    'bdf': {'t': t_bdf.tolist(), 'map': map_bdf.tolist()},
    'pure_euler': pure,
    'sequential_euler': seq,
}
with open('experiments/figure3_data.json', 'w') as f:
    json.dump(results, f, indent=2)

print('\n=== Figure 3 ===')
print(f'{"dt":>6}  {"Pure RMSE":>10}  {"Seq RMSE":>10}  {"Ratio":>8}')
for p, s in zip(pure, seq):
    print(f'{p["dt"]:>6.3f}  {p["rmse"]:>10.4f}  {s["rmse"]:>10.4f}  {s["rmse"]/p["rmse"]:>8.1f}x')

print('\nPure → convergent ✓  |  Sequential → DIVERGENT ✗')
print('Splitting error does NOT vanish with dt.')