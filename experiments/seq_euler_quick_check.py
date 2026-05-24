"""
Quick convergence check: Sequential Euler (step) vs BDF reference
Tests step_dt = [0.1, 0.05, 0.025, 0.01] — should show RMSE decreasing with dt
"""
import os, sys, types, json
import numpy as np

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
from scipy.interpolate import interp1d

WEIGHT_KG = 20.0
T_END = 60.0
DT_GRID = [0.1, 0.05, 0.025, 0.01]
SAVE_DT = 0.5  # Record every 0.5s

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
            'HR': float(vc.heart.heart_rate), 'BV': float(vc.heart.circulating_volume_ml)}

# BDF reference (single run)
print('Computing BDF reference...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)

def rhs(t, y):
    return vc._unified_rhs(t, y)

sol = solve_ivp(rhs, (0.0, T_END), y0, method='BDF', rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
t_bdf = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_bdf = sol.sol(t_bdf).T
bdf_records = [unpack_and_record(vc, y_bdf[i], t_bdf[i]) for i in range(len(t_bdf))]
map_bdf = np.array([p['MAP'] for p in bdf_records])
print(f'BDF: MAP range [{map_bdf.min():.2f}, {map_bdf.max():.2f}], final MAP={map_bdf[-1]:.2f}')

# Sequential Euler via step()
print('\nSequential Euler (step) dt study:')
results = []
for step_dt in DT_GRID:
    vc = make_vc()
    vc.dt = step_dt  # Set dt before calling step()
    n_steps = int(T_END / step_dt)
    save_interval = int(SAVE_DT / step_dt)

    records = []
    for i in range(n_steps + 1):
        t = i * step_dt
        if i % save_interval == 0:
            records.append({'t': float(t), 'MAP': float(vc.heart.mean_arterial_pressure),
                           'HR': float(vc.heart.heart_rate)})
        vc.step()

    t_seq = np.array([p['t'] for p in records])
    map_seq = np.array([p['MAP'] for p in records])

    # Interpolate to BDF time points
    f_seq = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    n_common = min(len(t_bdf), len(t_seq))
    common_t = t_bdf[:n_common]
    rmse = np.sqrt(np.mean((map_bdf[:n_common] - f_seq(common_t))**2))

    results.append({'step_dt': step_dt, 'rmse_MAP': rmse,
                    'final_MAP': map_seq[-1] if len(map_seq) > 0 else np.nan,
                    'n_steps': n_steps})
    print(f'  dt={step_dt:.3f}: RMSE={rmse:.4f}, final_MAP={results[-1]["final_MAP"]:.2f}, steps={n_steps}')

print('\n=== Convergence Check ===')
print(f'  {"dt":>6}  {"RMSE":>8}  {"monotonic?":>10}')
prev_rmse = None
for r in results:
    delta_str = ''
    if prev_rmse is not None:
        if r['rmse_MAP'] < prev_rmse:
            delta_str = '✓ decreasing'
        elif r['rmse_MAP'] == prev_rmse:
            delta_str = '= same'
        else:
            delta_str = '✗ INCREASING'
    print(f'  {r["step_dt"]:>6.3f}  {r["rmse_MAP"]:>8.4f}  {delta_str:>10}')
    prev_rmse = r['rmse_MAP']

# Check: is this Pure Euler (solve_ivp with Euler) or Sequential Euler (step)?
print('\nNote: This tests step() path (Sequential Euler), NOT solve_ivp path.')
print('step() uses Euler with module-by-module FactorCommand coupling.')
print('If RMSE increases as dt decreases → bug in step() path.')