from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class EngineAdvancerProtocol(Protocol):
    """Application-facing adapter for advancing the physiology engine."""

    def advance_minutes(self, engine: Any, minutes: float) -> None:
        """Advance an engine by a scenario-level duration."""


@dataclass(frozen=True)
class PhysicalMinuteAdvancer:
    """Default app-layer mapping: scenario minutes -> physical minutes."""

    def advance_minutes(self, engine: Any, minutes: float) -> None:
        if minutes <= 0:
            return

        if hasattr(engine, "advance_seconds"):
            engine.advance_seconds(minutes * 60.0)
            return

        engine.simulate(float(minutes))
