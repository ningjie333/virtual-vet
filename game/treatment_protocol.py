"""
Treatment Protocol — 给药状态写协议（灰区 #3 收纳器）。

职责:
  - 收纳游戏层对内核 pharmacology 子系统的"懒挂载 + 给药"写操作
  - 与 `GameplayModifierProtocol` 并列，作为 `GameRuntime` 的第五个协作者

设计原则:
  - interpreter 是只读契约，不承担 mutation
  - advancer 主管时间推进，不混淆给药
  - treatment 是"游戏给药 → 内核 pharmacology 写"的唯一合规通道
  - 游戏层的疾病→药物协议映射（_DRUG_PROTOCOL）仍留在 game/treatment.py，
    本协议只负责 pharmacology 状态网关
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TreatmentProtocol(Protocol):
    """给药协议：pharmacology 状态网关。"""

    def ensure_pharmacology(self, engine: Any) -> None:
        """确保引擎已挂载 PharmacologyState（懒初始化）。"""
        ...

    def administer_drug(
        self,
        engine: Any,
        drug_name: str,
        *,
        dose_mg_kg: float = 0.0,
        volume_ml: float = 0.0,
    ) -> None:
        """给药（剂量或容量二选一）。"""
        ...


class DefaultTreatment:
    """默认实现：pharmacology 懒挂载 + administer_drug 委托。

    逻辑迁自 game/action_system.py 的 administer_drug action 内联代码
    与 game/treatment.py::_ensure_pharmacology（阶段 2 重构）。
    直接读写 engine.pharmacology —— 这是预期行为：
    Protocol 实现内部是"灰区收纳器"，把散落在游戏层的直写集中到一处可控实现。
    """

    def ensure_pharmacology(self, engine: Any) -> None:
        from src.pharmacology import PharmacologyState

        if not hasattr(engine, "pharmacology") or engine.pharmacology is None:
            engine.pharmacology = PharmacologyState(weight_kg=engine.w)

    def administer_drug(
        self,
        engine: Any,
        drug_name: str,
        *,
        dose_mg_kg: float = 0.0,
        volume_ml: float = 0.0,
    ) -> None:
        self.ensure_pharmacology(engine)
        if volume_ml > 0:
            engine.pharmacology.administer_drug(drug_name, volume_ml=volume_ml)
        else:
            engine.pharmacology.administer_drug(drug_name, dose_mg_kg=dose_mg_kg)
