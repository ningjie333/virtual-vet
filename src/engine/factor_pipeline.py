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
"""

from __future__ import annotations

import logging
from typing import Any

from src.common_types import FactorCommand
from .topology import _PARAM_PATHS

logger = logging.getLogger(__name__)


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

    if cmd.op == "multiply":
        new_value = current * cmd.value
    elif cmd.op == "add":
        new_value = current + cmd.value
    elif cmd.op == "set":
        new_value = cmd.value
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
