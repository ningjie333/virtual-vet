#!/usr/bin/env python3
"""
exp2_dt_scaling.py — DT scaling experiment for chemoreceptor drive FactorCommands.

For each dt in [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]:
  - Create VirtualCreature(body_weight_kg=20)
  - Set creature.dt = dt
  - Run for 60 / TOTAL_STEPS (where TOTAL_STEPS = 60/dt)
  - Count FCs: whenever creature.neuro.chemoreceptor_drive * 15.0 > 0.1
  - Record final MAP, HR, FC count, FC rate (FCs/second)

Key prediction:
  - FC_count should scale as ~1/dt (O(1) in dt)
  - FC_count × dt should be approximately constant
  - Final MAP should be ~144.7 for all dt values
"""

import math
import os
import sys
import time
import types

# ── Monkey-patching to import src modules from experiments/ ──────────────
SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)


def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")


sys.modules["parameters"] = types.ModuleType("parameters")
exec(
    compile(
        _read_patched(os.path.join(SRC_DIR, "parameters.py")),
        os.path.join(SRC_DIR, "parameters.py"),
        "exec",
    ),
    sys.modules["parameters"].__dict__,
)

for _name in [
    "blood",
    "fluid",
    "cardiac_electrophysiology",
    "noble_purkinje",
    "respiratory_rhythm",
    "heart",
    "lung",
    "kidney",
    "gut",
    "liver",
    "endocrine",
    "neuro",
    "immune",
    "coagulation",
    "lymphatic",
    "lifecycle",
    "toxicology",
    "organ_health",
    "pharmacology",
    "simulation",
]:
    _path = os.path.join(SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

from simulation import VirtualCreature

# ── Experiment parameters ────────────────────────────────────────────────
DT_VALUES = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
TOTAL_TIME_S = 60.0  # 60 seconds

# ── Run experiment ───────────────────────────────────────────────────────
print(f"{'dt':<8} {'MAP':<8} {'HR':<8} {'FC_count':<10} {'FC_rate(/s)':<14} {'FC_count x dt':<14}")
print("-" * 62)

for dt in DT_VALUES:
    total_steps = int(TOTAL_TIME_S / dt + 0.5)

    creature = VirtualCreature(body_weight_kg=20)
    creature.dt = dt

    fc_count = 0

    for _ in range(total_steps):
        creature.step()
        # Count when chemoreceptor-driven HR contribution > 0.1 bpm
        if creature.neuro.chemoreceptor_drive * 15.0 > 0.1:
            fc_count += 1

    final_MAP = creature.heart.mean_arterial_pressure
    final_HR = creature.heart.heart_rate
    fc_rate = fc_count / TOTAL_TIME_S
    fc_dt_product = fc_count * dt

    print(
        f"{dt:<8.3f} {final_MAP:<8.1f} {final_HR:<8.1f} {fc_count:<10} {fc_rate:<14.3f} {fc_dt_product:<14.3f}"
    )
