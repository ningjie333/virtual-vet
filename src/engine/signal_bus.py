"""
Signal bus + BloodShim — Phase 4 architectural refactor (治本路径).

This module centralises the engine's "data bus" so that every read and
write of `self.blood.X` flows through one observable channel. The
`BloodShim` class is a transparent proxy: it looks like a BloodCompartment
to all callers (organs, tests, gui_app.py) but it records every
attribute access to the `SignalBus`.

The shim is a BACKWARD-COMPATIBLE wrapper. `self.blood` in
`VirtualCreature` is now a `BloodShim` instance that delegates to the
real `BloodCompartment`. The 9 organ modules continue to write
`self.blood.X = value` exactly as before — no module code changes.

Phase 1-3 work (C1, C5, 12 parameter calibrations, etc.) is preserved
intact. The bus is purely additive.

Phase 5+ (per-module INPUTS/OUTPUTS migration): the bus becomes the
canonical source of truth; module writes to self.blood can be replaced
with explicit `ctx.bus.publish_blood(name, value)`.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any


class SignalBus:
    """Engine-level data bus.

    Every blood field is a "signal". Writes go through `publish_blood`,
    reads go through `read_blood`. The bus also records a history
    of writes for diagnostics (Phase 4) and replay (future).

    The bus is NOT a replacement for the BloodCompartment — it is an
    observability layer on top. The real blood data still lives in the
    BloodCompartment instance; the bus just makes the flow visible.
    """

    def __init__(self) -> None:
        # Per-field write count for diagnostics
        self._write_count: dict[str, int] = defaultdict(int)
        self._read_count: dict[str, int] = defaultdict(int)
        # Optional: ring buffer of last N writes (Phase 5+)
        # self._recent_writes: list[tuple[float, str, Any]] = []
        # Phase 5: per-module I/O contract registry
        self._module_contracts: dict[str, dict[str, tuple[str, ...]]] = {}
        # Phase 6: real blood compartment (set by VirtualCreature after BloodShim creation)
        self._real_blood: Any = None

    def publish_blood(self, name: str, value: Any) -> None:
        """Record a blood field write (no behavior change)."""
        self._write_count[name] += 1

    def read_blood(self, name: str) -> None:
        """Record a blood field read."""
        self._read_count[name] += 1

    def register_module(
        self,
        name: str,
        inputs: tuple[str, ...] = (),
        outputs: tuple[str, ...] = (),
        reads_blood: tuple[str, ...] = (),
        writes_blood: tuple[str, ...] = (),
    ) -> None:
        """Phase 5: register a module's declared I/O contract.

        The contract is metadata only — it does not affect runtime
        behavior. It is used by `discover_topology()` and by diagnostic
        queries (`engine._signal_bus.contracts`).

        Args:
            name: module name (e.g. "heart", "liver")
            inputs: tuple of input names the module consumes
            outputs: tuple of output names the module produces
            reads_blood: tuple of blood field names the module reads
            writes_blood: tuple of blood field names the module writes
        """
        self._module_contracts[name] = {
            "inputs": tuple(inputs),
            "outputs": tuple(outputs),
            "reads_blood": tuple(reads_blood),
            "writes_blood": tuple(writes_blood),
        }

    @property
    def module_contracts(self) -> dict[str, dict[str, tuple[str, ...]]]:
        """Return all registered module I/O contracts."""
        return dict(self._module_contracts)

    @property
    def write_count(self) -> dict[str, int]:
        return dict(self._write_count)

    @property
    def read_count(self) -> dict[str, int]:
        return dict(self._read_count)

    # Phase 6: expose real blood for explicit read/write by organ modules
    @property
    def real_blood(self) -> Any:
        """Return the underlying real blood compartment (for Phase 6 migration)."""
        return self._real_blood

    @real_blood.setter
    def real_blood(self, value: Any) -> None:
        self._real_blood = value

    def stats(self) -> dict[str, Any]:
        """Return bus statistics for diagnostics."""
        return {
            "total_writes": sum(self._write_count.values()),
            "total_reads": sum(self._read_count.values()),
            "unique_written_fields": len(self._write_count),
            "fields_written": dict(self._write_count),
            "registered_modules": list(self._module_contracts.keys()),
        }


class BloodShim:
    """Backward-compat proxy for BloodCompartment.

    Looks like a BloodCompartment (any attribute access forwards to the
    underlying instance) but records every read/write to a SignalBus.

    Usage:
        real = BloodCompartment(...)
        bus = SignalBus()
        self.blood = BloodShim(real, bus)

    Then `self.blood.glucose_mmol_L` does:
      1. `__getattr__("glucose_mmol_L")` called
      2. `bus.read_blood("glucose_mmol_L")` recorded
      3. `getattr(self._real, "glucose_mmol_L")` returns the value

    And `self.blood.glucose_mmol_L = 4.5` does:
      1. `__setattr__("glucose_mmol_L", 4.5)` called
      2. `bus.publish_blood("glucose_mmol_L", 4.5)` recorded
      3. `setattr(self._real, "glucose_mmol_L", 4.5)`

    Caveat: methods on the real BloodCompartment are also forwarded,
    e.g. `self.blood.summary()` works. The shim only intercepts
    attribute ACCESS, not call return values.
    """

    __slots__ = ("_real", "_bus")

    def __init__(self, real_blood: Any, bus: SignalBus) -> None:
        # Use object.__setattr__ to bypass our own __setattr__ during init
        object.__setattr__(self, "_real", real_blood)
        object.__setattr__(self, "_bus", bus)

    def __getattr__(self, name: str) -> Any:
        # __getattr__ is only called when the attribute is NOT found
        # on the instance via normal lookup. So we forward to _real.
        real = object.__getattribute__(self, "_real")
        bus = object.__getattribute__(self, "_bus")
        bus.read_blood(name)
        return getattr(real, name)

    def __setattr__(self, name: str, value: Any) -> None:
        # Intercept writes. Do NOT call super().__setattr__ for the
        # data fields — that would store them on the shim, not the real
        # blood. We forward to the real blood.
        if name in ("_real", "_bus"):
            object.__setattr__(self, name, value)
            return
        real = object.__getattribute__(self, "_real")
        bus = object.__getattribute__(self, "_bus")
        bus.publish_blood(name, value)
        setattr(real, name, value)

    def __repr__(self) -> str:
        real = object.__getattribute__(self, "_real")
        return f"<BloodShim wrapping {type(real).__name__} instance>"
