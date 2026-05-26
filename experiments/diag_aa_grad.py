"""Quick check: what is the actual AA gradient and diffusion coefficient?"""
import sys, os, types

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
             os.path.join(SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
              "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
              "endocrine", "neuro", "immune", "coagulation", "lymphatic",
              "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _path = os.path.join(SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    _mod.__file__ = _path
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

from simulation import VirtualCreature
from parameters import LUNG_DIFFUSION_COEFFICIENT

creature = VirtualCreature(body_weight_kg=20)
creature.dt = 0.01

# Warmup
for _ in range(3000):
    creature.step()

# Check lung state
l = creature.lung
diff_coef = l.diffusion_coefficient
print(f"lung.diffusion_coefficient = {diff_coef}")
print(f"LUNG_DIFFUSION_COEFFICIENT param = {LUNG_DIFFUSION_COEFFICIENT}")
aa = 10.0 + (1.0 - diff_coef / LUNG_DIFFUSION_COEFFICIENT) * 30.0
print(f"aa_gradient = 10 + (1 - {diff_coef}/{LUNG_DIFFUSION_COEFFICIENT}) * 30 = {aa}")

# Step through and print diffusion coef and aa_gradient after each Step 4.5
# We need to intercept after lung.compute but before anything modifies it

# Let's directly compute what's happening
for i in range(100):
    creature.step()
    if i % 10 == 0:
        t = (3000 + i) * creature.dt
        # arterial_PO2 right after step()
        step_pao2 = creature.blood.arterial_PO2_mmHg

        # What should it be based on alveolar gas?
        alveolar_PAO2 = l.alveolar_PO2
        alveolar_PACO2 = l.alveolar_PCO2
        rr = l.respiratory_rate
        tv = l.tidal_volume
        mv = rr * tv
        vr = mv / l.base_minute_ventilation
        dc = l.diffusion_coefficient
        aa_calc = 10.0 + (1.0 - dc / LUNG_DIFFUSION_COEFFICIENT) * 30.0

        if i % 20 == 0:
            print(f"t={t:.1f}  PAO2={alveolar_PAO2:.1f}  PACO2={alveolar_PACO2:.1f}  "
                  f"RR={rr:.1f}  TV={tv:.0f}  MV={mv:.0f}  VR={vr:.3f}  "
                  f"DC={dc:.2f}  AA={aa_calc:.1f}  "
                  f"expected_PaO2={alveolar_PAO2-aa_calc:.1f}  actual_PaO2={step_pao2:.1f}")
