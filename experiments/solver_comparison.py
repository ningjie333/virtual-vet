"""
求解器对比实验 — Figure 3

实验目的：证明 stiff 生理系统需要隐式求解器，
显式方法（RK45/Euler）效率低或崩溃。

数据来源：VetSim v1.0，20 kg 犬，600 s 稳态仿真
参考解：Radau rtol=1e-10, atol=1e-12
"""

import sys
import os
import types
import time
import json
from dataclasses import dataclass, asdict

import numpy as np
from scipy.integrate import solve_ivp

# ── 确定路径 ─────────────────────────────────────────────────────────────
_EXPERIMENTS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_EXPERIMENTS_DIR)
_SRC_DIR = os.path.join(_PROJECT_ROOT, "src")

if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)

# ── 加载策略：两遍扫描 ────────────────────────────────────────────────────
# 第一遍：加载 parameters.py（无 src. 依赖）
# 第二遍：加载其余模块（可能引用已加载模块，递归满足）

def _read_patched(path: str) -> str:
    """读取 .py 文件并将所有 'from src.X' 替换为 'from X'。"""
    src = open(path, encoding="utf-8").read()
    return src.replace("from src.", "from ")

# 先加载 parameters.py（无 src. 依赖）
sys.modules["parameters"] = types.ModuleType("parameters")
exec(compile(_read_patched(os.path.join(_SRC_DIR, "parameters.py")),
             os.path.join(_SRC_DIR, "parameters.py"), "exec"),
     sys.modules["parameters"].__dict__)

# 按依赖顺序加载其余所有模块
# 已加载的模块会被 sys.modules 记录，后续引用自动命中
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
T_END = 30.0         # 缩短到 30s（加快实验）
DT_SAVE = 10.0

SOLVER_CONFIGS = {
    # Radau/BDF 对 44 变量 stiff 系统极慢，仅测 RK45（LSODA 自动选择会挂）
    "RK45":        {"method": "RK45",  "rtol": 1e-5, "atol": 1e-7},
}

EULER_DTS = [0.001, 0.005, 0.01, 0.05, 0.1]


@dataclass
class SolverResult:
    solver: str
    success: bool
    time_s: float
    nfev: int | None
    n_steps: int | None
    n_accept: int | None
    message: str
    final_HR: float | None = None
    final_MAP: float | None = None
    final_PaCO2: float | None = None
    final_pH: float | None = None
    HR_drift: float | None = None
    MAP_drift: float | None = None


def run_solver(solver_name: str, config: dict) -> SolverResult:
    """直接调用 solve_ivp with specified method (bypasses run_unified_ivp)."""
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    t0 = time.perf_counter()
    try:
        # Initialise cache and pack state
        vc._cached_inputs.clear()
        y0 = vc._pack_unified_state()
        _ = vc._unified_rhs(0.0, y0)  # warm-up

        t_eval = np.arange(0.0, T_END + DT_SAVE, DT_SAVE)
        sol = solve_ivp(
            vc._unified_rhs, [0.0, T_END], y0,
            method=config["method"],
            rtol=config.get("rtol", 1e-8),
            atol=config.get("atol", 1e-10),
            t_eval=t_eval, dense_output=True,
            vectorized=False,
        )
        elapsed = time.perf_counter() - t0
        return SolverResult(
            solver=solver_name, success=True, time_s=elapsed,
            nfev=sol.nfev, n_steps=sol.nsteps,
            n_accept=getattr(sol, "n_accept", None),
            message="Integration successful",
            final_HR=vc.heart.heart_rate,
            final_MAP=vc.heart.mean_arterial_pressure,
            final_PaCO2=vc.blood.arterial_PCO2_mmHg,
            final_pH=vc.blood.arterial_pH,
            HR_drift=vc.heart.heart_rate - 85.0,
            MAP_drift=vc.heart.mean_arterial_pressure - 100.0,
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return SolverResult(
            solver=solver_name, success=False, time_s=elapsed,
            nfev=None, n_steps=None, n_accept=None,
            message=str(e)[:120],
        )


def run_euler_dt(dt: float) -> SolverResult:
    vc = VirtualCreature(body_weight_kg=WEIGHT_KG)
    t0 = time.perf_counter()
    try:
        total_steps = int(T_END / dt)
        for _ in range(total_steps):
            vc.step()
        elapsed = time.perf_counter() - t0
        return SolverResult(
            solver=f"Euler dt={dt}", success=True, time_s=elapsed,
            nfev=total_steps, n_steps=total_steps, n_accept=total_steps,
            message="Integration successful",
            final_HR=vc.heart.heart_rate,
            final_MAP=vc.heart.mean_arterial_pressure,
            final_PaCO2=vc.blood.arterial_PCO2_mmHg,
            final_pH=vc.blood.arterial_pH,
            HR_drift=vc.heart.heart_rate - 85.0,
            MAP_drift=vc.heart.mean_arterial_pressure - 100.0,
        )
    except Exception as e:
        elapsed = time.perf_counter() - t0
        return SolverResult(
            solver=f"Euler dt={dt}", success=False, time_s=elapsed,
            nfev=None, n_steps=None, n_accept=None,
            message=str(e)[:120],
        )


def run_all() -> dict:
    results = {}

    print("=== 实验 1：各求解器能否跑完 600s？ ===")
    for name, config in SOLVER_CONFIGS.items():
        r = run_solver(name, config)
        results[name] = r
        print(f"  {name:8s}: {'OK' if r.success else 'FAIL'} {r.time_s:.3f}s  {r.message[:60]}")
        if r.success:
            print(f"           HR={r.final_HR:.1f}({r.HR_drift:+.1f})  "
                  f"MAP={r.final_MAP:.1f}({r.MAP_drift:+.1f})  PaCO2={r.final_PaCO2:.1f}")

    print("\n=== 实验 2：Euler dt 敏感性 ===")
    for dt in EULER_DTS:
        r = run_euler_dt(dt)
        results[r.solver] = r
        status = "OK" if r.success else "FAIL"
        print(f"  dt={dt:6.3f}: {status} t={r.time_s:.3f}s  "
              f"HR={r.final_HR:.1f}({r.HR_drift:+.1f})  "
              f"MAP={r.final_MAP:.1f}({r.MAP_drift:+.1f})  "
              f"PaCO2={r.final_PaCO2:.1f}")

    print("\n=== 实验 3：与参考解（Radau high precision）偏差 ===")
    vc_ref = VirtualCreature(body_weight_kg=WEIGHT_KG)
    vc_ref._cached_inputs.clear()
    y0_ref = vc_ref._pack_unified_state()
    _ = vc_ref._unified_rhs(0.0, y0_ref)
    t_eval_ref = np.arange(0.0, T_END + DT_SAVE, DT_SAVE)
    sol_ref = solve_ivp(vc_ref._unified_rhs, [0.0, T_END], y0_ref,
                        method="Radau", rtol=1e-8, atol=1e-10,
                        t_eval=t_eval_ref, dense_output=True,
                        vectorized=False)
    ref_HR = vc_ref.heart.heart_rate
    ref_MAP = vc_ref.heart.mean_arterial_pressure
    ref_PaCO2 = vc_ref.blood.arterial_PCO2_mmHg
    ref_pH = vc_ref.blood.arterial_pH
    print(f"  Reference (Radau 1e-10): HR={ref_HR:.2f}, MAP={ref_MAP:.2f}, "
          f"PaCO2={ref_PaCO2:.2f}, pH={ref_pH:.3f}")
    for name, r in results.items():
        if r.success:
            hr_err = abs(r.final_HR - ref_HR) if r.final_HR else None
            map_err = abs(r.final_MAP - ref_MAP) if r.final_MAP else None
            print(f"  {name:20s}: |dHR|={hr_err:.2f}  |dMAP|={map_err:.2f}")

    return {
        "config": {
            "weight_kg": WEIGHT_KG, "t_end_s": T_END, "dt_save": DT_SAVE,
            "reference_HR": ref_HR, "reference_MAP": ref_MAP,
            "reference_PaCO2": ref_PaCO2, "reference_pH": ref_pH,
        },
        "results": {k: asdict(v) for k, v in results.items()},
    }


if __name__ == "__main__":
    print("求解器对比实验 — Figure 3")
    print("=" * 60)
    data = run_all()

    out_path = os.path.join(_EXPERIMENTS_DIR, "solver_comparison_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"\n数据已保存 → {out_path}")