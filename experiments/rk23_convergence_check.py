"""
Radau vs Euler convergence: does RK23 with max_step=dt show RMSE ∝ dt?
Tests solve_ivp with method='RK23' at various max_step values (Pure Euler path)
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
SAVE_DT = 0.5
DT_GRID = [0.1, 0.05, 0.025, 0.01, 0.005, 0.002, 0.001]  # max_step values

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
    return {
        't': float(t),
        'MAP': float(vc.heart.mean_arterial_pressure),
        'HR': float(vc.heart.heart_rate),
        'BV': float(vc.heart.circulating_volume_ml),
    }

# BDF reference
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
hr_bdf = np.array([p['HR'] for p in bdf_records])
print(f'BDF: MAP range [{map_bdf.min():.2f}, {map_bdf.max():.2f}], HR range [{hr_bdf.min():.1f}, {hr_bdf.max():.1f}]')
print(f'BDF HR: t=30s={hr_bdf[np.argmin(np.abs(t_bdf-30))]:.1f}, t=60s={hr_bdf[-1]:.1f}')

# Pure Euler (RK23): does RMSE ∝ dt?
print('\nPure Euler (RK23) dt convergence study:')
results = []
for max_step in DT_GRID:
    vc = make_vc()
    y0 = pack(vc)
    _ = vc._unified_rhs(0.0, y0)

    sol_euler = solve_ivp(rhs, (0.0, T_END), y0, method='RK23',
                          rtol=1e-3, atol=1e-5, max_step=max_step, dense_output=True)

    t_rec = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
    y_rec = sol_euler.sol(t_rec).T
    seq_records = [unpack_and_record(vc, y_rec[i], t_rec[i]) for i in range(len(t_rec))]

    t_seq = np.array([p['t'] for p in seq_records])
    map_seq = np.array([p['MAP'] for p in seq_records])
    hr_seq = np.array([p['HR'] for p in seq_records])

    f_seq = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    n_common = min(len(t_bdf), len(t_seq))
    rmse = np.sqrt(np.mean((map_bdf[:n_common] - f_seq(t_bdf[:n_common]))**2))

    results.append({'max_step': max_step, 'rmse_MAP': rmse,
                    'hr_t30': hr_seq[np.argmin(np.abs(t_seq-30))],
                    'hr_t60': hr_seq[-1],
                    'map_t60': map_seq[-1]})
    print(f'  max_step={max_step:.3f}: RMSE={rmse:.4f}, HR_t30={hr_seq[np.argmin(np.abs(t_seq-30))]:.1f}, HR_t60={hr_seq[-1]:.1f}')

print('\n=== Convergence Check (RK23) ===')
print(f'  {"max_step":>8}  {"RMSE":>8}  {"ΔRMSE":>10}  {"converging?":>12}')
prev = None
for r in results:
    if prev is None:
        print(f'  {r["max_step"]:>8.3f}  {r["rmse_MAP"]:>8.4f}  {"(base)":>10}')
    else:
        delta = r['rmse_MAP'] - prev
        ok = '✓ YES' if delta < -0.001 else ('~ stable' if abs(delta) < 0.01 else '✗ NO')
        print(f'  {r["max_step"]:>8.3f}  {r["rmse_MAP"]:>8.4f}  {delta:>+10.4f}  {ok:>12}')
    prev = r['rmse_MAP']