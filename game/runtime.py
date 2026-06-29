from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

from src.clinical_interpreter import (
    ClinicalInterpreterProtocol,
    DefaultClinicalInterpreter,
)
from src.engine_advancer import EngineAdvancerProtocol, PhysicalMinuteAdvancer
from src.interpretation_refresher import (
    ClinicalSignsRefresher,
    InterpretationRefresherProtocol,
)
from game.gameplay_modifier import (
    DefaultGameplayModifier,
    GameplayModifierProtocol,
)
from game.treatment_protocol import (
    DefaultTreatment,
    TreatmentProtocol,
)


@dataclass(frozen=True)
class GameRuntime:
    """Outer-layer collaborators that drive the kernel.

    五协作者（阶段 2 重构后）:
      - advancer: 时间推进（场景分钟 → 物理秒）
      - interpreter: 只读临床解释（snapshot/phase/summary/report）
      - refresher: 解释状态刷新
      - modifier: 玩法状态写（夜间修正等，灰区 #1 收纳器）
      - treatment: 给药状态写（pharmacology 网关，灰区 #3 收纳器）
    """

    advancer: EngineAdvancerProtocol
    interpreter: ClinicalInterpreterProtocol = field(
        default_factory=DefaultClinicalInterpreter
    )
    refresher: InterpretationRefresherProtocol = field(
        default_factory=ClinicalSignsRefresher
    )
    modifier: GameplayModifierProtocol = field(
        default_factory=DefaultGameplayModifier
    )
    treatment: TreatmentProtocol = field(default_factory=DefaultTreatment)

    def advance_and_refresh(self, engine, minutes: float) -> None:
        self.advancer.advance_minutes(engine, minutes)
        self.refresher.refresh(engine)

    def advance_and_refresh_async(self, engine, minutes: float,
                                  on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        self.advancer.advance_minutes_async(engine, minutes, on_progress=on_progress)
        self.refresher.refresh(engine)


_DEFAULT_RUNTIME = GameRuntime(
    advancer=PhysicalMinuteAdvancer(),
    interpreter=DefaultClinicalInterpreter(),
    refresher=ClinicalSignsRefresher(),
    modifier=DefaultGameplayModifier(),
    treatment=DefaultTreatment(),
)


def default_runtime() -> GameRuntime:
    return _DEFAULT_RUNTIME
