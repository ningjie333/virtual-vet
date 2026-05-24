"""
Radau reference for 400mL hemorrhage — key transient metrics
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

WEIGHT_KG = 20.0

print('Building Radau reference...')
vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc._cached_inputs.clear()
vc._blood_loss_config = {
    't_onset': 5.0,
    'total_ml': 400.0,
    'duration': 300.0,
    'width': 6.0,
    'k': 35.0,
}

print(f'  _blood_loss_config: {vc._blood_loss_config}')
print(f'  initial BV: {vc.heart.circulating_volume_ml}')

# Run Radau
print('  solving (Radau rtol=1e-10, atol=1e-12)...')
try:
    sol = vc.run_unified_ivp(t_end=120.0, dt_save=0.5)
    print(f'  sol success: {sol.success}')
    print(f'  sol.message: {sol.message}')
    print(f'  shape: {sol.y.shape}')
    # Extract MAP at save points
    t_vals = sol.t
    n_steps_save = len(t_vals)
    print(f'  n_save_points: {n_steps_save}')
except Exception as e:
    print(f'  ERROR: {e}')
    import traceback
    traceback.print_exc()

# Manual time-value extraction from sol
# Need to re-extract because run_unified_ivp returns the sol object
vc2 = VirtualCreature(body_weight_kg=WEIGHT_KG)
vc2._cached_inputs.clear()
vc2._blood_loss_config = {
    't_onset': 5.0,
    'total_ml': 400.0,
    'duration': 300.0,
    'width': 6.0,
    'k': 35.0,
}

print()
print('Re-running for time-series extraction...')
sol2 = vc2.run_unified_ivp(t_end=120.0, dt_save=0.5)
t_vals = sol2.t
# Need MAP from sol2.y — which rows correspond to heart?
# We need to re-run to get the full state
# Instead, let's do it properly by extracting the full y and re-computing MAP
from scipy.integrate import solve_ivp

# Get full state at each step
y0 = vc2._pack_unified_state()
print(f'  state dim: {len(y0)}')
print(f'  calling rhs to initialize...')
_ = vc2._unified_rhs(0.0, y0)

# Run with dense output
t_eval = np.arange(0, 120.5, 0.5)
sol3 = solve_ivp(
    vc2._unified_rhs,
    [0.0, 120.0],
    y0,
    method='Radau',
    rtol=1e-10, atol=1e-12,
    t_eval=t_eval,
    dense_output=True,
)
print(f'  Radau solved: {sol3.success}, message: {sol3.message}')
print(f'  shape: {sol3.y.shape}, t: {len(sol3.t)}')

# Extract MAP from full state
# state_map: (module, varname) -> index
state_map = vc2._get_state_map()
# heart MAP is raw MAP (before correction) or mean_arterial_pressure
# We need to unpack and compute MAP
map_idx = state_map.get(('heart', 'mean_arterial_pressure'), None)
print(f'  MAP index: {map_idx}')
bv_idx = state_map.get(('heart', 'circulating_volume_ml'), None)
print(f'  BV index: {bv_idx}')

if map_idx is not None:
    map_vals = sol3.y[map_idx, :]
    bv_vals = sol3.y[bv_idx, :] if bv_idx is not None else None
    times = sol3.t

    def get(t_target):
        idx = np.argmin(np.abs(times - t_target))
        return times[idx], map_vals[idx], bv_vals[idx] if bv_vals is not None else np.nan

    print()
    print('=== Radau Reference: 400mL Hemorrhage ===')
    print()
    print(f'  MAP_min:   {map_vals.min():.3f} mmHg at t={times[map_vals.argmin()]:.2f}s')
    print(f'  BV_final: {bv_vals[-1]:.1f} mL at t={times[-1]:.1f}s' if bv_vals is not None else '')
    print()
    print(f'  {"t[s]":>6}  {"MAP":>10}  {"BV":>10}')
    for t_target in [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 90, 120]:
        t, m, b = get(t_target)
        print(f'  {t_target:6.0f}  {m:10.3f}  {b:10.1f}')

    print()
    print('=== Key comparison: Radau vs two Euler orders ===')
    print(f'  {"":20}  {"Radau":>10}  {"heart→neuro":>10}  {"neuro→heart":>10}')
    # From hemorrhage_transient.py results:
    radau_at30 = get(30)[1]
    radau_min = map_vals.min()
    radau_tmin = times[map_vals.argmin()]
    print(f'  {"MAP_min":20}  {radau_min:10.3f}  {"89.183":>10}  {"88.982":>10}')
    print(f'  {"t_MAP_min":20}  {radau_tmin:10.2f}  {"24.90":>10}  {"28.02":>10}')
    print(f'  {"MAP @ t=30s":20}  {radau_at30:10.3f}  {"98.355":>10}  {"89.049":>10}')
    radau_at90 = get(90)[1]
    radau_at120 = get(120)[1]
    print(f'  {"MAP @ t=90s":20}  {radau_at90:10.3f}  {"97.363":>10}  {"97.360":>10}')
    print(f'  {"MAP @ t=120s":20}  {radau_at120:10.3f}  {"97.355":>10}  {"97.359":>10}')
else:
    print('  Could not find MAP index in state_map')
    print('  Available keys:', list(state_map.keys())[:30])