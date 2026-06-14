"""
state_vector.py — unified ODE state packing / unpacking / RHS.

- Step 1 (solver-refactor-roadmap-v3): pure code-motion extraction from
  `src/simulation.py`. Zero behavior change.
- Step 2: declaration-driven pack/unpack. Each organ module now declares its
  own `STATE_VARS = (("ode_name", "attr_name"), ...)` class attribute (sibling
  to the existing INPUTS/OUTPUTS contract in `src/organs/contracts.py`). The
  legacy central table's per-module `var_names` lists and the ~80-line
  if/elif chains in pack/unpack are gone — adding an ODE state var is now a
  1-place edit on the module. Bit-identical to the legacy y-vector (verified
  by direct array_equal + twin-run).

These four functions implement the "how to pack/unpack the unified y-vector
and evaluate its right-hand side" concern, decoupled from "how to integrate
it" (which stays in `solvers.py` / `simulation._step_*`). Step 3 of the
roadmap (Radau → `src/engine/solvers/radau.py`) builds on this seam.

Mirrors the style of `step_common.py`: module-level functions taking the
engine instance as the first argument. `VirtualCreature` keeps thin wrapper
methods (same names) for backward compatibility with the 70+ references in
`experiments/` and `tools/`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from src.engine.topology import CONNECTIONS

if TYPE_CHECKING:
    from src.simulation import VirtualCreature


# ── 模块注册（Step 2: 瘦身为 2-tuple）──────────────────────────────────
# Each entry is (module_name, engine_attr) — i.e. the logical module name
# used in CONNECTIONS / state_map keys, and the engine instance attribute
# that holds the module object. The state-variable surface itself is now
# declared by each module via its own `STATE_VARS` class attribute (see
# src/organs/contracts.py for the sibling INPUTS/OUTPUTS pattern), so adding
# an ODE state var is a 1-place edit on the module, not a 3-place edit here.
#
# Backward compat: VirtualCreature._UNIFIED_MODULES aliases this list. The
# legacy 3-tuple shape (name, var_names, attr) is gone — verified no callers
# unpack the 3-tuple form (grep: only this file did, all rewritten below).
UNIFIED_MODULES = [
    # module_name, engine_attr
    ("heart",       "heart"),
    ("lung",        "lung"),
    ("kidney",      "kidney"),
    ("fluid",       "fluid"),
    ("gut",         "gut"),
    ("liver",       "liver"),
    ("endocrine",   "endocrine"),
    ("neuro",       "neuro"),
    ("immune",      "immune"),
    ("coagulation", "coagulation"),
    ("lymphatic",   "lymphatic"),
]


def _iter_state_modules(engine: "VirtualCreature"):
    """Yield (module_name, module_instance) for every registered module."""
    for mname, attr in UNIFIED_MODULES:
        yield mname, getattr(engine, attr)


def build_state_map(engine: "VirtualCreature") -> dict[tuple[str, str], int]:
    """建立 (module_name, ode_name) → y-array index 映射表（器官 + 疾病）。

    Step 2: state-variable names now come from each module's STATE_VARS
    declaration (not a central var_names list). The ode_name in each
    STATE_VARS tuple is the key — identical to the legacy var_names, so the
    resulting state_map (and thus the y-vector layout) is bit-identical.
    """
    state_map: dict[tuple[str, str], int] = {}
    idx = 0

    # 器官状态变量 — 读各模块的 STATE_VARS 声明
    for mname, module in _iter_state_modules(engine):
        for ode_name, _attr in module.STATE_VARS:
            state_map[(mname, ode_name)] = idx
            idx += 1

    # 疾病状态变量
    if engine.disease is not None and hasattr(engine.disease, '_state_vars'):
        for vname in engine.disease._state_vars:
            state_map[("disease", vname)] = idx
            idx += 1

    return state_map


def pack_state(engine: "VirtualCreature") -> np.ndarray:
    """将所有器官 + 疾病状态打包成 numpy 向量 y0。

    Step 2: declaration-driven. Reads each module's STATE_VARS
    `(ode_name, attr_name)` tuples and pulls values via getattr — the ~70-line
    if/elif chain is gone. Output is bit-identical to the legacy implementation
    (verified by twin-run + direct array_equal test).
    """
    state_map = build_state_map(engine)
    y0 = np.zeros(len(state_map))

    # 器官状态 — 从各模块 STATE_VARS 声明读取
    for mname, module in _iter_state_modules(engine):
        for ode_name, attr_name in module.STATE_VARS:
            y0[state_map[(mname, ode_name)]] = getattr(module, attr_name)

    # 疾病状态
    if engine.disease is not None and hasattr(engine.disease, '_state_vars'):
        for vname in engine.disease._state_vars:
            idx = state_map[("disease", vname)]
            y0[idx] = engine.disease._state_vars[vname]

    return y0


def unpack_state(engine: "VirtualCreature", y: np.ndarray) -> None:
    """将 numpy 向量 y 分解到各模块的实例属性。

    Step 2: declaration-driven. Writes via setattr from each module's
    STATE_VARS tuples — the ~80-line if/elif chain (including heart's MAP
    side-effect) is gone. Heart's MAP re-sync now lives in
    HeartModule._post_unpack_state (extracted verbatim), invoked here via the
    optional hook protocol after the module's STATE_VARS are written.
    """
    state_map = build_state_map(engine)

    for mname, module in _iter_state_modules(engine):
        for ode_name, attr_name in module.STATE_VARS:
            setattr(module, attr_name, y[state_map[(mname, ode_name)]])
        # Optional post-unpack hook (currently only heart: re-syncs MAP from
        # the just-unpacked HR/SV/SVR/blood_volume). Must run AFTER all of a
        # module's STATE_VARS are written.
        hook = getattr(module, "_post_unpack_state", None)
        if hook is not None:
            hook()

    # 疾病状态
    if engine.disease is not None and hasattr(engine.disease, '_state_vars'):
        for vname in engine.disease._state_vars:
            idx = state_map[("disease", vname)]
            engine.disease._state_vars[vname] = y[idx]


def unified_rhs(engine: "VirtualCreature", t: float, y: np.ndarray) -> np.ndarray:
    """
    统一 ODE 右端函数（供 solve_ivp Radau 调用）。

    ── 半隐式 Gauss-Seidel 耦合策略 ──────────────────────────────────────
    这是 engine 的**积分环内**（intra-step）数据流，与 Euler 路径的**步后**
    CouplingEngine（post-step 规则引擎）是**两套不同语义的耦合机制**——见
    docs/coupling_inventory.md 的完整对比。

    Gauss-Seidel 半隐式要点：
    - 每次 rhs(t, y) 调用时，各模块的 derivatives() **只读 `_cached_inputs`**
      （上一次 rhs 调用的 outputs 经 CONNECTIONS 表路由的结果），**不读**
      其他模块的当前实例状态。
    - 模块按固定顺序求导（heart → lung → kidney → ... → fluid），每个模块
      的 outputs 立即可被本调用内更靠后的模块消费（如 gut 的输出直接喂给
      liver）——这是 Gauss-Seidel 顺序松驰的本质。
    - solve_ivp(Radau) 的 Newton 迭代会反复调 rhs：每次调用都更新
      `_cached_inputs`，子迭代间 inputs 逐步收敛，最终到达耦合不动点。
      这是为什么半隐式格式能与隐式 Radau 配合——Newton 不需要显式 Jacobian
      of the coupling，靠函数值迭代即可收敛。

    ── 数据流 ──────────────────────────────────────────────────────────
    1. （连续失血 sigmoid 计算）
    2. 解包 y → 模块实例属性（unpack_state）
    3. 初始化 module_inputs = copy(_cached_inputs)；all_outputs = {}
    4. 按固定顺序调各模块 derivatives(dt, **inputs_from_cache) → (dydt, outputs)
       - gut 的 outputs 直接作为 liver 的 gut_state 入参（intra-call 直传）
       - 其余跨模块依赖通过 CONNECTIONS 在本调用末尾路由到 _cached_inputs
    5. 按 CONNECTIONS 表路由 all_outputs → _cached_inputs（供下次 rhs 用）
       注：src_var 命名不匹配的条目被 `if val is not None` 静默跳过
       （见 docs/coupling_inventory.md 的 dead routes 清单）
    6. 打包 module_dydt → numpy 向量返回（用 derivatives 的 dydt，非 outputs）

    ── 已知限制 ─────────────────────────────────────────────────────────
    - **H20**：`_cached_inputs` 在 Newton 子迭代间会变，"上一次输出"的语义
      因此松散（取决于 solve_ivp 的内部子步策略）。当前可接受——Radau 的
      自适应步长会限制子迭代幅度。
    - **覆盖差异**：CONNECTIONS 只在 Radau 路径生效；Euler 路径用
      CouplingEngine + data/coupling_rules.json。两套机制覆盖的耦合关系
      **不同**（如 heart.cardiac_output→kidney 只在 CONNECTIONS；
      RAAS→SVR 只在 CouplingEngine）。详见 docs/coupling_inventory.md。
    """
    # 1. 连续失血模型（sigmoid，用于 Radau 积分路径）
    # 与 step() 里的公式保持一致：bell curve = sigmoid_on × (1 - sigmoid_off)
    blood_loss_rate_ml_s = 0.0
    if engine._blood_loss_config is not None:
        cfg = engine._blood_loss_config
        t_rel = t - cfg["t_onset"]
        if t_rel >= 0:
            sigmoid_on = 1.0 / (1.0 + np.exp(-t_rel / cfg["width"]))
            t_fall = t_rel - 3 * cfg["width"]
            sigmoid_off = 1.0 / (1.0 + np.exp(-t_fall / cfg["width"]))
            blood_loss_rate_ml_s = cfg["k"] * sigmoid_on * (1.0 - sigmoid_off)

    # 2. 解包状态
    unpack_state(engine, y)

    # 3. 准备各模块的 inputs（用 cached 值 + 当前输出填充）
    all_outputs: dict[str, dict[str, float]] = {}
    module_inputs: dict[str, dict] = {}

    # 初始化 inputs 为 cached_inputs（上一调用输出的值）
    for mname, _attr in UNIFIED_MODULES:
        module_inputs[mname] = dict(engine._cached_inputs.get(mname, {}))
        all_outputs[mname] = {}

    # 3a. 第一批：不需要其他模块输出作为输入的模块
    # 所有模块的 derivatives（用 time-constant 参数 dt，别用 _USE_DT）
    # dydt 收集到 module_dydt（用于打包 return dydt_vec）
    # outputs 收集到 all_outputs（用于 CONNECTIONS 路由和供其他模块调用）
    # 注：这里 dt 用于低通滤波时间常数的计算。
    # H6 fix: 使用 engine.dt（物理步长）代替硬编码的 0.01，
    # 使 chemoreceptor 低通滤波（τ=30s）的时间常数与实际步长一致。
    # Radau 积分器自己管理步长，不受这里 dt 值影响。
    _USE_DT = engine.dt
    module_dydt: dict[str, dict] = {}

    # 心脏 — 传入当前失血率（用于 blood_volume dydt）
    module = getattr(engine, "heart")
    dydt, outputs = module.derivatives(dt=_USE_DT, svr_factor=1.0,
                                        blood_loss_rate_ml_s=blood_loss_rate_ml_s)
    module_dydt["heart"] = dydt
    all_outputs["heart"] = outputs

    # 肺部 — co_input 从缓存
    module = getattr(engine, "lung")
    co_input = module_inputs.get("lung", {}).get("co_input")
    dydt, outputs = module.derivatives(dt=_USE_DT, co_input=co_input)
    module_dydt["lung"] = dydt
    all_outputs["lung"] = outputs

    # 肾脏 — 三个必需位置参数都从缓存
    module = getattr(engine, "kidney")
    kidney_in = module_inputs.get("kidney", {})
    dydt, outputs = module.derivatives(
        dt=_USE_DT,
        map_input=kidney_in.get("map_input", 90.0),
        cvp_input=kidney_in.get("cvp_input", 5.0),
        co_input=kidney_in.get("co_input", 1500.0),
    )
    module_dydt["kidney"] = dydt
    all_outputs["kidney"] = outputs

    # 肠道 — co_input 从缓存；输出是 gut_state dict，存入 all_outputs["gut"]
    module = getattr(engine, "gut")
    gut_in = module_inputs.get("gut", {})
    dydt, gut_gut_outputs = module.derivatives(dt=_USE_DT, co_input=gut_in.get("co_input", 1500.0))
    module_dydt["gut"] = dydt
    all_outputs["gut"] = gut_gut_outputs

    # 肝脏 — co_input 从缓存，gut_state 取自肠道输出
    module = getattr(engine, "liver")
    liver_in = module_inputs.get("liver", {})
    dydt, outputs = module.derivatives(
        dt=_USE_DT,
        co_input=liver_in.get("co_input", 1500.0),
        gut_state=gut_gut_outputs,  # 肠道输出作为 liver 的输入
    )
    module_dydt["liver"] = dydt
    all_outputs["liver"] = outputs

    # 内分泌 — 无外部输入
    module = getattr(engine, "endocrine")
    dydt, outputs = module.derivatives(dt=0.0)
    module_dydt["endocrine"] = dydt
    all_outputs["endocrine"] = outputs

    # 神经 — map_input, lung_rr 从缓存
    module = getattr(engine, "neuro")
    neuro_in = module_inputs.get("neuro", {})
    dydt, outputs = module.derivatives(
        dt=_USE_DT,
        map_input=neuro_in.get("map_input", 90.0),
        heart_hr=neuro_in.get("heart_rate_bpm", 80.0),
        lung_rr=neuro_in.get("lung_rr", 15.0),
    )
    module_dydt["neuro"] = dydt
    all_outputs["neuro"] = outputs

    # 免疫 — endocrine_cortisol 从缓存
    module = getattr(engine, "immune")
    immune_in = module_inputs.get("immune", {})
    dydt, outputs = module.derivatives(
        dt=_USE_DT,
        endocrine_cortisol=immune_in.get("endocrine_cortisol"),
    )
    module_dydt["immune"] = dydt
    all_outputs["immune"] = outputs

    # 凝血 — liver_health_factor, immune_cytokine 从缓存
    module = getattr(engine, "coagulation")
    coag_in = module_inputs.get("coagulation", {})
    dydt, outputs = module.derivatives(
        dt=_USE_DT,
        liver_health_factor=coag_in.get("liver_health_factor", 1.0),
        immune_cytokine=coag_in.get("immune_cytokine", 0.0),
    )
    module_dydt["coagulation"] = dydt
    all_outputs["coagulation"] = outputs

    # 淋巴 — map_input, hr_input, cytokine_input, gut_fat_absorption
    module = getattr(engine, "lymphatic")
    lymph_in = module_inputs.get("lymphatic", {})
    dydt, outputs = module.derivatives(
        dt=_USE_DT,
        map_input=lymph_in.get("map_input", 80.0),
        hr_input=lymph_in.get("hr_input", 80.0),
        cytokine_input=lymph_in.get("cytokine_input", 0.0),
        gut_fat_absorption=lymph_in.get("gut_fat_absorption", False),
    )
    module_dydt["lymphatic"] = dydt
    all_outputs["lymphatic"] = outputs

    # 体液 — map_input 从缓存
    module = getattr(engine, "fluid")
    fluid_in = module_inputs.get("fluid", {})
    dydt, outputs = module.derivatives(dt=0.0, map_input=fluid_in.get("map_input"))
    module_dydt["fluid"] = dydt
    all_outputs["fluid"] = outputs

    # 疾病
    if engine.disease is not None and hasattr(engine.disease, 'compute_derivatives'):
        engine_state = engine._get_engine_state()
        disease_dydt = engine.disease.compute_derivatives(engine_state)
        all_outputs["disease"] = disease_dydt

    # 4. 按 CONNECTIONS 表路由 outputs → cached inputs（供下次 rhs 调用用）
    for (src_mod, src_var), targets in CONNECTIONS.items():
        val = all_outputs.get(src_mod, {}).get(src_var)
        if val is not None:
            for (tgt_mod, tgt_var) in targets:
                if tgt_mod not in engine._cached_inputs:
                    engine._cached_inputs[tgt_mod] = {}
                engine._cached_inputs[tgt_mod][tgt_var] = val

    # ── 5. 打包 dydt — 使用各模块 derivatives() 返回的 dydt（而非 outputs）
    # blood_volume 的 dydt 现在由 heart.derivatives() 直接提供（blood_loss_rate_ml_s）
    # Radau 通过 y 向量积分 blood_volume 状态变量，不再需要外部应用
    state_map = build_state_map(engine)
    n = len(state_map)
    dydt_vec = np.zeros(n)

    for (mname, vname), idx in state_map.items():
        if mname == "disease":
            dydt_vec[idx] = module_dydt.get("disease", {}).get(vname, 0.0)
        else:
            dydt_vec[idx] = module_dydt.get(mname, {}).get(vname, 0.0)

    return dydt_vec
