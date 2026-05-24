"""
补跑缺失实验：只跑 Euler dt=0.001（精细对照组）
不重新跑 Ref/Euler/Radau（已有数据）
"""
import sys, os, types, time as time_, json
import numpy as np
from scipy.integrate import solve_ivp

_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

def _read_patched(path):
    src = open(path, encoding="utf-8").read()
    return src.replace("from src.", "from ")

sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(_SRC_DIR, "parameters.py")),
             os.path.join(_SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in ["blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation"]:
    _path = os.path.join(_SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature

WEIGHT_KG = 20.0
T_END = 60.0
DT_SAVE = 2.0
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0

def _make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc

def _record(vc, t):
    CO = vc.heart.heart_rate * vc.heart.stroke_volume
    return dict(
        t=t, HR=vc.heart.heart_rate,
        MAP=vc.heart.mean_arterial_pressure, CO=CO,
        PaCO2=vc.blood.arterial_PCO2_mmHg,
        pH=vc.blood.arterial_pH,
        blood_volume_mL=vc.heart.circulating_volume_ml,
    )

def run_sequential_dt0001():
    vc = _make_vc()
    dt = 0.001
    total_steps = int(T_END / dt)
    vc._cached_inputs.clear()
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)
    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME, duration=20.0, width=2.0)

    t0 = time_.perf_counter()
    time_series = [_record(vc, 0.0)]
    save_interval = int(DT_SAVE / dt)

    for step_i in range(total_steps):
        vc.step()
        if step_i % save_interval == 0:
            time_series.append(_record(vc, vc.current_time_s))

    elapsed = time_.perf_counter() - t0
    ts = time_series
    map_vals = [p["MAP"] for p in ts]
    min_MAP = min(map_vals)
    min_MAP_t = ts[np.argmin(map_vals)]["t"]
    initial_MAP = time_series[0]["MAP"]
    target_low = initial_MAP * 0.90
    recover_t = None
    for p in ts:
        if p["t"] > min_MAP_t and p["MAP"] >= target_low:
            recover_t = p["t"]
            break

    return dict(
        success=True, time_s=elapsed,
        initial_HR=time_series[0]["HR"],
        initial_MAP=initial_MAP,
        initial_CO=time_series[0]["CO"],
        min_MAP_after_shock=min_MAP,
        min_MAP_at_t=min_MAP_t,
        time_to_recover_MAP=recover_t,
        HR_at_30s=ts[min(15, len(ts)-1)]["HR"] if len(ts) > 15 else None,
        MAP_at_30s=ts[min(15, len(ts)-1)]["MAP"] if len(ts) > 15 else None,
        CO_at_30s=ts[min(15, len(ts)-1)]["CO"] if len(ts) > 15 else None,
        time_series=time_series,
    )

if __name__ == "__main__":
    print("补跑 Euler dt=0.001（60,000 步，预计 30-60s）...")
    r = run_sequential_dt0001()
    print(f"  完成: min_MAP={r['min_MAP_after_shock']:.2f}, t={r['time_s']:.1f}s")

    # 合并到现有 JSON
    out_path = os.path.join(_EXPERIMENTS_DIR, "coupling_comparison_data.json")
    with open(out_path, encoding="utf-8") as f:
        data = json.load(f)

    r["method"] = "Sequential (Euler dt=0.001)"
    data["sequential_dt0001"] = r

    # 重新计算 panel_d
    ref_ts = data["reference"]["time_series"]
    ref_map_by_t = {p["t"]: p["MAP"] for p in ref_ts}

    panel_d = []
    for key in ["reference", "semi_implicit", "sequential", "sequential_dt001",
                "sequential_dt010", "sequential_dt0001"]:
        if key not in data:
            continue
        d = data[key]
        if not d.get("success") or not d.get("time_series"):
            continue
        max_dev = 0.0
        mse_sum = 0.0
        n = 0
        steady_err = None
        for p in d["time_series"]:
            if p["t"] in ref_map_by_t:
                dev = abs(p["MAP"] - ref_map_by_t[p["t"]])
                if dev > max_dev:
                    max_dev = dev
                mse_sum += dev ** 2
                n += 1
                if p["t"] == 60.0:
                    steady_err = dev
        rmse = np.sqrt(mse_sum / n) if n > 0 else None
        panel_d.append({
            "method": d["method"],
            "time_s": d["time_s"],
            "max_MAP_deviation": max_dev,
            "rmse_MAP": rmse,
            "steady_state_error": steady_err,
        })

    data["panel_d"] = panel_d

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    print(f"\npanel_d 指标：")
    for p in panel_d:
        print(f"  {p['method']:<35} time={p['time_s']:>8.2f}s  L∞={p['max_MAP_deviation']:.3f}  RMSE={p['rmse_MAP']:.3f}  SS={p['steady_state_error']}")
    print(f"\n数据已更新 → {out_path}")