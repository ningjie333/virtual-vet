"""
Factor pipeline — the single engine-level interface for writing parameter values.

`apply_factor(FactorCommand)` is the sole entry point for external
perturbations: disease modules, pharmacology, scenario events, and the
coupling engine all dispatch through it. The whitelist of writable
parameter paths lives in `_PARAM_PATHS` (see `topology.py`).

This module factors out the `apply_factor` method that previously lived
inline in `VirtualCreature`. It can be called as a free function with
an explicit engine root, e.g.:

    apply_factor(cmd, engine=self)

Phase 1: this is a free function that takes the engine as a parameter,
not a class method. The class method form is preserved on `VirtualCreature`
for backward compatibility (it just delegates to this function).

C7 blood_volume guard: preserved. `heart.blood_volume` cannot go negative
on `add` or `set` operations.

P0.2: Per-step baseline idempotency
  - snapshot_baselines(engine) captures all writable param values at
    step start.  Called once at the top of _step_euler.
  - First multiply / add on a target uses the step-baseline as the
    base (prevents exponential compounding across steps).  Subsequent
    writes to the same target chain from the current value (preserves
    intra-step chaining for coupling, tox, lifecycle, multi-disease).
  - set operations are naturally idempotent and pop the baseline.
"""

from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING

from src.common_types import FactorCommand
from .topology import _PARAM_PATHS

if TYPE_CHECKING:
    from src.engine.step_contract import StepGuard

logger = logging.getLogger(__name__)

# ── P0.2: per-step baseline tracking ─────────────────────────────────
_step_baselines: dict[str, float] = {}


def snapshot_baselines(engine: Any, guard: "StepGuard | None" = None) -> None:
    """Capture current values of all writable parameters.

    Call once at the start of each simulation step.  Resets the
    per-step tracking so that the first multiply / add on each target
    uses the step-start value as the base.

    R3 contract:
        requires_not  INV_BASELINES_CLEARED (cannot snapshot after clear in same step)
        sets          INV_BASELINES_SNAPSHOTTED
    """
    if guard is not None:
        from src.engine.step_contract import INV_BASELINES_CLEARED
        guard.require_invariant_not(INV_BASELINES_CLEARED)

    _step_baselines.clear()
    for target, (module_name, attr_name) in _PARAM_PATHS.items():
        module = getattr(engine, module_name, None)
        if module is None:
            continue
        val = getattr(module, attr_name, None)
        if val is not None:
            _step_baselines[target] = float(val)

    if guard is not None:
        from src.engine.step_contract import INV_BASELINES_SNAPSHOTTED
        guard.set_invariant(INV_BASELINES_SNAPSHOTTED)


def clear_baselines(guard: "StepGuard | None" = None) -> None:
    """Clear per-step baseline tracking.

    Called at end of each step to prevent stale baselines from leaking
    into tests that don't call step().

    R3 contract:
        sets  INV_BASELINES_CLEARED
    """
    _step_baselines.clear()

    if guard is not None:
        from src.engine.step_contract import INV_BASELINES_CLEARED
        guard.set_invariant(INV_BASELINES_CLEARED)


def _get_param_path(target: str) -> tuple[str, str] | None:
    """Resolve `target` (e.g. 'heart.heart_rate') to (module_name, attr_name).

    Returns None if the target is not in the registry.
    """
    return _PARAM_PATHS.get(target)


class FactorCommandRegistry:
    """Whitelisted dispatch table for FactorCommand targets.

    Phase 1: this is a thin wrapper over the module-level `_PARAM_PATHS` dict.
    Phase 5+: may grow to track (path, value) writes for telemetry / replay.
    """

    def __init__(self) -> None:
        # Phase 1: registry IS the dict. Phase 5: may track per-path write
        # counts and last-write timestamps for diagnostics.
        self._writable_count: int = len(_PARAM_PATHS)

    @property
    def writable_count(self) -> int:
        return self._writable_count

    def lookup(self, target: str) -> tuple[str, str] | None:
        return _get_param_path(target)

    def is_writable(self, target: str) -> bool:
        return target in _PARAM_PATHS


def apply_factor(cmd: FactorCommand, engine: Any) -> None:
    """Unified parameter write interface — single entry point for all
    external perturbations (disease / drugs / events / coupling rules).

    Looks up `cmd.target` in `_PARAM_PATHS`, then applies `cmd.op`
    (multiply / add / set) to the corresponding module attribute on
    `engine`. Unknown targets / ops are logged and silently ignored
    (fail-safe: a disease with a bad target doesn't crash the sim).

    C7 special protection: `heart.blood_volume` cannot go negative on
    `add` or `set` operations.

    P0.2 idempotency: for the first multiply / add on a target each
    step the baseline value is used as the base, preventing exponential
    compounding across steps.  Subsequent writes chain from the current
    value so that intra-step layering (tox → lifecycle → disease →
    coupling) still works correctly.

    Args:
        cmd: FactorCommand instruction
        engine: VirtualCreature (or any object with the modules listed
               in `_PARAM_PATHS` as attributes)
    """
    path = _PARAM_PATHS.get(cmd.target)
    if path is None:
        logger.warning("apply_factor: unknown target '%s'", cmd.target)
        return

    module_name, attr_name = path
    module = getattr(engine, module_name, None)
    if module is None:
        logger.warning("apply_factor: module '%s' not found", module_name)
        return

    current = getattr(module, attr_name, None)
    if current is None:
        logger.warning("apply_factor: attr '%s' not found on %s", attr_name, module_name)
        return

    # P0.2: first multiply / add on a target uses the step-baseline
    if cmd.op in ("multiply", "add"):
        baseline = _step_baselines.pop(cmd.target, None)
        if baseline is not None:
            base = baseline
        else:
            base = current

        if cmd.op == "multiply":
            new_value = base * cmd.value
        else:
            new_value = base + cmd.value
    elif cmd.op == "set":
        new_value = cmd.value
        _step_baselines.pop(cmd.target, None)  # set overrides the baseline
    else:
        logger.warning("apply_factor: unknown op '%s'", cmd.op)
        return

    # C7: 特殊保护 — heart.blood_volume 不能为负
    if cmd.target == "heart.blood_volume":
        if cmd.op in ("add", "set"):
            new_value = max(0.0, new_value)

    setattr(module, attr_name, new_value)
    logger.debug(
        "apply_factor: %s %s %.4f → %.4f",
        cmd.target, cmd.op, current, new_value,
    )
