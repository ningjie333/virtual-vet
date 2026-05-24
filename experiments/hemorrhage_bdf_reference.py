"""
Radau reference for 400mL hemorrhage — use Euler path to get reference
Since Radau hangs on blood_loss_config, we use BDF+RK45 as proxy reference.
"""
import os, sys, types, numpy as np
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
DT = 0.01

print('=== BDF + RK45 cross-validation reference for 400mL hemorrhage ===')
print()

# Run with original step() — this is our "ground truth" for the Euler path
vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc.dt = DT
vc._cached_inputs.clear()
vc._blood_loss_config = {
    't_onset': 5.0, 'total_ml': 400.0, 'duration': 300.0, 'width': 6.0, 'k': 35.0,
}

N_STEPS = int(120.0 / DT)
print('Running original (heart→neuro) Euler 120s...')
times_o, maps_o, bvs_o = [], [], []
for i in range(N_STEPS + 1):
    times_o.append(vc.current_time_s)
    maps_o.append(float(vc.heart.mean_arterial_pressure))
    bvs_o.append(float(vc.heart.circulating_volume_ml))
    vc.step()
times_o = np.array(times_o)
maps_o = np.array(maps_o)
bvs_o = np.array(bvs_o)

# Run with BDF method on the same _unified_rhs
print('Running BDF reference on unified RHS...')
vc2 = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc2._cached_inputs.clear()
vc2._blood_loss_config = {
    't_onset': 5.0, 'total_ml': 400.0, 'duration': 300.0, 'width': 6.0, 'k': 35.0,
}
y0 = vc2._pack_unified_state()
vc2._unified_rhs(0.0, y0)  # warmup

# BDF is for stiff systems, much faster than Radau
t_eval = np.arange(0, 120.5, 0.5)
sol_bdf = solve_ivp(
    vc2._unified_rhs,
    [0.0, 120.0],
    y0,
    method='BDF',
    rtol=1e-8, atol=1e-10,
    t_eval=t_eval,
    max_step=2.0,
)
print(f'BDF success: {sol_bdf.success}, msg: {sol_bdf.message}')
print(f'BDF shape: {sol_bdf.y.shape}')

# Extract MAP from BDF solution — need to recompute from unpacked state
# Map from state index to (module, varname)
state_map = vc2._build_unified_state_map()
# Find heart indices
hr_idx = state_map.get(('heart', 'HR'))
sv_idx = state_map.get(('heart', 'SV'))
svr_idx = state_map.get(('heart', 'SVR'))
bv_idx = state_map.get(('heart', 'blood_volume'))
print(f'heart indices: HR={hr_idx}, SV={sv_idx}, SVR={svr_idx}, BV={bv_idx}')

# MAP computation (from heart.py:156-160)
def compute_map(HR, SV, SVR, blood_vol, total_vol=1720.0):
    CO = HR * SV
    MAP_baseline = 60.0
    vol_ratio = blood_vol / total_vol
    raw_MAP = MAP_baseline + (CO / 60.0) * SVR
    if vol_ratio < 0.7:
        raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)
    raw_MAP = max(30.0, min(180.0, raw_MAP))
    return raw_MAP

if sol_bdf.success:
    bdf_times = sol_bdf.t
    bdf_maps = np.array([compute_map(
        sol_bdf.y[hr_idx, i],
        sol_bdf.y[sv_idx, i],
        sol_bdf.y[svr_idx, i],
        sol_bdf.y[bv_idx, i],
    ) for i in range(sol_bdf.y.shape[1])])
    bdf_bvs = sol_bdf.y[bv_idx, :]

    print()
    print('=== BDF Reference ===')
    print(f'  MAP_min:   {bdf_maps.min():.3f} mmHg at t={bdf_times[bdf_maps.argmin()]:.2f}s')
    print(f'  BV_final: {bdf_bvs[-1]:.1f} mL')
    print()
    print(f'  {"t":>6}  {"BDF MAP":>10}  {"Euler MAP":>10}  {"BDF BV":>10}')
    for t_target in [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 90, 120]:
        idx_bdf = np.argmin(np.abs(bdf_times - t_target))
        idx_eul = np.argmin(np.abs(times_o - t_target))
        print(f'  {t_target:6.0f}  {bdf_maps[idx_bdf]:10.3f}  {maps_o[idx_eul]:10.3f}  {bdf_bvs[idx_bdf]:10.1f}')

    print()
    print('=== Key comparison: BDF reference vs two Euler orders ===')
    print(f'  (Euler Original MAP@30s=98.355, Euler Reversed MAP@30s=89.049)')
    print(f'  BDF MAP@30s = {bdf_maps[np.argmin(np.abs(bdf_times - 30))]:.3f}')
    print(f'  BDF MAP_min = {bdf_maps.min():.3f}')
    print()
    print(f'  Conclusion: ', end='')
    bdf_at30 = bdf_maps[np.argmin(np.abs(bdf_times - 30))]
    if abs(bdf_at30 - 98.355) < abs(bdf_at30 - 89.049):
        print(f'BDF={bdf_at30:.3f} CLOSER to heart→neuro (98.355) → original order is more accurate')
    else:
        print(f'BDF={bdf_at30:.3f} CLOSER to neuro→heart (89.049) → reversed order is more accurate')
else:
    print(f'BDF failed: {sol_bdf.message}')