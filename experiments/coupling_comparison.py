"""
耦合策略对比实验 — Figure 4

实验目的：证明

（Radau + cached_inputs）优于顺序耦合（Euler step loop）
—— 同一生理场景（失血性休克）下，对比 MAP/HR/CO 瞬态响应。

数据来源：VetSim v1.0，20 kg 犬
场景：t=5s 失血 400 mL（23.5% BV = II级休克）
观察窗口：0–60 s（急性失血 + 压力感受器代偿期）

实验设计原则：
1. 预热验证（Warm-up）：无扰动运行 5s，确认两条路径在失血前一致（<3% 偏差）
2. 相同模型：两条路径使用相同的 sigmoid 连续失血模型
3. 参考基线：Radau rtol=1e-10 作为"真值"参考
"""

import sys
import os
import types
import time as time_
import json
from dataclasses import dataclass, asdict

import numpy as np
from scipy.integrate import solve_ivp

# ── 路径设置 ─────────────────────────────────────────────────────────────
_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def _read_patched(path: str) -> str:
    src = open(path, encoding="utf-8").read()
    return src.replace("from src.", "from ")


# 加载所有模块
sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(_SRC_DIR, "parameters.py")),
             os.path.join(_SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

for _name in [
    "blood", "fluid", "cardiac_electrophysiology", "noble_purkinje",
    "respiratory_rhythm", "heart", "lung", "kidney", "gut", "liver",
    "endocrine", "neuro", "immune", "coagulation", "lymphatic",
    "lifecycle", "toxicology", "organ_health", "pharmacology", "simulation",
]:
    _path = os.path.join(_SRC_DIR, f"{_name}.py")
    _src = _read_patched(_path)
    _mod = types.ModuleType(_name)
    sys.modules[_name] = _mod
    exec(compile(_src, _path, "exec"), _mod.__dict__)

VirtualCreature = sys.modules["simulation"].VirtualCreature


WEIGHT_KG = 20.0
T_END = 60.0         # 观察60s（急性失血+压力感受器代偿，Radau tractable）
DT_SAVE = 2.0         # 2s 采样间隔
BLOOD_LOSS_TIME = 5.0
BLOOD_LOSS_VOLUME = 400.0  # 400 mL = 23.5% BV = II级休克


@dataclass
class TimeSeriesPoint:
    t: float
    HR: float
    MAP: float
    CO: float
    PaCO2: float
    pH: float
    blood_volume_mL: float


@dataclass
class CouplingResult:
    method: str
    success: bool
    time_s: float
    time_series: list[TimeSeriesPoint]
    initial_HR: float | None
    initial_MAP: float | None
    initial_CO: float | None
    min_MAP_after_shock: float | None = None
    min_MAP_at_t: float | None = None
    time_to_recover_MAP: float | None = None
    HR_at_30s: float | None = None
    MAP_at_30s: float | None = None
    CO_at_30s: float | None = None
    message: str = ""


@dataclass
class WarmupVerification:
    max_HR_deviation: float   # % from initial
    max_MAP_deviation: float  # % from initial
    max_CO_deviation: float   # % from initial
    max_BV_deviation: float  # % from initial
    passed: bool
    message: str


def run_warmup_verification() -> WarmupVerification:
    """无扰动 warm-up 验证：两条路径在失血前是否一致（<3% 偏差）"""
    T_WARMUP = 5.0  # 预热 5s（sigmoid 在 t=5s 才开始失血）

    # Euler warmup
    vc_e = _make_vc()
    vc_e._cached_inputs.clear()
    y0 = vc_e._pack_unified_state()
    _ = vc_e._unified_rhs(0.0, y0)

    dt = 0.05
    n_steps = int(T_WARMUP / dt)
    euler_vals = []
    for i in range(n_steps + 1):
        t_i = i * dt
        if i % int(DT_SAVE / dt) == 0:
            euler_vals.append((t_i, _record(vc_e, t_i)))
        vc_e.step()

    # Radau warmup
    vc_r = _make_vc()
    vc_r._cached_inputs.clear()
    y0_r = vc_r._pack_unified_state()
    _ = vc_r._unified_rhs(0.0, y0_r)

    t_eval = np.arange(0.0, T_WARMUP + 1e-9, DT_SAVE)
    sol = solve_ivp(
        vc_r._unified_rhs, [0.0, T_WARMUP], y0_r,
        method="Radau",
        rtol=1e-4, atol=1e-6,
        t_eval=t_eval, dense_output=True,
        vectorized=False,
        max_step=0.5,
    )
    radau_vals = [(t_eval[0], _record(vc_r, 0.0))]
    for i, t_val in enumerate(sol.t):
        vc_r._unpack_unified_state(sol.y[:, i])
        radau_vals.append((t_val, _record(vc_r, t_val)))

    # 对齐时间点，比较偏差
    e_map = {t: p.MAP for t, p in euler_vals}
    r_map = {t: p.MAP for t, p in radau_vals}
    e_hr = {t: p.HR for t, p in euler_vals}
    r_hr = {t: p.HR for t, p in radau_vals}
    e_co = {t: p.CO for t, p in euler_vals}
    r_co = {t: p.CO for t, p in radau_vals}
    e_bv = {t: p.blood_volume_mL for t, p in euler_vals}
    r_bv = {t: p.blood_volume_mL for t, p in radau_vals}

    common_t = sorted(set(e_map.keys()) & set(r_map.keys()))
    baseline_MAP = list(e_map.values())[0]
    baseline_HR = list(e_hr.values())[0]
    baseline_CO = list(e_co.values())[0]
    baseline_BV = list(e_bv.values())[0]

    max_map_dev = max(abs(e_map[t] - r_map[t]) / baseline_MAP * 100 for t in common_t) if common_t else 0
    max_hr_dev = max(abs(e_hr[t] - r_hr[t]) / baseline_HR * 100 for t in common_t) if common_t else 0
    max_co_dev = max(abs(e_co[t] - r_co[t]) / baseline_CO * 100 for t in common_t) if common_t else 0
    max_bv_dev = max(abs(e_bv[t] - r_bv[t]) / baseline_BV * 100 for t in common_t) if common_t else 0

    threshold = 3.0  # %
    passed = all(d < threshold for d in [max_map_dev, max_hr_dev, max_co_dev, max_bv_dev])

    return WarmupVerification(
        max_HR_deviation=max_hr_dev,
        max_MAP_deviation=max_map_dev,
        max_CO_deviation=max_co_dev,
        max_BV_deviation=max_bv_dev,
        passed=passed,
        message=("PASS" if passed else "FAIL")
        + f" MAP={max_map_dev:.2f}% HR={max_hr_dev:.2f}% CO={max_co_dev:.2f}% BV={max_bv_dev:.2f}%",
    )


def _make_vc():
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc._cached_inputs.clear()
    return vc


def _record(vc: VirtualCreature, t: float) -> TimeSeriesPoint:
    # Unpack updates heart.circulating_volume_ml (Radau integrated)
    # blood.total_volume_ml is synced from heart in step() but not after unpack,
    # so we use heart.circulating_volume_ml for the correct tracked value
    # CO is computed directly from HR×SV since cardiac_output is a cached value
    # that is NOT updated by _unpack_unified_state (only HR,SV,SVR,BV are)
    CO = vc.heart.heart_rate * vc.heart.stroke_volume
    return TimeSeriesPoint(
        t=t,
        HR=vc.heart.heart_rate,
        MAP=vc.heart.mean_arterial_pressure,
        CO=CO,
        PaCO2=vc.blood.arterial_PCO2_mmHg,
        pH=vc.blood.arterial_pH,
        blood_volume_mL=vc.heart.circulating_volume_ml,
    )


def run_sequential_coupling(dt: float = 0.05) -> CouplingResult:
    vc = _make_vc()
    t0 = time_.perf_counter()
    total_steps = int(T_END / dt)

    vc._cached_inputs.clear()
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    # 连续 ODE 失血模型（与 Radau 实验使用相同的 sigmoid 模型）
    # 400mL 在 20s 内平滑失血，急性足以触发代偿、又不至于让 Radau 崩溃
    # width=5s：较宽的 sigmoid 上升沿保证 Radau Newton 迭代不崩溃
    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME, duration=20.0, width=2.0)

    initial = _record(vc, 0.0)
    time_series = [initial]

    try:
        for step_i in range(total_steps):
            vc.step()

            current_t = vc.current_time_s
            if step_i % int(DT_SAVE / dt) == 0:
                time_series.append(_record(vc, current_t))

        elapsed = time_.perf_counter() - t0

        ts = time_series
        map_vals = [p.MAP for p in ts]
        min_MAP = min(map_vals)
        min_MAP_t = ts[np.argmin(map_vals)].t if map_vals else None

        initial_MAP = initial.MAP
        target_low = initial_MAP * 0.90
        recover_t = None
        for p in ts:
            if p.t > min_MAP_t and p.MAP >= target_low:
                recover_t = p.t
                break

        return CouplingResult(
            method=f"Sequential (Euler dt={dt})",
            success=True, time_s=elapsed,
            time_series=time_series,
            initial_HR=initial.HR, initial_MAP=initial_MAP, initial_CO=initial.CO,
            min_MAP_after_shock=min_MAP,
            min_MAP_at_t=min_MAP_t,
            time_to_recover_MAP=recover_t,
            HR_at_30s=ts[min(15, len(ts)-1)].HR if len(ts) > 15 else None,
            MAP_at_30s=ts[min(15, len(ts)-1)].MAP if len(ts) > 15 else None,
            CO_at_30s=ts[min(15, len(ts)-1)].CO if len(ts) > 15 else None,
            message="Integration successful",
        )
    except Exception as e:
        elapsed = time_.perf_counter() - t0
        return CouplingResult(
            method=f"Sequential (Euler dt={dt})",
            success=False, time_s=elapsed,
            time_series=time_series,
            initial_HR=initial.HR, initial_MAP=initial.MAP, initial_CO=initial.CO,
            min_MAP_after_shock=None, min_MAP_at_t=None, time_to_recover_MAP=None,
            HR_at_30s=None, MAP_at_30s=None, CO_at_30s=None,
            message=str(e)[:120],
        )


def run_reference_coupling() -> CouplingResult:
    vc = _make_vc()

    vc._cached_inputs.clear()
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME, duration=20.0, width=2.0)

    initial = _record(vc, 0.0)

    t0 = time_.perf_counter()
    try:
        t_eval = np.arange(0.0, T_END + 1e-9, DT_SAVE)
        sol = solve_ivp(
            vc._unified_rhs, [0.0, T_END], y0,
            method="Radau",
            rtol=1e-10, atol=1e-12,
            t_eval=t_eval, dense_output=True,
            vectorized=False,
            max_step=0.1,
        )
        elapsed = time_.perf_counter() - t0

        if not sol.success:
            return CouplingResult(
                method="Ref (Radau rtol=1e-10)",
                success=False, time_s=elapsed,
                time_series=[initial],
                initial_HR=initial.HR, initial_MAP=initial.MAP, initial_CO=initial.CO,
                min_MAP_after_shock=None, min_MAP_at_t=None, time_to_recover_MAP=None,
                HR_at_30s=None, MAP_at_30s=None, CO_at_30s=None,
                message=sol.message[:120],
            )

        time_series = [initial]
        for i, t_val in enumerate(sol.t):
            vc._unpack_unified_state(sol.y[:, i])
            time_series.append(_record(vc, t_val))

        ts = time_series[1:]
        map_vals = [p.MAP for p in ts]
        min_MAP = min(map_vals)
        min_MAP_t = ts[np.argmin(map_vals)].t if map_vals else None

        initial_MAP = initial.MAP
        target_low = initial_MAP * 0.90
        recover_t = None
        for p in ts:
            if p.t > (min_MAP_t or 0) and p.MAP >= target_low:
                recover_t = p.t
                break

        return CouplingResult(
            method="Ref (Radau rtol=1e-10)",
            success=True, time_s=elapsed,
            time_series=time_series,
            initial_HR=initial.HR, initial_MAP=initial_MAP, initial_CO=initial.CO,
            min_MAP_after_shock=min_MAP,
            min_MAP_at_t=min_MAP_t,
            time_to_recover_MAP=recover_t,
            HR_at_30s=ts[min(15, len(ts)-1)].HR if len(ts) > 15 else None,
            MAP_at_30s=ts[min(15, len(ts)-1)].MAP if len(ts) > 15 else None,
            CO_at_30s=ts[min(15, len(ts)-1)].CO if len(ts) > 15 else None,
            message="Integration successful",
        )
    except Exception as e:
        elapsed = time_.perf_counter() - t0
        return CouplingResult(
            method="Ref (Radau rtol=1e-10)",
            success=False, time_s=elapsed,
            time_series=[initial],
            initial_HR=initial.HR, initial_MAP=initial.MAP, initial_CO=initial.CO,
            min_MAP_after_shock=None, min_MAP_at_t=None, time_to_recover_MAP=None,
            HR_at_30s=None, MAP_at_30s=None, CO_at_30s=None,
            message=str(e)[:120],
        )


def run_semi_implicit_coupling() -> CouplingResult:
    vc = _make_vc()

    vc._cached_inputs.clear()
    y0 = vc._pack_unified_state()
    _ = vc._unified_rhs(0.0, y0)

    # 连续 ODE 失血模型（替代 schedule_event，用于 Radau）
    # 400mL 在 300s（5min）内平滑失血，sigmoid 上升沿宽度=5s
    vc.set_blood_loss_scenario(t_onset=BLOOD_LOSS_TIME, total_ml=BLOOD_LOSS_VOLUME, duration=20.0, width=2.0)

    initial = _record(vc, 0.0)

    t0 = time_.perf_counter()
    try:
        t_eval = np.arange(0.0, T_END + 1e-9, DT_SAVE)
        sol = solve_ivp(
            vc._unified_rhs, [0.0, T_END], y0,
            method="Radau",
            rtol=1e-4, atol=1e-6,
            t_eval=t_eval, dense_output=True,
            vectorized=False,
            max_step=0.5,
        )
        elapsed = time_.perf_counter() - t0

        if not sol.success:
            return CouplingResult(
                method="Semi-implicit (Radau)",
                success=False, time_s=elapsed,
                time_series=[initial],
                initial_HR=initial.HR, initial_MAP=initial.MAP, initial_CO=initial.CO,
                min_MAP_after_shock=None, min_MAP_at_t=None, time_to_recover_MAP=None,
                HR_at_30s=None, MAP_at_30s=None, CO_at_30s=None,
                message=sol.message[:120],
            )

        time_series = [initial]
        for i, t_val in enumerate(sol.t):
            vc._unpack_unified_state(sol.y[:, i])
            time_series.append(_record(vc, t_val))

        ts = time_series[1:]
        map_vals = [p.MAP for p in ts]
        min_MAP = min(map_vals)
        min_MAP_t = ts[np.argmin(map_vals)].t if map_vals else None

        initial_MAP = initial.MAP
        target_low = initial_MAP * 0.90
        recover_t = None
        for p in ts:
            if p.t > (min_MAP_t or 0) and p.MAP >= target_low:
                recover_t = p.t
                break

        return CouplingResult(
            method="Semi-implicit (Radau)",
            success=True, time_s=elapsed,
            time_series=time_series,
            initial_HR=initial.HR, initial_MAP=initial_MAP, initial_CO=initial.CO,
            min_MAP_after_shock=min_MAP,
            min_MAP_at_t=min_MAP_t,
            time_to_recover_MAP=recover_t,
            HR_at_30s=ts[min(15, len(ts)-1)].HR if len(ts) > 15 else None,
            MAP_at_30s=ts[min(15, len(ts)-1)].MAP if len(ts) > 15 else None,
            CO_at_30s=ts[min(15, len(ts)-1)].CO if len(ts) > 15 else None,
            message="Integration successful",
        )
    except Exception as e:
        elapsed = time_.perf_counter() - t0
        return CouplingResult(
            method="Semi-implicit (Radau)",
            success=False, time_s=elapsed,
            time_series=[initial],
            initial_HR=initial.HR, initial_MAP=initial.MAP, initial_CO=initial.CO,
            min_MAP_after_shock=None, min_MAP_at_t=None, time_to_recover_MAP=None,
            HR_at_30s=None, MAP_at_30s=None, CO_at_30s=None,
            message=str(e)[:120],
        )


def run_all() -> dict:
    results = {}

    print("=== 耦合策略对比实验 — Figure 4 ===")
    print(f"场景：{WEIGHT_KG} kg 犬，t={BLOOD_LOSS_TIME} s 失血 {BLOOD_LOSS_VOLUME} mL")
    print()

    # Warm-up 验证：确认两条路径在失血前一致
    print("预热验证：无扰动运行 5s，检查两条路径偏差 <3%")
    wv = run_warmup_verification()
    results["warmup"] = wv
    print(f"  {wv.message}")
    if not wv.passed:
        print("  ⚠️  警告：预热偏差超过 3%，结果可能包含初始状态不稳定因素")

    print()
    print("实验 0：Ref 基线（Radau rtol=1e-10, atol=1e-12, max_step=0.1）")
    r_ref = run_reference_coupling()
    results["reference"] = r_ref
    status = "OK" if r_ref.success else "FAIL"
    print(f"  {status}  t={r_ref.time_s:.3f}s  {r_ref.message[:60]}")
    if r_ref.success:
        print(f"  初始：HR={r_ref.initial_HR:.1f}  MAP={r_ref.initial_MAP:.1f}  CO={r_ref.initial_CO:.0f}")
        print(f"  最低 MAP={r_ref.min_MAP_after_shock:.1f}（{r_ref.min_MAP_at_t:.1f}s 后）  恢复={r_ref.time_to_recover_MAP:.1f}s")

    print()
    print("实验 1：顺序耦合（Euler step loop，dt=0.05 s）")
    r_seq = run_sequential_coupling(dt=0.05)
    results["sequential"] = r_seq
    status = "OK" if r_seq.success else "FAIL"
    print(f"  {status}  t={r_seq.time_s:.3f}s  {r_seq.message[:60]}")
    if r_seq.success:
        print(f"  初始：HR={r_seq.initial_HR:.1f}  MAP={r_seq.initial_MAP:.1f}  CO={r_seq.initial_CO:.0f}")
        print(f"  最低 MAP={r_seq.min_MAP_after_shock:.1f}（{r_seq.min_MAP_at_t:.1f}s 后）  恢复={r_seq.time_to_recover_MAP:.1f}s")

    print()
    print("实验 1b：顺序耦合（Euler dt=0.01 s）")
    r_seq2 = run_sequential_coupling(dt=0.01)
    results["sequential_dt001"] = r_seq2
    status = "OK" if r_seq2.success else "FAIL"
    print(f"  {status}  t={r_seq2.time_s:.3f}s  {r_seq2.message[:60]}")
    if r_seq2.success:
        print(f"  初始：HR={r_seq2.initial_HR:.1f}  MAP={r_seq2.initial_MAP:.1f}  CO={r_seq2.initial_CO:.0f}")
        print(f"  最低 MAP={r_seq2.min_MAP_after_shock:.1f}（{r_seq2.min_MAP_at_t:.1f}s 后）  恢复={r_seq2.time_to_recover_MAP:.1f}s")

    print()
    print("实验 1b：顺序耦合（Euler dt=0.10 s）")
    r_seq3 = run_sequential_coupling(dt=0.10)
    results["sequential_dt010"] = r_seq3
    status = "OK" if r_seq3.success else "FAIL"
    print(f"  {status}  t={r_seq3.time_s:.3f}s  {r_seq3.message[:60]}")
    if r_seq3.success:
        print(f"  初始：HR={r_seq3.initial_HR:.1f}  MAP={r_seq3.initial_MAP:.1f}  CO={r_seq3.initial_CO:.0f}")
        print(f"  最低 MAP={r_seq3.min_MAP_after_shock:.1f}（{r_seq3.min_MAP_at_t:.1f}s 后）  恢复={r_seq3.time_to_recover_MAP:.1f}s")

    print()
    print("实验 1c：顺序耦合（Euler dt=0.001 s，精细对照组）")
    r_seq4 = run_sequential_coupling(dt=0.001)
    results["sequential_dt0001"] = r_seq4
    status = "OK" if r_seq4.success else "FAIL"
    print(f"  {status}  t={r_seq4.time_s:.3f}s  {r_seq4.message[:60]}")
    if r_seq4.success:
        print(f"  初始：HR={r_seq4.initial_HR:.1f}  MAP={r_seq4.initial_MAP:.1f}  CO={r_seq4.initial_CO:.0f}")
        rec_str = f"{r_seq4.time_to_recover_MAP:.1f}s" if r_seq4.time_to_recover_MAP is not None else "N/A"
        print(f"  最低 MAP={r_seq4.min_MAP_after_shock:.1f}（{r_seq4.min_MAP_at_t:.1f}s 后）  恢复={rec_str}")

    print()
    print("实验 2：半隐式耦合（Radau + cached_inputs）")
    r_semi = run_semi_implicit_coupling()
    results["semi_implicit"] = r_semi
    status = "OK" if r_semi.success else "FAIL"
    print(f"  {status}  t={r_semi.time_s:.3f}s  {r_semi.message[:60]}")
    if r_semi.success:
        print(f"  初始：HR={r_semi.initial_HR:.1f}  MAP={r_semi.initial_MAP:.1f}  CO={r_semi.initial_CO:.0f}")
        print(f"  最低 MAP={r_semi.min_MAP_after_shock:.1f}（{r_semi.min_MAP_at_t:.1f}s 后）  恢复={r_semi.time_to_recover_MAP:.1f}s")

    return results


if __name__ == "__main__":
    data = run_all()

    # Compute panel (d) data: L∞ + L2 + steady-state error vs reference
    ref_ts = data["reference"].time_series
    ref_map_by_t = {p.t: p.MAP for p in ref_ts}

    panel_d = []
    for key in ["reference", "semi_implicit", "sequential", "sequential_dt001",
                "sequential_dt010", "sequential_dt0001"]:
        if key not in data:
            continue
        r = data[key]
        if not r.success or not r.time_series:
            continue
        max_dev = 0.0
        mse_sum = 0.0
        n = 0
        steady_err = None
        for p in r.time_series:
            if p.t in ref_map_by_t:
                dev = abs(p.MAP - ref_map_by_t[p.t])
                if dev > max_dev:
                    max_dev = dev
                mse_sum += dev ** 2
                n += 1
                if p.t == 60.0:
                    steady_err = dev
        rmse = np.sqrt(mse_sum / n) if n > 0 else None
        panel_d.append({
            "method": r.method,
            "time_s": r.time_s,
            "max_MAP_deviation": max_dev,       # L∞ 范数
            "rmse_MAP": rmse,                     # L2 范数（新增）
            "steady_state_error": steady_err,    # t=60s 稳态偏差（新增）
        })

    out_path = os.path.join(_EXPERIMENTS_DIR, "coupling_comparison_data.json")
    serializable = {}

    # Warmup 单独序列化
    wv = data["warmup"]
    serializable["warmup"] = {
        "max_HR_deviation": wv.max_HR_deviation,
        "max_MAP_deviation": wv.max_MAP_deviation,
        "max_CO_deviation": wv.max_CO_deviation,
        "max_BV_deviation": wv.max_BV_deviation,
        "passed": wv.passed,
        "message": wv.message,
    }

    for k, r in data.items():
        if k == "warmup" or not isinstance(r, CouplingResult):
            continue
        d = {
            "method": r.method,
            "success": r.success,
            "time_s": r.time_s,
            "initial_HR": r.initial_HR,
            "initial_MAP": r.initial_MAP,
            "initial_CO": r.initial_CO,
            "min_MAP_after_shock": r.min_MAP_after_shock,
            "min_MAP_at_t": r.min_MAP_at_t,
            "time_to_recover_MAP": r.time_to_recover_MAP,
            "HR_at_30s": r.HR_at_30s,
            "MAP_at_30s": r.MAP_at_30s,
            "CO_at_30s": r.CO_at_30s,
            "message": r.message,
            "time_series": [
                {"t": p.t, "HR": p.HR, "MAP": p.MAP, "CO": p.CO,
                 "PaCO2": p.PaCO2, "pH": p.pH, "blood_volume_mL": p.blood_volume_mL}
                for p in r.time_series
            ],
        }
        serializable[k] = d
    serializable["panel_d"] = panel_d

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(serializable, f, indent=2, ensure_ascii=False)
    print(f"\n数据已保存 → {out_path}")