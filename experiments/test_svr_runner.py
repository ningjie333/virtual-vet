#!/usr/bin/env python3
"""Subprocess runner for SVR dt-dependency test."""
import sys, os, types, json

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
sys.path.insert(0, SRC_DIR)

def _read_patched(path):
    return open(path, encoding="utf-8").read().replace("from src.", "from ")

def _load_modules(patch_fn):
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
        _src = patch_fn(_name, _src)
        _mod = types.ModuleType(_name)
        sys.modules[_name] = _mod
        exec(compile(_src, _path, "exec"), _mod.__dict__)

def patch_current(name, src):
    """Current code: SVR multiply no dt scaling."""
    return src

def patch_svr_no_dt(name, src):
    """Seizure SVR no dt scaling."""
    return src

def patch_svr_with_dt(name, src):
    """SVR multiply with dt scaling."""
    if name == "neuro":
        src = src.replace(
            'factor_commands.append(FactorCommand("heart.SVR", "multiply", net_SVR_mult))',
            'factor_commands.append(FactorCommand("heart.SVR", "multiply", net_SVR_mult ** dt))'
        )
    return src

DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]

def run_condition(condition, seizure_active):
    patch_map = {
        "baseline": patch_current,
        "no_dt": patch_svr_no_dt,
        "with_dt": patch_svr_with_dt,
    }
    _load_modules(patch_map[condition])

    from simulation import VirtualCreature
    results = {}

    for dt in DT_SWEEP:
        vc = VirtualCreature(body_weight_kg=20, age_days=1095)
        vc.dt = dt
        for _ in range(int(30.0 / dt)): vc.step()

        if seizure_active and condition != "baseline":
            vc.neuro._seizure_timer = 30.0
            vc.neuro.seizure = 1.0

        for _ in range(int(60.0 / dt)): vc.step()

        results[dt] = {
            "SVR": round(vc.heart.SVR, 4),
            "MAP": round(vc.heart.mean_arterial_pressure, 2),
            "HR": round(vc.heart.heart_rate, 2),
        }

    if len(results) > 1:
        svrs = [v["SVR"] for v in results.values()]
        results["svr_range"] = round(max(svrs) - min(svrs), 4)

    return results

if __name__ == "__main__":
    condition = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    seizure_active = sys.argv[2] == "seizure" if len(sys.argv) > 2 else False
    results = run_condition(condition, seizure_active)
    print(json.dumps(results))