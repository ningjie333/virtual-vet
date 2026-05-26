"""Diagnostic: trace VdP and lung variables to find PO2 oscillation root cause."""
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

creature = VirtualCreature(body_weight_kg=20)
creature.dt = 0.01

# Warmup 30s to reach steady state
for _ in range(3000):
    creature.step()

# Now trace detailed variables for 30s, save every 5 steps
records = []
lung = creature.lung
vdp = lung._vdp
save_interval = 5  # every 5 steps = 0.05s

print("Tracing VdP + lung variables...")
for i in range(3000):  # 30s
    creature.step()
    if i % save_interval == 0:
        t = (i + 3000) * creature.dt
        # Direct VdP state
        minute_vent = lung.respiratory_rate * lung.tidal_volume
        vent_ratio = minute_vent / lung.base_minute_ventilation

        records.append({
            "t": t,
            "RR": lung.respiratory_rate,
            "TV": lung.tidal_volume,
            "min_vent": minute_vent,
            "vent_ratio": vent_ratio,
            "PACO2": lung.alveolar_PCO2,
            "PAO2": lung.alveolar_PO2,
            "PaO2": creature.blood.arterial_PO2_mmHg,
            "PaCO2": creature.blood.arterial_PCO2_mmHg,
            "vdp_x": vdp.x,
            "vdp_v": vdp.v,
            "vdp_amp": vdp.amplitude,
            "vdp_omega": vdp.omega,
            "vdp_phase": vdp.phase,
            "insp": vdp.is_inspiration,
        })

# Print analysis
print(f"\n{'t':>6} {'RR':>6} {'TV':>6} {'MV':>7} {'VR':>6} {'PACO2':>6} {'PAO2':>6} {'PaO2':>6} {'x':>7} {'v':>8} {'amp':>6} {'insp':>5}")
print("-" * 80)
for r in records[::10]:  # every 10th record (0.5s)
    print(f"{r['t']:6.2f} {r['RR']:6.1f} {r['TV']:6.0f} {r['min_vent']:7.0f} "
          f"{r['vent_ratio']:6.3f} {r['PACO2']:6.1f} {r['PAO2']:6.1f} {r['PaO2']:6.1f} "
          f"{r['vdp_x']:7.3f} {r['vdp_v']:8.3f} {r['vdp_amp']:6.3f} "
          f"{'INSP' if r['insp'] else 'EXP':>5}")

# Statistics
po2_vals = [r['PaO2'] for r in records]
vdp_amp_vals = [r['vdp_amp'] for r in records]
print(f"\n=== Statistics ===")
print(f"PaO2: min={min(po2_vals):.1f}, max={max(po2_vals):.1f}, mean={sum(po2_vals)/len(po2_vals):.1f}")
print(f"VdP amplitude: min={min(vdp_amp_vals):.3f}, max={max(vdp_amp_vals):.3f}")
print(f"VdP omega: {vdp.omega:.3f} rad/s (target RR = {vdp.omega/6.2832*60:.1f}/min)")
print(f"Effective RR from omega: {vdp.respiratory_rate:.1f}/min")
print(f"VdP internal dt: {vdp.dt:.4f}s")

# Check n_vdp_iterations
from lung import DT_SECONDS
print(f"DT_SECONDS param: {DT_SECONDS}")
print(f"Simulation dt: {creature.dt}")
n_iters = max(1, round(creature.dt / DT_SECONDS))
print(f"n_vdp_iterations = max(1, round({creature.dt}/{DT_SECONDS})) = {n_iters}")
print(f"VdP advances {n_iters * vdp.dt:.4f}s per sim step of {creature.dt:.4f}s")
print(f"VdP speed multiplier: {n_iters * vdp.dt / creature.dt:.1f}x")
