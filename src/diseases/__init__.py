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

from ..simulation import FactorCommand
from ..logger_config import get_logger

logger = get_logger(__name__)

# ---------- 全局疾病注册表 ----------
_DISEASE_REGISTRY: dict[str, type] = {}


def register_disease(name: str, cls: type):
    """
    注册一个疾病模块。

    Args:
        name: 疾病唯一标识符（小写，下划线分隔）
        cls: DiseaseModule 子类

    Example:
        register_disease("pneumonia", PneumoniaModule)
    """
    if not issubclass(cls, DiseaseModule):
        raise TypeError(f"{cls.__name__} must be a subclass of DiseaseModule")
    _DISEASE_REGISTRY[name.lower()] = cls
    logger.debug("Registered disease module: %s → %s", name, cls.__name__)


def list_diseases() -> list[str]:
    """返回所有已注册疾病名称"""
    return list(_DISEASE_REGISTRY.keys())


def create_disease(name: str, **kwargs) -> "DiseaseModule":
    """
    工厂方法：按名称实例化疾病模块。

    Args:
        name: 疾病名称（必须在注册表中）
        **kwargs: 传递给构造函数的参数

    Returns:
        DiseaseModule 实例

    Raises:
        KeyError: 未注册的疾病
    """
    cls = _DISEASE_REGISTRY.get(name.lower())
    if cls is None:
        raise KeyError(
            f"Disease '{name}' not registered. "
            f"Available: {list_diseases()}"
        )
    return cls(**kwargs)


class DiseaseModule(ABC):
    """
    疾病模块基类。

    子类必须实现：
      - compute(dt: float, engine_state: dict) -> list[FactorCommand]
        每步调用，返回 FactorCommand 指令列表供引擎通过 apply_factor() 写入。

    只返回需要变更的指令，未提及的器官/参数保持不变。
    不活跃时返回空列表。
    """

    def __init__(self, name: str):
        self.name = name
        self.active = False        # 是否已激活（病原体已侵入）
        self.activated_at_s = 0.0  # 激活时间（仿真秒）

    def activate(self, current_time_s: float):
        """激活疾病（病原体侵入宿主）"""
        self.active = True
        self.activated_at_s = current_time_s
        logger.info("Disease activated: %s at t=%.1fs", self.name, current_time_s)

    def deactivate(self):
        """清除疾病（治愈/死亡后重置）"""
        self.active = False
        self.activated_at_s = 0.0
        logger.info("Disease deactivated: %s", self.name)

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

# 必须在模块底部导入，避免循环依赖
from .pneumonia import PneumoniaModule  # noqa: E402, F401
from .acute_renal_failure import AcuteRenalFailureModule  # noqa: E402, F401
from .dilated_cardiomyopathy import DilatedCardiomyopathyModule  # noqa: E402, F401
