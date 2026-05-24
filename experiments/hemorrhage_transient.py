"""
Hemorrhage transient analysis — two orders compared
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
DT = 0.01
T_END = 120.0
N_STEPS = int(T_END / DT)

class VC_NeuroFirst(VirtualCreature):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._step_count = 0
    def step(self):
        dt = self.dt
        self._step_count += 1
        t = self.current_time_s
        self._process_events(t)
        if self._blood_loss_config is not None:
            cfg = self._blood_loss_config
            t_rel = t - cfg['t_onset']
            if t_rel >= 0:
                sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg['width']))
                t_fall = t_rel - 3 * cfg['width']
                sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg['width']))
                rate = cfg['k'] * sigmoid_on * (1.0 - sigmoid_off)
                self.heart.circulating_volume_ml -= rate * dt
                if self.heart.circulating_volume_ml < 0:
                    self.heart.circulating_volume_ml = 0
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors(self)
            death_cause = self.lifecycle.death_check()
            if death_cause:
                self._handle_death(death_cause)
                return
        tox_state = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox_state['contractility_factor']
        svr_factor = tox_state['svr_factor']
        if hasattr(self, 'medication_due') and self.medication_due:
            pharma_commands = self.pharmacology.compute(dt, self)
            if pharma_commands:
                for cmd in pharma_commands:
                    self.apply_factor(cmd)
            self.medication_due = False
        neuro_state = self.neuro.compute(dt,
            {'MAP_mmHg': self.heart.mean_arterial_pressure,
             'HR': self.heart.heart_rate,
             'SVR': self.heart.SVR},
            {'PaO2_mmHg': self.blood.arterial_PO2_mmHg,
             'PaCO2_mmHg': self.blood.arterial_PCO2_mmHg,
             'pH': self.blood.arterial_pH})
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)
        co_ml_min = heart_state['cardiac_output_ml_min']
        self.lung.compute(dt, co_ml_min)
        self.kidney.compute(dt, heart_state['MAP_mmHg'], 0, co_ml_min)
        gut_state = self.gut.compute(dt, co_ml_min)
        liver_state = self.liver.compute(dt, gut_state, co_ml_min)
        endocrine_state = self.endocrine.compute(dt)
        self.coagulation.compute(dt, liver_state, {})
        self.lymphatic.compute(dt, gut_state, {})
        self.immune.compute(dt, endocrine_state)
        if self.disease:
            engine_state = {'MAP_mmHg': heart_state['MAP_mmHg'],
                           'HR': heart_state['heart_rate_bpm'],
                           'CO_L_per_min': co_ml_min / 1000.0,
                           'blood_volume_mL': self.heart.circulating_volume_ml}
            commands = self.disease.compute(dt, engine_state)
            if commands:
                for cmd in commands:
                    self.apply_factor(cmd)
        self.fluid.compute(dt)
        self.current_time_s += dt

def run(VCClass):
    vc = VCClass(body_weight_kg=WEIGHT_KG)
    vc.dt = DT
    vc._cached_inputs.clear()
    vc._blood_loss_config = {'t_onset': 5.0, 'volume_ml': 400.0, 'k': 35.0, 'width': 6.0}
    times, maps, bvs = [], [], []
    for i in range(N_STEPS + 1):
        times.append(vc.current_time_s)
        maps.append(float(vc.heart.mean_arterial_pressure))
        bvs.append(float(vc.heart.circulating_volume_ml))
        vc.step()
    times = np.array(times)
    maps = np.array(maps)
    bvs = np.array(bvs)
    return times, maps, bvs

print('Running simulation...')
times_o, maps_o, bvs_o = run(VirtualCreature)
times_r, maps_r, bvs_r = run(VC_NeuroFirst)

def get_val(times, maps, bvs, t_target, t_window=0.05):
    idx = np.where(np.abs(times - t_target) < t_window)[0]
    return idx[0], times[idx[0]], maps[idx[0]], bvs[idx[0]]

def summary(times, maps, bvs, label):
    map_min = maps.min()
    t_map_min = times[maps.argmin()]
    t_map_lt65 = (maps < 65).sum() * DT
    return {
        'label': label,
        'MAP_min': map_min,
        't_MAP_min': t_map_min,
        't_MAP<65': t_map_lt65,
        'MAP_final': maps[-1],
        'BV_final': bvs[-1],
    }

s_o = summary(times_o, maps_o, bvs_o, 'Original')
s_r = summary(times_r, maps_r, bvs_r, 'Reversed')

print()
print('=== Transient Metrics: 400mL Hemorrhage (onset=5s, 120s) ===')
print()
print(f'{"Metric":<20}  {"Original":>12}  {"Reversed":>12}  {"delta":>12}')
print('-' * 62)
for key in ['MAP_min', 't_MAP_min', 't_MAP<65']:
    v_o = s_o[key]
    v_r = s_r[key]
    if key == 't_MAP<65':
        print(f'{key:<20}  {v_o:12.3f}  {v_r:12.3f}  {v_r-v_o:+.3f}')
    else:
        print(f'{key:<20}  {v_o:12.3f}  {v_r:12.3f}  {v_r-v_o:+.3f}')
print()
print('=== Time series key timepoints ===')
print(f'{"t":>6}  {"Orig MAP":>10}  {"Rev MAP":>10}  {"Orig BV":>10}  {"Rev BV":>10}')
for t_target in [5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 90, 120]:
    idx_o, t_o, map_o, bv_o = get_val(times_o, maps_o, bvs_o, t_target)
    idx_r, t_r, map_r, bv_r = get_val(times_r, maps_r, bvs_r, t_target)
    print(f'{t_target:6.0f}  {map_o:10.3f}  {map_r:10.3f}  {bv_o:10.1f}  {bv_r:10.1f}')

print()
print('=== Nadir window (t=15-35s) ===')
mask_o = (times_o >= 15) & (times_o <= 35)
mask_r = (times_r >= 15) & (times_r <= 35)
print(f'Original MAP range in [15,35]s: [{maps_o[mask_o].min():.3f}, {maps_o[mask_o].max():.3f}]')
print(f'Reversed MAP range in [15,35]s: [{maps_r[mask_r].min():.3f}, {maps_r[mask_r].max():.3f}]')

print()
print('=== Clinical thresholds ===')
# MAP < 65 for how long?
for threshold in [60, 65, 70, 80]:
    dur_o = (maps_o < threshold).sum() * DT
    dur_r = (maps_r < threshold).sum() * DT
    print(f'  MAP < {threshold} mmHg: Original={dur_o:.2f}s  Reversed={dur_r:.2f}s  delta={dur_r-dur_o:+.2f}s')