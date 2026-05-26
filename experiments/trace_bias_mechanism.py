"""Trace the complete bias mechanism: blood gases, chemoreceptor, neuro FCs."""
import sys, os, types, numpy as np

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

creature = VirtualCreature(body_weight_kg=20)
creature.dt = 0.01

print(f"{'t(s)':>7} {'MAP':>9} {'HR':>8} {'SVR':>8} {'sym':>7} {'PO2':>7} {'PCO2':>7} {'pH':>7} {'chemo':>7} {'FCval':>7}")
print("-" * 90)

fc_start_step = None
for step in range(6000):
    t = step * 0.01
    creature.step()
    # Check for FC at every step near the threshold crossing
    h, b, n = creature.heart, creature.blood, creature.neuro
    net_HR_add = n.chemoreceptor_drive * 15.0
    if abs(net_HR_add) > 0.1 and fc_start_step is None:
        fc_start_step = step
        print(f"\n*** FC starts at t={t:.3f}s (step {step}), chemo_drive={n.chemoreceptor_drive:.6f}, net_HR_add={net_HR_add:.4f} ***\n")
    if step % 10 == 0:
        h, b, n = creature.heart, creature.blood, creature.neuro
        chemo_HR_add = n.chemoreceptor_drive * 15.0
        has_fc = abs(chemo_HR_add) > 0.1
        fc_val = chemo_HR_add if has_fc else 0.0
        print(f"{t:7.3f} {h.mean_arterial_pressure:9.4f} {h.heart_rate:8.4f} {h.SVR:8.4f} "
              f"{h.sympathetic:7.5f} {b.arterial_PO2_mmHg:7.2f} {b.arterial_PCO2_mmHg:7.2f} "
              f"{b.arterial_pH:7.4f} {n.chemoreceptor_drive:7.6f} {fc_val:7.4f}")

print(f"\nFinal: MAP={creature.heart.mean_arterial_pressure:.1f}, HR={creature.heart.heart_rate:.1f}")
print(f"Chemo drive: {creature.neuro.chemoreceptor_drive:.6f}")
