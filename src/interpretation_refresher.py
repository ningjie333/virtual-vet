from __future__ import annotations

from typing import Any, Callable, Protocol


class InterpretationRefresherProtocol(Protocol):
    """Refreshes interpretation-side state after physical time advancement."""

    def refresh(self, engine: Any) -> None: ...


class NoOpInterpretationRefresher:
    """Compatibility default for interpreters that do not need explicit refresh."""

    def refresh(self, engine: Any) -> None:
        return None


class ClinicalSignsRefresher:
    """Refreshes the engine-attached sign engine if present."""

    def __init__(
        self,
        signs_engine_resolver: Callable[[Any], Any | None] | None = None,
    ) -> None:
        self._signs_engine_resolver = signs_engine_resolver or _default_signs_engine_resolver

    def refresh(self, engine: Any) -> None:
        signs_engine = self._signs_engine_resolver(engine)
        if signs_engine is None:
            return None
        signs_engine.compute(engine.current_time_s)
        return None


def _default_signs_engine_resolver(engine: Any) -> Any | None:
    return getattr(engine, "clinical_signs_engine", None)
