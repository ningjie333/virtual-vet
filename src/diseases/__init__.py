"""
Disease Module Framework — 疾病扰动模块框架

设计原则：
  - 疾病 = 数个 ODE 状态变量 + 对引擎参数的扰动指令（FactorCommand）
  - 不硬编码时间表或阶段表
  - 只定义病原体-宿主动力学 ODE
  - 临床阶段是引擎自然演化的涌现结果
  - 返回值是 list[FactorCommand]，引擎通过 apply_factor() 统一写入

使用方式：
  1. 在 src/diseases/ 下新建 <disease>.py
  2. 实现 DiseaseModule 子类，重写 compute()
  3. 调用 register_disease() 注册
"""

import logging
from abc import ABC, abstractmethod
from enum import Enum

from ..common_types import FactorCommand
from ..logger_config import get_logger

logger = get_logger(__name__)


class DiseaseState(Enum):
    """R5 Stage 2: 疾病生命周期状态机。

    状态转换图：
        INCUBATING ──activate()──> ACTIVE ──deactivate()──> RESOLVED
                                         │
                                         └──(宿主死亡)──> DEAD

    - INCUBATING: 已构造但未激活（病原体未侵入）
    - ACTIVE: 已激活，每步 compute() 返回 FactorCommand
    - RESOLVED: 已治愈/自愈，compute() 返回空列表（仍留在 engine.diseases 列表）
    - DEAD: 宿主因此疾病死亡（compute() 返回空列表）

    RESOLVED/DEAD 疾病可通过 detach_disease() 从引擎移除。
    """
    INCUBATING = "incubating"
    ACTIVE = "active"
    RESOLVED = "resolved"
    DEAD = "dead"

# ---------- 全局疾病注册表 ----------
_DISEASE_REGISTRY: dict[str, type] = {}


def register_disease(name: str, cls: type, **extra):
    """
    注册一个疾病模块。

    Args:
        name: 疾病唯一标识符（小写，下划线分隔）
        cls: DiseaseModule 子类或工厂可调用对象
        **extra: 额外参数（如 config=dict），存储在注册表中传递给构造函数

    Example:
        register_disease("pneumonia", PneumoniaModule)
        register_disease("pneumonia", ConfigDrivenDiseaseModule, config=conf)
    """
    if not (isinstance(cls, type) and issubclass(cls, DiseaseModule)):
        raise TypeError(f"{cls} must be a DiseaseModule subclass")
    _DISEASE_REGISTRY[name.lower()] = (cls, extra)
    logger.debug("Registered disease module: %s → %s", name, cls.__name__)


def list_diseases() -> list[str]:
    """返回所有已注册疾病名称"""
    return list(_DISEASE_REGISTRY.keys())


def create_disease(name: str, **kwargs) -> "DiseaseModule":
    """
    工厂方法：按名称实例化疾病模块。

    Args:
        name: 疾病名称（必须在注册表中）
        **kwargs: 传递给构造函数的参数（如 severity="moderate"）

    Returns:
        DiseaseModule 实例

    Raises:
        KeyError: 未注册的疾病
    """
    entry = _DISEASE_REGISTRY.get(name.lower())
    if entry is None:
        raise KeyError(
            f"Disease '{name}' not registered. "
            f"Available: {list_diseases()}"
        )
    cls, extra = entry
    # 合并：name + 注册时的 extra（如 config）+ 调用时的 kwargs（如 severity）
    merged = {"name": name, **extra, **kwargs}
    return cls(**merged)


class DiseaseModule(ABC):
    """
    疾病模块基类。

    子类必须实现：
      - compute(dt: float, engine_state: dict) -> list[FactorCommand]
        每步调用，返回 FactorCommand 指令列表供引擎通过 apply_factor() 写入。

    只返回需要变更的指令，未提及的器官/参数保持不变。
    不活跃时返回空列表。

    ──────────────────────────────────────────────────────────────────────
    多病叠加的合并语义 (Q2 spec, 2026-06-14)
    ──────────────────────────────────────────────────────────────────────
    当多个 DiseaseModule 通过 VirtualCreature.attach_disease() 叠加时，
    引擎按 **attach 顺序 chained-rebase** 合并所有 active 疾病的 FactorCommand：

      - `multiply` 链 = 复合效应
        例: DCM 降 30% (`×0.7`) + 肺炎降 20% (`×0.8`) → 最终 `×0.56`
        临床对应: 慢性基础病 + 急性合并症，复合恶化（不是覆盖）
      - `add` 链 = 累加
        例: 疼痛 +5 bpm + 发热 +10 bpm → 最终 `+15 bpm`
        临床对应: 多源刺激累加
      - `set` 链 = 后写者赢
        例: 疾病 A `set HR=120`，疾病 B 紧跟 `set HR=140` → 最终 `HR=140`
        临床对应: 最近 attach 的疾病 = 最相关的临床上下文

    该 spec 的依据：临床 3 个核心 multi-disease 场景（DCM+肺炎、CKD+肺炎、
    糖尿病+UTI）都需要复合效果，"覆盖"或"取最大"都不生理。详见
    `docs/severity_design_proposal.md` §"技术问题核实结果" / Q2。

    排序 = `VirtualCreature.attach_disease` 调用顺序（先到先得）；
    第一个 attach 的疾病是基线，后续 attach 的疾病在此基线上做 chained-rebase。

    **注意**：本类不强制 priority / aggregation 字段（已明确决策：YAGNI）。
    若未来需要优先级/聚合策略，再扩展本基类。

    测试: `tests/test_multi_disease.py` 回归套件。
    """

    def __init__(self, name: str):
        self.name = name
        self._state = DiseaseState.INCUBATING  # R5 Stage 2: 生命周期状态
        self.activated_at_s = 0.0  # 激活时间（仿真秒）

    @property
    def active(self) -> bool:
        """R5 Stage 2: 向后兼容 — active = (state == ACTIVE)。"""
        return self._state == DiseaseState.ACTIVE

    @active.setter
    def active(self, value: bool):
        """R5 Stage 2: 向后兼容 setter — True→ACTIVE, False→RESOLVED。"""
        if value and self._state != DiseaseState.ACTIVE:
            self._state = DiseaseState.ACTIVE
        elif not value and self._state == DiseaseState.ACTIVE:
            self._state = DiseaseState.RESOLVED

    def activate(self, current_time_s: float):
        """激活疾病（病原体侵入宿主）：INCUBATING → ACTIVE"""
        self._state = DiseaseState.ACTIVE
        self.activated_at_s = current_time_s
        logger.info("Disease activated: %s at t=%.1fs", self.name, current_time_s)

    def deactivate(self):
        """治愈/停止疾病：ACTIVE → RESOLVED（不清空 _state_vars，保留历史）"""
        if self._state == DiseaseState.ACTIVE:
            self._state = DiseaseState.RESOLVED
            self.activated_at_s = 0.0  # 向后兼容：reset 激活时间
            logger.info("Disease deactivated: %s", self.name)

    def mark_dead(self):
        """标记宿主因此疾病死亡：ACTIVE → DEAD"""
        if self._state == DiseaseState.ACTIVE:
            self._state = DiseaseState.DEAD
            logger.info("Disease marked DEAD: %s", self.name)

    @property
    def state(self) -> DiseaseState:
        """R5 Stage 2: 当前生命周期状态。"""
        return self._state

    @property
    def elapsed_since_activation_s(self) -> float:
        """从激活到现在的秒数（需外部更新 current_time）"""
        return getattr(self, '_current_time_s', 0.0) - self.activated_at_s

    @abstractmethod
    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]:
        """
        计算当前步的疾病扰动指令。

        Args:
            dt: 时间步长（秒）
            engine_state: 引擎当前状态快照（只读），包含：
              "heart": {"heart_rate_bpm", "MAP_mmHg", "cardiac_output_ml_min"}
              "lung":  {"arterial_PO2"}
              "kidney": {"GFR_ml_min"}

        Returns:
            list[FactorCommand] 指令列表。不活跃时返回空列表。
        """
        ...

    def _cmd(self, target: str, op: str, value: float) -> FactorCommand:
        """快捷创建 FactorCommand 指令。"""
        return FactorCommand(target=target, op=op, value=value)

    def _clamp(self, value: float, lo: float, hi: float) -> float:
        """工具方法：数值限幅"""
        return max(lo, min(hi, value))

# 导入配置驱动引擎（自动注册所有 JSON 中定义的疾病）
from .config_driven import ConfigDrivenDiseaseModule, register_ode_type  # noqa: E402, F401
