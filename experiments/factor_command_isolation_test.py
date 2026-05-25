"""Subprocess isolation test: Sequential without FactorCommand vs Sequential with FactorCommand"""
import subprocess, os, textwrap

pwd = os.getcwd()
src_dir = os.path.join(pwd, 'src')
print(f'Working dir: {pwd}')
print(f'SRC_DIR: {src_dir}')

SCRIPT = r"""
import sys, os, types, numpy as np
SRC_DIR = r"{src_dir}"
sys.path.insert(0, SRC_DIR)

def _read_patched(path, remove_factor=False):
    src = open(path, encoding="utf-8").read().replace("from src.", "from ")
    if remove_factor:
        # Remove all issue_factor_command calls
        src = src.replace("self.issue_factor_command(", "# ISSUE_FACTOR_COMMAND_REMOVED: self.issue_factor_command(")
    return src

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
             os.path.join(SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _n in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _p = os.path.join(SRC_DIR, _n + ".py")
    _s = _read_patched(_p, remove_factor=({remove_factor}))
    _m = types.ModuleType(_n)
    sys.modules[_n] = _m
    exec(compile(_s, _p, "exec"), _m.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature

DT = 0.01
T_END = 60.0
n_steps = int(T_END / DT)

{class_def}

vc.dt = DT
for i in range(n_steps):
    vc.step()
print(f"MAP={{vc.heart.mean_arterial_pressure:.3f}}, HR={{vc.heart.heart_rate:.2f}}", flush=True)
"""

heart_class = 'vc = VirtualCreature(body_weight_kg=20.0)'

neuro_class = """
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
            t_rel = t - cfg["t_onset"]
            if t_rel >= 0:
                sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg["width"]))
                t_fall = t_rel - 3 * cfg["width"]
                sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg["width"]))
                rate = cfg["k"] * sigmoid_on * (1.0 - sigmoid_off)
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
        self.heart.contractility_factor = tox_state["contractility_factor"]
        svr_factor = tox_state["svr_factor"]
        if hasattr(self, "medication_due") and self.medication_due:
            pharma_commands = self.pharmacology.compute(dt, self)
            if pharma_commands:
                for cmd in pharma_commands:
                    self.apply_factor(cmd)
            self.medication_due = False
        neuro_state = self.neuro.compute(dt,
            {"MAP_mmHg": self.heart.mean_arterial_pressure,
             "HR": self.heart.heart_rate,
             "SVR": self.heart.SVR},
            {"PaO2_mmHg": self.blood.arterial_PO2_mmHg,
             "PaCO2_mmHg": self.blood.arterial_PCO2_mmHg,
             "pH": self.blood.arterial_pH})
        for cmd in neuro_state.get("factor_commands", []):
            self.apply_factor(cmd)
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)
        co_ml_min = heart_state["cardiac_output_ml_min"]
        lung_state = self.lung.compute(dt, co_ml_min)
        kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], 0, co_ml_min)
        gut_state = self.gut.compute(dt, co_ml_min)
        liver_state = self.liver.compute(dt, gut_state, co_ml_min)
        endocrine_state = self.endocrine.compute(dt)
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        immune_state = self.immune.compute(dt, endocrine_state)
        if self.disease:
            engine_state = {"MAP_mmHg": heart_state["MAP_mmHg"],
                           "HR": heart_state["heart_rate_bpm"],
                           "CO_L_per_min": co_ml_min / 1000.0,
                           "blood_volume_mL": self.heart.circulating_volume_ml}
            commands = self.disease.compute(dt, engine_state)
            if commands:
                for cmd in commands:
                    self.apply_factor(cmd)
        fluid_state = self.fluid.compute(dt)
        self.current_time_s += dt
vc = VC_NeuroFirst(body_weight_kg=20.0)
"""

print('\n=== EXPERIMENT 1: Sequential without FactorCommand ===\n')
script_no_factor = SCRIPT.format(src_dir=src_dir, class_def=textwrap.dedent(neuro_class), remove_factor="True")
r1 = subprocess.run(['python', '-c', script_no_factor], capture_output=True, text=True, timeout=300)
print('Sequential (no FactorCommand):')
print(' ', r1.stdout.strip())
if r1.stderr:
    err = r1.stderr.strip()
    if err and 'WARNING' not in err and 'Deprecation' not in err:
        print('  stderr:', err[:500])

print('\n=== EXPERIMENT 2: Sequential WITH FactorCommand ===\n')
script_with_factor = SCRIPT.format(src_dir=src_dir, class_def=textwrap.dedent(neuro_class), remove_factor="False")
r2 = subprocess.run(['python', '-c', script_with_factor], capture_output=True, text=True, timeout=300)
print('Sequential (with FactorCommand):')
print(' ', r2.stdout.strip())
if r2.stderr:
    err = r2.stderr.strip()
    if err and 'WARNING' not in err and 'Deprecation' not in err:
        print('  stderr:', err[:500])

print('\n=== ANALYSIS ===')
def parse_output(out):
    for line in out.strip().split('\n'):
        if 'MAP=' in line:
            try:
                map_val = float(line.split('MAP=')[1].split(',')[0])
                return map_val
            except:
                pass
    return None

map_no_fc = parse_output(r1.stdout)
map_with_fc = parse_output(r2.stdout)

print(f'No FactorCommand: MAP = {map_no_fc}')
print(f'With FactorCommand: MAP = {map_with_fc}')
print(f'Radau reference: MAP = 100.000')
print(f'Unified Euler: MAP ≈ 100.0 (RMSE < 0.2)')

if map_no_fc and map_with_fc:
    diff_with_without = abs(map_with_fc - map_no_fc)
    print(f'\nDifference (with vs without FC): {diff_with_without:.3f} mmHg')

    # Interpretation
    if map_no_fc > 143 and map_with_fc > 143:
        print('\n→ Explanation B confirmed: O(1) bias is from Gauss-Seidel structural error, NOT FactorCommand')
        print('  Both with and without FactorCommand → ~144.7 mmHg')
    elif map_no_fc < 101 and map_with_fc > 143:
        print('\n→ Explanation A confirmed: FactorCommand is the cause of O(1) bias')
        print('  Without FC → ~100 mmHg (correct); With FC → ~144.7 mmHg (biased)')
    elif map_no_fc < 101 and map_with_fc < 101:
        print('\n→ Unexpected: Neither produces bias. Something else is at play.')
    elif map_with_fc < 101:
        print('\n→ Partial evidence for A: FactorCommand contributes significantly to bias')
    else:
        print(f'\n→ Inconclusive: map_no_fc={map_no_fc}, map_with_fc={map_with_fc}')
        print('  Need to examine the actual values.')