"""
ConfigDrivenDiseaseModule — 配置驱动通用疾病 ODE 引擎。

从 data/ode_diseases.json 读取疾病定义，自动执行 ODE 求解 + FactorCommand 输出。
新增疾病只需在 JSON 中添加配置，无需编写 Python 类。

ODE 类型（内置）:
  - logistic:      dS/dt = rate * S * (1 - S/K) + seed_boost
  - algebraic:     S = fn(其他状态变量) — 纯代数映射
  - first_order_lag: dS/dt = (target - S) / tau
  - custom:        dS/dt = derivative_fn(状态变量, params)

扩展点:
  register_ode_type(name, solver_fn) — 注册自定义 ODE 求解器。
  solver_fn 签名: (state_var_value, params, state_vars, engine_state, dt) -> new_value
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Callable

from . import DiseaseModule, register_disease
from ..config_validation import validate_ode_diseases, ValidationError
from ..simulation import FactorCommand
from ..logger_config import get_logger

logger = get_logger(__name__)

# ── ODE 求解器注册表 ----------------------------------------------------------
_ODE_SOLVERS: dict[str, Callable] = {}


def register_ode_type(name: str, solver: Callable) -> None:
    """注册自定义 ODE 求解器。"""
    _ODE_SOLVERS[name] = solver
    logger.debug("Registered custom ODE solver: %s", name)


def _clamp(value: float, lo: float | None, hi: float | None) -> float:
    if lo is not None and value < lo:
        return lo
    if hi is not None and value > hi:
        return hi
    return value


def _compile_expr(fn_str: str):
    """预编译表达式字符串为 code 对象，加速重复求值。"""
    try:
        return compile(fn_str, "<expr>", "eval")
    except (SyntaxError, ValueError) as e:
        logger.error("Expression compile failed: '%s' → %s", fn_str, e)
        return None


_SAFE_BUILTINS = {"min": min, "max": max, "abs": abs, "clamp": _clamp}


def _ns(state_vars: dict, params: dict, engine_state: dict) -> dict:
    """构建求值命名空间，排除 code 对象和内部字段。"""
    merged = {**state_vars, **params, "engine": engine_state}
    return {k: v for k, v in merged.items() if not hasattr(v, "co_code")}


def _eval_fn(code, namespace: dict) -> float:
    """求值预编译的表达式 code 对象。"""
    if code is None:
        return 0.0
    try:
        return float(eval(code, {"__builtins__": _SAFE_BUILTINS}, namespace))
    except Exception as e:
        logger.error("Expression eval failed → %s", e)
        return 0.0


# ── 内置 ODE 导数求解器（Phase 2: 供 solve_ivp 调用）───────────────────────────
# 这些函数只返回导数，不做时间推进。
# 引擎层统一由 scipy.integrate.solve_ivp(method='Radau') 调用。
_DERIVATIVE_SOLVERS: dict[str, Callable] = {}


def _register_derivative_solvers() -> None:
    """注册导数求解器（供 compute_derivatives() 使用）。"""
    global _DERIVATIVE_SOLVERS

    def _deriv_logistic(value, params, state_vars, engine_state):
        rate = params.get("rate", 0.0)
        K = params.get("K", 1.0)
        growth = rate * value * (1.0 - value / K) if K > 0 else 0.0
        threshold = params.get("seed_threshold", 0.0)
        if value < threshold:
            seed_boost = params.get("seed_boost", 0.0)
            code = params.get("seed_boost_fn")
            if code is not None:
                namespace = _ns(state_vars, params, engine_state)
                seed_boost = _eval_fn(code, namespace)
            growth += seed_boost
        return growth

    def _deriv_algebraic(value, params, state_vars, engine_state):
        return 0.0  # 在 compute_derivatives() 里单独处理

    def _deriv_first_order_lag(value, params, state_vars, engine_state):
        tau = params.get("tau", 1.0)
        if tau <= 0:
            return 0.0
        namespace = _ns(state_vars, params, engine_state)
        if params.get("target_source") == "engine":
            target = _eval_fn(params.get("target_fn"), namespace)
        elif "target_fn" in params and params["target_fn"] is not None:
            target = _eval_fn(params["target_fn"], namespace)
        else:
            target = params.get("target", 0.0)
        return (target - value) / tau

    def _deriv_custom(value, params, state_vars, engine_state):
        code = params.get("derivative_fn")
        namespace = _ns(state_vars, params, engine_state)
        return _eval_fn(code, namespace)

    _DERIVATIVE_SOLVERS = {
        "logistic": _deriv_logistic,
        "algebraic": _deriv_algebraic,
        "first_order_lag": _deriv_first_order_lag,
        "custom": _deriv_custom,
    }


_register_derivative_solvers()


# ── 内置 ODE 求解器（向后兼容：compute() 使用 Euler 推进）───────────────────

def _solve_logistic(
    value: float, params: dict, state_vars: dict, engine_state: dict, dt: float
) -> float:
    """logistic 增长: dS/dt = rate * S * (1 - S/K) + seed_boost"""
    rate = params.get("rate", 0.0)
    K = params.get("K", 1.0)
    growth = rate * value * (1.0 - value / K) if K > 0 else 0.0
    threshold = params.get("seed_threshold", 0.0)
    if value < threshold:
        seed_boost = params.get("seed_boost", 0.0)
        code = params.get("seed_boost_fn")
        if code is not None:
            namespace = _ns(state_vars, params, engine_state)
            seed_boost = _eval_fn(code, namespace)
        growth += seed_boost
    new_val = value + growth * dt
    lo = params.get("_clamp_lo", 0.0)
    hi = params.get("_clamp_hi", 1.0)
    return _clamp(new_val, lo, hi)


def _solve_algebraic(
    value: float, params: dict, state_vars: dict, engine_state: dict, dt: float
) -> float:
    """纯代数映射: S = fn(其他状态变量)"""
    code = params.get("fn")
    namespace = _ns(state_vars, params, engine_state)
    result = _eval_fn(code, namespace)
    lo = params.get("_clamp_lo", 0.0)
    hi = params.get("_clamp_hi", 1.0)
    return _clamp(result, lo, hi)


def _solve_first_order_lag(
    value: float, params: dict, state_vars: dict, engine_state: dict, dt: float
) -> float:
    """一阶滞后: dS/dt = (target - S) / tau"""
    tau = params.get("tau", 1.0)
    if tau <= 0:
        return value
    namespace = _ns(state_vars, params, engine_state)
    if params.get("target_source") == "engine":
        target = _eval_fn(params.get("target_fn"), namespace)
    elif "target_fn" in params and params["target_fn"] is not None:
        target = _eval_fn(params["target_fn"], namespace)
    else:
        target = params.get("target", 0.0)
    rate = (target - value) / tau
    new_val = value + rate * dt
    lo = params.get("_clamp_lo", 0.0)
    hi = params.get("_clamp_hi", 1.0)
    return _clamp(new_val, lo, hi)


def _solve_custom(
    value: float, params: dict, state_vars: dict, engine_state: dict, dt: float
) -> float:
    """自定义导数: dS/dt = derivative_fn(状态变量, params)"""
    code = params.get("derivative_fn")
    namespace = _ns(state_vars, params, engine_state)
    derivative = _eval_fn(code, namespace)
    new_val = value + derivative * dt
    lo = params.get("_clamp_lo", 0.0)
    hi = params.get("_clamp_hi", 1.0)
    return _clamp(new_val, lo, hi)


# 注册内置求解器（向后兼容：compute() 使用）
_ODE_SOLVERS["logistic"] = _solve_logistic
_ODE_SOLVERS["algebraic"] = _solve_algebraic
_ODE_SOLVERS["first_order_lag"] = _solve_first_order_lag
_ODE_SOLVERS["custom"] = _solve_custom


# ── 配置加载 ------------------------------------------------------------------

def _load_config() -> dict:
    """加载 data/ode_diseases.json"""
    config_path = Path(__file__).resolve().parents[2] / "data" / "ode_diseases.json"
    with open(config_path, "r", encoding="utf-8") as f:
        config = json.load(f)
    # Validate config before use
    errors = validate_ode_diseases(config)
    if errors:
        msgs = "; ".join(f"{e.path}: {e.message}" for e in errors)
        raise ValidationError("ode_diseases.json", "root", f"ODE diseases validation failed: {msgs}")
    return config


def _get_clamp(clamp_list: list | None) -> tuple[float | None, float | None]:
    if clamp_list is None:
        return None, None
    lo = clamp_list[0] if len(clamp_list) > 0 else None
    hi = clamp_list[1] if len(clamp_list) > 1 else None
    return lo, hi


# ── 通用疾病模块 --------------------------------------------------------------

class ConfigDrivenDiseaseModule(DiseaseModule):
    """
    配置驱动通用疾病模块。

    从 ode_diseases.json 读取 ODE 定义，自动执行状态变量更新 + FactorCommand 输出。
    行为等同于手写 DiseaseModule 子类，但完全由数据驱动。
    """

    def __init__(self, name: str, config: dict, severity: str = "moderate"):
        super().__init__(name=name)
        self._config = config
        self._severity = severity

        # 应用严重程度预设
        presets = config.get("severity_presets", {})
        self._params: dict[str, Any] = {}
        if severity in presets:
            self._params.update(presets[severity])
        elif "moderate" in presets:
            self._params.update(presets["moderate"])

        # 时间缩放：引擎速率 → 游戏速率（统一 14x）
        # 所有 ODE 速率常数和 tau 除以该系数，使疾病进展速度与游戏时间匹配
        _TIME_SCALE = 14.0
        for key in list(self._params.keys()):
            if key.endswith("_rate"):
                self._params[key] /= _TIME_SCALE

        # 初始化状态变量
        self._state_vars: dict[str, float] = {}
        self._var_meta: dict[str, dict] = {}
        for var_name, var_conf in config.get("state_variables", {}).items():
            initial = var_conf.get("initial", 0.0)
            if "initial_key" in var_conf:
                initial = self._params.get(var_conf["initial_key"], initial)
            self._state_vars[var_name] = initial
            lo, hi = _get_clamp(var_conf.get("clamp"))
            raw_params = {**self._params, **var_conf.get("params", {})}
            # 将顶层求解器字段下沉到 params（保持求解器查找一致）
            for _key in ("fn", "derivative_fn", "target_source", "target_engine_key", "target_engine_fn"):
                if _key in var_conf:
                    raw_params[_key] = var_conf[_key]
            # 展开 rate_key / K_key：将 preset 中的实际值注入 params
            if "rate_key" in raw_params:
                rk = raw_params.pop("rate_key")
                if rk in self._params and "rate" not in raw_params:
                    raw_params["rate"] = self._params[rk]
            if "K_key" in raw_params:
                kk = raw_params.pop("K_key")
                if kk in self._params and "K" not in raw_params:
                    raw_params["K"] = self._params[kk]
            raw_params["_clamp_lo"] = lo
            raw_params["_clamp_hi"] = hi
            # 缩放时间常数（tau）和种子增量（seed_boost）
            if "tau" in raw_params:
                raw_params["tau"] /= _TIME_SCALE
            if "seed_boost" in raw_params:
                raw_params["seed_boost"] /= _TIME_SCALE
            # 预编译所有表达式字符串为 code 对象，加速重复求值
            for _expr_key in ("fn", "derivative_fn", "target_fn", "seed_boost_fn"):
                if _expr_key in raw_params and isinstance(raw_params[_expr_key], str):
                    raw_params[_expr_key] = _compile_expr(raw_params[_expr_key])
            self._var_meta[var_name] = {
                "ode_type": var_conf.get("ode_type", "algebraic"),
                "params": raw_params,
            }

        # 缓存 outputs 配置，预编译表达式
        self._outputs = []
        for output in config.get("outputs", []):
            out = dict(output)
            if "fn" in out and isinstance(out["fn"], str):
                out["fn"] = _compile_expr(out["fn"])
            if "condition" in out and isinstance(out["condition"], str):
                out["condition"] = _compile_expr(out["condition"])
            self._outputs.append(out)

        logger.info(
            "ConfigDrivenDiseaseModule created: %s (severity=%s, vars=%s)",
            name, severity, list(self._state_vars.keys()),
        )

    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]:
        if not self.active:
            return []

        # 构建命名空间：状态变量 + 参数（过滤 code 对象）
        namespace = _ns(self._state_vars, self._params, engine_state)

        # Step 1: 更新所有状态变量（Forward Euler 推进，用于向后兼容）
        for var_name, meta in self._var_meta.items():
            ode_type = meta["ode_type"]
            solver = _ODE_SOLVERS.get(ode_type)
            if solver is None:
                logger.warning("Unknown ode_type '%s' for var '%s', skipping", ode_type, var_name)
                continue
            old_val = self._state_vars[var_name]
            new_val = solver(old_val, meta["params"], self._state_vars, engine_state, dt)
            self._state_vars[var_name] = new_val

        # Step 2: 计算 FactorCommand 输出
        commands = []
        for output in self._outputs:
            # 条件输出
            cond_code = output.get("condition")
            if cond_code is not None:
                cond_result = _eval_fn(cond_code, namespace)
                if not cond_result:
                    continue
            fn_code = output.get("fn")
            value = _eval_fn(fn_code, namespace)
            # 输出值 clamp
            out_clamp = output.get("clamp")
            if out_clamp:
                value = _clamp(value, out_clamp[0], out_clamp[1])
            cmd = FactorCommand(target=output["target"], op=output["op"], value=round(value, 4))
            commands.append(cmd)

        return commands

    def compute_derivatives(self, engine_state: dict) -> dict[str, float]:
        """返回所有状态变量的导数（供 solve_ivp Radau 调用）。

        algebraic 变量用极小 tau=0.001s 的一阶 lag 近似，使其可融入 ODE 框架。
        所有导数均未做 clamp——clamp 由 solve_ivp 的 atol 或后处理负责。
        """
        if not self.active:
            return {var: 0.0 for var in self._state_vars}

        namespace = _ns(self._state_vars, self._params, engine_state)
        derivatives: dict[str, float] = {}
        TAU_INSTANT = 0.001  # 极小时间常数 ≈ 瞬时响应

        for var_name, meta in self._var_meta.items():
            ode_type = meta["ode_type"]
            solver = _DERIVATIVE_SOLVERS.get(ode_type)
            if solver is None:
                derivatives[var_name] = 0.0
                continue

            if ode_type == "algebraic":
                # 代数约束 S = fn(other_vars) → 用一阶 lag 近似
                code = meta["params"].get("fn")
                target_val = _eval_fn(code, namespace)
                current_val = self._state_vars[var_name]
                derivatives[var_name] = (target_val - current_val) / TAU_INSTANT
            else:
                derivatives[var_name] = solver(
                    self._state_vars[var_name], meta["params"], self._state_vars, engine_state
                )

        return derivatives

    def summary(self) -> dict:
        result = {"name": self.name, "active": self.active}
        for var_name, value in self._state_vars.items():
            result[var_name] = round(value, 4)
        return result

    def __getattr__(self, name: str):
        """允许通过属性访问状态变量（如 module.cellular_toxicity）。"""
        if name in self._state_vars:
            return self._state_vars[name]
        raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'")

    def __setattr__(self, name: str, value):
        if name.startswith("_") or name in ("name", "active", "activated_at_s"):
            super().__setattr__(name, value)
        elif hasattr(self, "_state_vars") and name in self._state_vars:
            self._state_vars[name] = value
        else:
            super().__setattr__(name, value)


# ── 自动注册所有配置中的疾病 ---------------------------------------------------

def _register_all() -> None:
    config = _load_config()
    for disease_name, disease_conf in config.items():
        if disease_name.startswith("_"):
            continue
        register_disease(disease_name, ConfigDrivenDiseaseModule, config=disease_conf)


_register_all()
