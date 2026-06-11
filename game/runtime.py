from __future__ import annotations

from dataclasses import dataclass, field

from src.clinical_interpreter import (
    ClinicalInterpreterProtocol,
    DefaultClinicalInterpreter,
)
from src.engine_advancer import EngineAdvancerProtocol, PhysicalMinuteAdvancer
from src.interpretation_refresher import (
    ClinicalSignsRefresher,
    InterpretationRefresherProtocol,
)


@dataclass(frozen=True)
class GameRuntime:
    """Outer-layer collaborators that drive the kernel."""

    advancer: EngineAdvancerProtocol
    interpreter: ClinicalInterpreterProtocol = field(
        default_factory=DefaultClinicalInterpreter
    )
    refresher: InterpretationRefresherProtocol = field(
        default_factory=ClinicalSignsRefresher
    )

    def advance_and_refresh(self, engine, minutes: float) -> None:
        self.advancer.advance_minutes(engine, minutes)
        self.refresher.refresh(engine)


_DEFAULT_RUNTIME = GameRuntime(
    advancer=PhysicalMinuteAdvancer(),
    interpreter=DefaultClinicalInterpreter(),
    refresher=ClinicalSignsRefresher(),
)


def default_runtime() -> GameRuntime:
    return _DEFAULT_RUNTIME
