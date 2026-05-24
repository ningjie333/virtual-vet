"""Step 2: compute RK45"""
import os, sys, types, json, numpy as np
EXPERIMENTS_DIR = 'experiments'
PROJECT_ROOT = os.path.dirname(os.path.abspath(EXPERIMENTS_DIR))
SRC_DIR = os.path.join(PROJECT_ROOT, 'src')
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding='utf-8').read().replace('from src.', 'from ')

sys.modules['parameters'] = types.ModuleType('parameters')
exec(compile(_read_patched(os.path.join(SRC_DIR, 'parameters.py')), os.path.join(SRC_DIR, 'parameters.py'), 'exec'), sys.modules['parameters'].__dict__)

for _name in ['blood', 'fluid', 'cardiac_electrophysiology', 'noble_purkinje', 'respiratory_rhythm', 'heart', 'lung', 'kidney', 'gut', 'liver', 'endocrine', 'neuro', 'immune', 'coagulation', 'lymphatic', 'lifecycle', 'toxicology', 'organ_health', 'pharmacology', 'simulation']:
    _path = os.path.join(SRC_DIR, f'{_name}.py')
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, 'exec'), _mod.__dict__)

from scipy.integrate import solve_ivp
import time

VirtualCreature = sys.modules['simulation'].VirtualCreature
vc = VirtualCreature(body_weight_kg=20.0)
vc.set_blood_loss_scenario(t_onset=5.0, total_ml=400.0, duration=20.0, width=2.0)
vc._cached_inputs.clear()
y0 = vc._pack_unified_state()
_ = vc._unified_rhs(0.0, y0)

T_END, SAVE_DT = 10.0, 0.5
t_eval = np.arange(0, T_END + SAVE_DT/2, SAVE_DT)

print('RK45...')
t0 = time.time()
sol = solve_ivp(lambda t, y: vc._unified_rhs(t, y), (0.0, T_END), y0,
                method='RK45', rtol=1e-6, atol=1e-8, max_step=0.5, t_eval=t_eval)
print(f'Done in {time.time()-t0:.1f}s, nfev={sol.nfev}, success={sol.success}')
rk_map = []
for i in range(sol.y.shape[1]):
    vc._cached_inputs.clear()
    vc._unpack_unified_state(sol.y[:, i])
    rk_map.append(float(vc.heart.mean_arterial_pressure))
rk_map = np.array(rk_map)
print(f'RK45: [{rk_map.min():.4f}, {rk_map.max():.4f}], final={rk_map[-1]:.4f}')

with open('experiments/ref_rk45.json', 'w') as f:
    json.dump({'t': t_eval.tolist(), 'map': rk_map.tolist(), 'nfev': int(sol.nfev)}, f)
print('Saved: experiments/ref_rk45.json')