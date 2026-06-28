"""R6 Layer B: Outer-layer persistence adapter.

CODE_WIKI "灰区" #2 explicitly flags `to_persistence_snapshot()` on the
`VirtualCreature` kernel as a coupling issue — session persistence is an
application concern, not a kernel concern. This module provides the outer-layer
adapter that wraps the kernel's snapshot method, so app code can call
`build_persistence_snapshot(engine)` instead of `engine.to_persistence_snapshot()`.

The kernel method is retained (deprecated) for backward compatibility; new
callers should prefer this adapter. Migration is mechanical — replace
`vc.to_persistence_snapshot()` with `build_persistence_snapshot(vc)`.

See docs/clinical-interpretation-layer.md "Phase 3" for the broader plan.
"""
from __future__ import annotations

from typing import Any


def build_persistence_snapshot(engine: Any) -> dict:
    """Build a session-persistence snapshot from the kernel state.

    Thin wrapper over the kernel's `to_persistence_snapshot()` method,
    providing an outer-layer call site that can grow to include app concerns
    (action log, session metadata, etc.) without further polluting the kernel.

    Args:
        engine: VirtualCreature instance

    Returns:
        JSON-serializable dict suitable for session persistence / SQLite storage.
    """
    return engine.to_persistence_snapshot()
