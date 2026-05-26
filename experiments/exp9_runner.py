#!/usr/bin/env python3
"""
Shared runner for exp9 X/Y/Z conditions.
Each condition is a distinct patch from baseline buggy code.
Run via: python exp9_runner.py X|Y|Z <dc> <dt>
"""
import sys, os, types

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

def _load_all_modules(with_patch_fn):
    """Load all modules, applying patch to neuro.py and heart.py before exec."""
    sys.modules["parameters"] = types.ModuleType("parameters")
    exec(compile(_read_patched(os.path.join(SRC_DIR, "parameters.py")),
                 os.path.join(SRC_DIR, "parameters.py"), "exec"),
         sys.modules["parameters"].__dict__)
    for _name in ["blood","fluid","cardiac_electrophysiology","noble_purkinje",
                  "respiratory_rhythm","heart","lung","kidney","gut","liver",
                  "endocrine","neuro","immune","coagulation","lymphatic",
                  "lifecycle","toxicology","organ_health","pharmacology","simulation"]:
        _path = os.path.join(SRC_DIR, f"{_name}.py")
        _src = _read_patched(_path)
        if with_patch_fn:
            _src = with_patch_fn(_name, _src)
        _mod = types.ModuleType(_name)
        sys.modules[_name] = _mod
        exec(compile(_src, _path, "exec"), _mod.__dict__)

def patch_X(name, src):
    """Condition X (buggy): FC no dt-scale, chemo in net_HR_add, NO continuous chemo."""
    if name == "neuro":
        src = src.replace(
            "net_HR_add = (\n            pain_HR_add\n            + seizure_HR_add\n            + cns_HR_add\n            # chemo_HR_add → 已移至连续路径 heart.py\n        )",
            "net_HR_add = (\n            pain_HR_add\n            + seizure_HR_add\n            + cns_HR_add\n            + chemo_HR_add\n        )"
        ).replace(
            "factor_commands.append(FactorCommand(\"heart.heart_rate\", \"add\", net_HR_add * dt))",
            "factor_commands.append(FactorCommand(\"heart.heart_rate\", \"add\", net_HR_add))"
        ).replace(
            "factor_commands.append(FactorCommand(\"lung.respiratory_rate\", \"add\", net_RR_add * dt))",
            "factor_commands.append(FactorCommand(\"lung.respiratory_rate\", \"add\", net_RR_add))"
        )
    if name == "heart":
        src = src.replace(
            "chemo_HR = chemoreceptor_drive * 15.0",
            "chemo_HR = 0.0   # DISABLED for X"
        ).replace(
            "HR_delta = (HR_para + HR_symp + chemo_HR) * dt",
            "HR_delta = (HR_para + HR_symp) * dt"
        )
    return src

def patch_Y(name, src):
    """Condition Y (A-only): FC × dt, chemo in net_HR_add, NO continuous chemo."""
    if name == "neuro":
        src = src.replace(
            "net_HR_add = (\n            pain_HR_add\n            + seizure_HR_add\n            + cns_HR_add\n            # chemo_HR_add → 已移至连续路径 heart.py\n        )",
            "net_HR_add = (\n            pain_HR_add\n            + seizure_HR_add\n            + cns_HR_add\n            + chemo_HR_add\n        )"
        )
    if name == "heart":
        src = src.replace(
            "chemo_HR = chemoreceptor_drive * 15.0",
            "chemo_HR = 0.0   # DISABLED for Y"
        ).replace(
            "HR_delta = (HR_para + HR_symp + chemo_HR) * dt",
            "HR_delta = (HR_para + HR_symp) * dt"
        )
    return src

# Condition Z: no patch (current code)
def no_patch(name, src):
    return src

if __name__ == "__main__":
    import json, argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("condition", choices=["X","Y","Z"])
    parser.add_argument("dc", type=float)
    parser.add_argument("dt", type=float)
    args = parser.parse_args()

    patch_map = {"X": patch_X, "Y": patch_Y, "Z": no_patch}
    _load_all_modules(patch_map[args.condition])

    from simulation import VirtualCreature
    creature = VirtualCreature(body_weight_kg=20, age_days=1095)
    creature.lifecycle._original_baselines["lung.diffusion_coefficient"] = args.dc
    creature.dt = args.dt

    for _ in range(int(30.0 / args.dt)):
        creature.step()

    for _ in range(int(60.0 / args.dt)):
        creature.step()

    result = {
        "condition": args.condition,
        "dc": args.dc,
        "dt": args.dt,
        "MAP": round(creature.heart.mean_arterial_pressure, 3),
        "HR": round(creature.heart.heart_rate, 2),
        "PaO2": round(creature.blood.arterial_PO2_mmHg, 2),
        "PaCO2": round(creature.blood.arterial_PCO2_mmHg, 2),
        "chemo_drive": round(creature.neuro.chemoreceptor_drive, 6),
    }
    print(json.dumps(result))