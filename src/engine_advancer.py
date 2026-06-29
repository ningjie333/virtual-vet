from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol


class EngineAdvancerProtocol(Protocol):
    """Application-facing adapter for advancing the physiology engine."""

    def advance_minutes(self, engine: Any, minutes: float) -> None:
        """Advance an engine by a scenario-level duration."""

    def advance_minutes_async(self, engine: Any, minutes: float,
                              on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        """Async variant — accepts a progress callback forwarded to advance_seconds."""


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

    def advance_minutes_async(self, engine: Any, minutes: float,
                              on_progress: Optional[Callable[[int, int], None]] = None) -> None:
        if minutes <= 0:
            return

        if hasattr(engine, "advance_seconds"):
            engine.advance_seconds(minutes * 60.0, progress_callback=on_progress)
            return

        engine.simulate(float(minutes))
