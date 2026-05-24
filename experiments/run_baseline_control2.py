"""
Baseline control: no hemorrhage, 60s
RK45 reference (fast, works at any T)
Pure Euler vs Sequential vs RK45
"""
import os, sys, types, json, numpy as np
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
import time

WEIGHT_KG = 20.0
T_END = 60.0
SAVE_DT = 0.5
DT = 0.01

def make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def pack(vc): return vc._pack_unified_state()
def record(vc, y, t):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(y)
    return {'MAP': float(vc.heart.mean_arterial_pressure),
            'HR': float(vc.heart.heart_rate)}

t_eval = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)
print(f'T_eval: {len(t_eval)} points')

# RK45 reference (no hemorrhage is easy - explicit works fine)
print('=== RK45 Reference ===')
vc = make_vc()
y0 = pack(vc)
_ = vc._unified_rhs(0.0, y0)
t0 = time.time()
sol = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0,
                method='RK45', rtol=1e-6, atol=1e-8, max_step=0.5, t_eval=t_eval)
print(f'  RK45 done in {time.time()-t0:.1f}s, nfev={sol.nfev}, success={sol.success}')
ref_map = np.array([record(vc, sol.y[:, i], t_eval[i])['MAP'] for i in range(len(t_eval))])
print(f'  RK45 MAP: [{ref_map.min():.3f}, {ref_map.max():.3f}], final={ref_map[-1]:.3f}')

# Pure Euler
print('\n=== Pure Euler (dt=0.01) ===')
vc = make_vc()
y = pack(vc)
_ = vc._unified_rhs(0.0, y)
n_steps = int(T_END / DT)
save_interval = int(SAVE_DT / DT)
t0 = time.time()
recs_pe = []
for i in range(n_steps + 1):
    if i % save_interval == 0:
        recs_pe.append({'t': i*DT, 'MAP': record(vc, y, i*DT)['MAP']})
    y = y + vc._unified_rhs(i * DT, y) * DT
print(f'  Pure Euler done in {time.time()-t0:.1f}s')
pe_map = np.array([r['MAP'] for r in recs_pe])
pe_t = np.array([r['t'] for r in recs_pe])
f_pe = lambda t: np.interp(t, pe_t, pe_map)
rmse_pe = np.sqrt(np.mean((ref_map - f_pe(t_eval))**2))
print(f'  MAP: [{pe_map.min():.3f}, {pe_map.max():.3f}], final={pe_map[-1]:.3f}')
print(f'  RMSE vs RK45: {rmse_pe:.6f} mmHg')

# Sequential Euler
print('\n=== Sequential Euler (step, dt=0.01) ===')
vc = make_vc()
vc.dt = DT
n_steps = int(T_END / DT)
save_interval = int(SAVE_DT / DT)
t0 = time.time()
recs_seq = []
for i in range(n_steps + 1):
    if i % save_interval == 0:
        recs_seq.append({'t': i*DT, 'MAP': float(vc.heart.mean_arterial_pressure)})
    vc.step()
print(f'  Sequential done in {time.time()-t0:.1f}s')
seq_map = np.array([r['MAP'] for r in recs_seq])
seq_t = np.array([r['t'] for r in recs_seq])
f_seq = lambda t: np.interp(t, seq_t, seq_map)
rmse_seq = np.sqrt(np.mean((ref_map - f_seq(t_eval))**2))
print(f'  MAP: [{seq_map.min():.3f}, {seq_map.max():.3f}], final={seq_map[-1]:.3f}')
print(f'  RMSE vs RK45: {rmse_seq:.6f} mmHg')

# Summary
print(f'\n=== Baseline Control (No Hemorrhage, T_END=60s) ===')
print(f'{"Method":<20}  {"RMSE vs RK45":>12}  {"MAP_final":>10}')
print(f'{"Pure Euler":<20}  {rmse_pe:>12.6f}  {pe_map[-1]:>10.3f}')
print(f'{"Sequential Euler":<20}  {rmse_seq:>12.6f}  {seq_map[-1]:>10.3f}')
print(f'{"RK45 ref":<20}  {"0.000000":>12}  {ref_map[-1]:>10.3f}')

delta_seq = seq_map[-1] - ref_map[-1]
delta_pe = pe_map[-1] - ref_map[-1]
print(f'\nMAP deviation from RK45 reference:')
print(f'  Pure Euler:      {delta_pe:+.4f} mmHg')
print(f'  Sequential Euler:{delta_seq:+.4f} mmHg')

if max(rmse_pe, rmse_seq) < 0.5:
    print('\n✓ Both methods agree with RK45 reference in steady state (no bias in baseline)')
else:
    print(f'\n✗ Unexpected large deviation - baseline bias detected')

out = {
    't': t_eval.tolist(),
    'rk45_map': ref_map.tolist(),
    'pure_euler_map': pe_map.tolist(),
    'seq_euler_map': seq_map.tolist(),
    'rmse_pure_euler': rmse_pe,
    'rmse_seq_euler': rmse_seq,
    'map_final_rk45': float(ref_map[-1]),
    'map_final_pure_euler': float(pe_map[-1]),
    'map_final_seq_euler': float(seq_map[-1]),
}
with open('experiments/baseline_control.json', 'w') as f:
    json.dump(out, f, indent=2)
print('\nSaved: experiments/baseline_control.json')