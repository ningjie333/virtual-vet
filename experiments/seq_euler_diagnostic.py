"""
Diagnostic: compare HR/MAP evolution between step() path at different dt
Use identical random seed for reproducibility
"""
import os, sys, types, json, random
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
DT_GRID = [0.1, 0.05, 0.025, 0.01]

def make_vc(seed=42):
    random.seed(seed)
    np.random.seed(seed)
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
        'sym': float(vc.heart.sympathetic),
        'para': float(vc.heart.parasympathetic),
        'SVR': float(vc.heart.SVR),
        'SV': float(vc.heart.stroke_volume),
        'CO': float(vc.heart.cardiac_output),
    }

# BDF reference
print('Computing BDF reference...')
vc0 = make_vc(seed=42)
y0 = pack(vc0)
_ = vc0._unified_rhs(0.0, y0)

def rhs(t, y):
    return vc0._unified_rhs(t, y)

sol = solve_ivp(rhs, (0.0, T_END), y0, method='BDF', rtol=1e-6, atol=1e-8, max_step=0.5, dense_output=True)
t_bdf = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
y_bdf = sol.sol(t_bdf).T
bdf_records = [unpack_and_record(vc0, y_bdf[i], t_bdf[i]) for i in range(len(t_bdf))]
map_bdf = np.array([p['MAP'] for p in bdf_records])
hr_bdf = np.array([p['HR'] for p in bdf_records])
print(f'BDF MAP: [{map_bdf.min():.2f}, {map_bdf.max():.2f}], HR: [{hr_bdf.min():.1f}, {hr_bdf.max():.1f}]')

# Sequential Euler via step()
print('\nSequential Euler dt study:')
results = {}
for step_dt in DT_GRID:
    random.seed(42)
    np.random.seed(42)
    vc = make_vc(seed=42)
    vc.dt = step_dt
    n_steps = int(T_END / step_dt)
    save_interval = int(SAVE_DT / step_dt)

    records = []
    for i in range(n_steps + 1):
        t = i * step_dt
        if i % save_interval == 0:
            records.append({
                't': float(t),
                'MAP': float(vc.heart.mean_arterial_pressure),
                'HR': float(vc.heart.heart_rate),
                'BV': float(vc.heart.circulating_volume_ml),
                'sym': float(vc.heart.sympathetic),
                'para': float(vc.heart.parasympathetic),
                'SVR': float(vc.heart.SVR),
                'SV': float(vc.heart.stroke_volume),
            })
        vc.step()

    t_seq = np.array([p['t'] for p in records])
    map_seq = np.array([p['MAP'] for p in records])

    f_seq = interp1d(t_seq, map_seq, kind='linear', fill_value='extrapolate', bounds_error=False)
    n_common = min(len(t_bdf), len(t_seq))
    common_t = t_bdf[:n_common]
    rmse = np.sqrt(np.mean((map_bdf[:n_common] - f_seq(common_t))**2))

    results[step_dt] = {
        'records': records,
        'rmse': rmse,
        'map_seq': map_seq,
        't_seq': t_seq,
    }
    print(f'  dt={step_dt:.3f}: RMSE={rmse:.4f}, final_MAP={map_seq[-1]:.2f}, steps={n_steps}')

# Check convergence
print('\n=== Convergence Check ===')
prev = None
for dt in DT_GRID:
    r = results[dt]
    if prev is None:
        print(f'  dt={dt:.3f}: RMSE={r["rmse"]:.4f}  (base)')
    else:
        delta = r['rmse'] - prev
        direction = '✓' if delta < 0 else '✗ INCREASING'
        print(f'  dt={dt:.3f}: RMSE={r["rmse"]:.4f}  Δ={delta:+.4f}  {direction}')
    prev = r['rmse']

# Print HR evolution at key times
print('\n=== HR at key times ===')
key_times = {5.0: 't=5s (hemorrhage onset)', 25.0: 't=25s (peak compensation)',
             30.0: 't=30s (divergence point)', 60.0: 't=60s (end)'}

# BDF HR at key times
print('BDF reference HR:')
for target_t, label in key_times.items():
    idx = np.argmin(np.abs(t_bdf - target_t))
    print(f'  {label}: HR={hr_bdf[idx]:.1f}, MAP={map_bdf[idx]:.1f}')

for dt in DT_GRID:
    r = results[dt]
    t_seq = r['t_seq']
    recs = r['records']
    print(f'\ndt={dt} HR:')
    for target_t, label in key_times.items():
        idx = np.argmin(np.abs(t_seq - target_t))
        rec = recs[idx]
        print(f'  {label}: HR={rec["HR"]:.1f}, MAP={rec["MAP"]:.1f}, sym={rec["sym"]:.3f}, para={rec["para"]:.3f}')

print('\n=== Sym/Para at t=60s ===')
print(f'BDF: sym={vc0.heart.sympathetic:.4f}, para={vc0.heart.parasympathetic:.4f}')
for dt in DT_GRID:
    r = results[dt]
    rec = r['records'][-1]
    print(f'dt={dt}: sym={rec["sym"]:.4f}, para={rec["para"]:.4f}')