"""
Direct comparison: BDF vs Euler (explicit) for same _unified_rhs
Tests whether explicit Euler has dt-dependent error growth for this ODE system.
"""
import os, sys, types
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
            'HR': float(vc.heart.heart_rate), 'BV': float(vc.heart.circulating_volume_ml),
            'sym': float(vc.heart.sympathetic), 'para': float(vc.heart.parasympathetic)}

# BDF reference
print('Computing BDF reference...')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)

def rhs(t, y):
    return vc._unified_rhs(t, y)

sol_bdf = solve_ivp(rhs, (0.0, T_END), y0, method='BDF', rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
t_bdf = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_bdf = sol_bdf.sol(t_bdf).T
bdf_records = [unpack_and_record(vc, y_bdf[i], t_bdf[i]) for i in range(len(t_bdf))]
map_bdf = np.array([p['MAP'] for p in bdf_records])
hr_bdf = np.array([p['HR'] for p in bdf_records])
print(f'BDF: MAP=[{map_bdf.min():.2f}, {map_bdf.max():.2f}], HR=[{hr_bdf.min():.1f}, {hr_bdf.max():.1f}]')
print(f'BDF HR at t=30s: {hr_bdf[np.argmin(np.abs(t_bdf-30))]:.1f}')

# Explicit Euler (manual fixed-step)
# The step() path uses explicit Euler-like updates in heart.compute()
# Compare: does explicit Euler on _unified_rhs show the same divergence?
print('\n=== Explicit Euler (fixed-step Euler on _unified_rhs) ===')
DT_GRID = [0.1, 0.05, 0.025, 0.01, 0.005]
results = []
for dt_euler in DT_GRID:
    vc = make_vc()
    y = pack(vc)
    _ = vc._unified_rhs(0.0, y)

    n_steps = int(T_END / dt_euler)
    save_interval = max(1, int(SAVE_DT / dt_euler))

    records = []
    for i in range(n_steps + 1):
        t = i * dt_euler
        if i % save_interval == 0:
            records.append(unpack_and_record(vc, y, t))

        # Explicit Euler: y_{n+1} = y_n + dt * f(t_n, y_n)
        dydt = vc._unified_rhs(t, y)
        y = y + dydt * dt_euler

    t_seq = np.array([p['t'] for p in records])
    map_seq = np.array([p['MAP'] for p in records])
    hr_seq = np.array([p['HR'] for p in records])

    f_seq = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    n_common = min(len(t_bdf), len(t_seq))
    rmse = np.sqrt(np.mean((map_bdf[:n_common] - f_seq(t_bdf[:n_common]))**2))

    hr_t30 = hr_seq[np.argmin(np.abs(t_seq - 30))]
    results.append({'dt': dt_euler, 'rmse': rmse, 'hr_t30': hr_t30, 'hr_t60': hr_seq[-1],
                    'map_t60': map_seq[-1]})
    print(f'  dt={dt_euler:.3f}: RMSE={rmse:.4f}, HR_t30={hr_t30:.1f}, HR_t60={hr_seq[-1]:.1f}')

print('\n=== Convergence Check (explicit Euler on _unified_rhs) ===')
prev = None
for r in results:
    if prev is None:
        print(f'  dt={r["dt"]:.3f}: RMSE={r["rmse"]:.4f}  (base)')
    else:
        delta = r['rmse'] - prev
        ok = '✓' if delta < -0.001 else '✗ INCREASING' if delta > 0.001 else '~'
        print(f'  dt={r["dt"]:.3f}: RMSE={r["rmse"]:.4f}  Δ={delta:+.4f}  {ok}')
    prev = r['rmse']

print('\nConclusion:')
print('  - If explicit Euler RMSE ↑ as dt ↓ → BUG in _unified_rhs (stiff ODE)')
print('  - If explicit Euler RMSE ↓ as dt ↓ → step() has the bug, not _unified_rhs')
print('  - BDF path is the reference (handles stiffness correctly)')