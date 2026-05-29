"""
Multi-organ closed-loop coupling engine.

PhysiologicalSignal : immutable signal value container
OrganContext       : per-organ signal bus (publish/subscribe)
CouplingEngine     : resolves coupling_rules.json → FactorCommands
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import jsonschema

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

ORGANS = Literal["heart", "lung", "kidney", "blood", "fluid", "liver", "coagulation", "nervous", "endocrine"]


@dataclass(frozen=True)
class PhysiologicalSignal:
    """Immutable signal emitted by an organ module."""

    name: str
    value: float
    unit: str
    source_module: ORGANS
    timestamp_s: float = 0.0


# ---------------------------------------------------------------------------
# OrganContext — signal bus per organ module
# ---------------------------------------------------------------------------

class OrganContext:
    """
    Per-organ signal bus.

    Organ modules call ``ctx.publish(signal)`` to expose their outputs,
    and ``ctx.get_signal(name)`` to read another organ's last-published value.

    All signals are last-value cache — only the most recent value is retained.
    """

    __slots__ = ("_module_name", "_signals")

    def __init__(self, module_name: ORGANS) -> None:
        object.__setattr__(self, "_module_name", module_name)
        object.__setattr__(self, "_signals", {})

    @property
    def module_name(self) -> ORGANS:
        return self._module_name

    def publish(self, signal: PhysiologicalSignal) -> None:
        self._signals[signal.name] = signal

    def get_signal(self, name: str) -> Optional[PhysiologicalSignal]:
        return self._signals.get(name)

    def get_value(self, name: str, default: float = 0.0) -> float:
        sig = self._signals.get(name)
        return sig.value if sig is not None else default

    def all_signals(self) -> dict[str, PhysiologicalSignal]:
        return dict(self._signals)


# ---------------------------------------------------------------------------
# CouplingEngine
# ---------------------------------------------------------------------------

@dataclass
class _CouplingRule:
    """Parsed coupling rule from coupling_rules.json."""

    name: str
    loop: str
    source_module: ORGANS
    source_signal: str
    target_module: ORGANS
    target_param: str
    op: Literal["multiply", "add", "set"]
    fn_expr: str
    condition: Optional[str]
    time_constant: float
    priority: int
    enabled: bool

    # cached lag state: signal_name → current_lagged_value
    _lag_state: dict = field(default_factory=dict)


class CouplingEngine:
    """
    Resolves inter-organ couplings from ``data/coupling_rules.json`` and
    produces a list of ``FactorCommand`` to apply each simulation step.

    Execution order within a step
    ----------------------------
    1. All organ modules compute their state (``organ.compute()``) and publish
       signals via their ``OrganContext``.
    2. ``CouplingEngine.resolve(step_outputs, dt)`` is called:
       a. Signals from all organs are collected into a shared ``_signal_map``.
       b. Each enabled coupling rule is evaluated in ascending ``priority`` order.
       c. Python expressions (``fn``) are evaluated against the signal map.
       d. If ``time_constant > 0``, a first-order lag is applied.
       e. Resulting ``FactorCommand`` list is returned.
    3. The commands are applied to the engine via the existing
       ``apply_factor()`` pipeline — **after** organs compute but **before**
       diseases compute.

    Circular dependencies are prevented by the ``priority`` field:
    kidney-coupled rules run at priority 10, cardiovascular-coupled at priority 20.
    """

    def __init__(
        self,
        rules_path: str | Path | None = None,
        schema_path: str | Path | None = None,
    ) -> None:
        if rules_path is None:
            rules_path = Path(__file__).parent.parent.parent / "data" / "coupling_rules.json"
        if schema_path is None:
            schema_path = Path(__file__).parent.parent.parent / "data" / "coupling_rules_schema.json"

        self._rules: list[_CouplingRule] = []
        self._signal_map: dict[str, float] = {}
        self._lag_state: dict[str, float] = {}  # rule_name:signal_name → lagged value
        self._load_rules(Path(rules_path), Path(schema_path))

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------

    def _load_rules(self, rules_path: Path, schema_path: Path) -> None:
        import json

        # Validate against schema
        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)

        with open(rules_path, encoding="utf-8") as f:
            data = json.load(f)

        jsonschema.validate(instance=data, schema=schema)

        raw_couplings = data.get("couplings", [])
        for raw in raw_couplings:
            rule = _CouplingRule(
                name=raw["name"],
                loop=raw["loop"],
                source_module=raw["source"]["module"],
                source_signal=raw["source"]["signal"],
                target_module=raw["target"]["module"],
                target_param=raw["target"]["param"],
                op=raw["target"]["op"],
                fn_expr=raw["target"]["fn"],
                condition=raw.get("condition"),
                time_constant=raw.get("time_constant", 0.0),
                priority=raw.get("priority", 50),
                enabled=raw.get("enabled", True),
            )
            self._rules.append(rule)

        self._rules.sort(key=lambda r: r.priority)
        logger.info("CouplingEngine loaded %d rules from %s", len(self._rules), rules_path)

    # ------------------------------------------------------------------
    # Resolve
    # ------------------------------------------------------------------

    def resolve(
        self,
        organ_contexts: dict[ORGANS, OrganContext],
        dt: float,
    ) -> list["_CouplingFactorCommand"]:
        """
        Compute all FactorCommands from current signal values.

        Args:
            organ_contexts: Map of module name → its OrganContext (with published signals)
            dt: Simulation time step in seconds

        Returns:
            List of FactorCommand to apply to the engine.
        """
        # Build flat signal map: "module.signal" → value
        self._signal_map.clear()
        for module_name, ctx in organ_contexts.items():
            for sig_name, sig in ctx.all_signals().items():
                key = f"{module_name}.{sig_name}"
                self._signal_map[key] = sig.value
                # Also store bare signal name for convenience
                self._signal_map[sig_name] = sig.value

        commands: list["FactorCommand"] = []
        for rule in self._rules:
            if not rule.enabled:
                continue

            # Check condition
            if rule.condition:
                try:
                    ok = bool(eval(rule.condition, {"__builtins__": {"min": min, "max": max}}, self._signal_map))
                except Exception:
                    ok = False
                if not ok:
                    continue

            # Evaluate target expression
            try:
                result_val = float(eval(rule.fn_expr, {"__builtins__": {"min": min, "max": max, "abs": abs}}, self._signal_map))
            except Exception as ex:
                logger.debug("Coupling eval error for rule %r: %s", rule.name, ex)
                continue

            # Apply first-order lag if time_constant > 0
            if rule.time_constant > 0:
                lag_key = f"{rule.name}:{rule.source_signal}"
                prev = self._lag_state.get(lag_key, result_val)
                # Discrete first-order lag: y_new = y_old + (target - y_old) * dt / tau
                new_lag = prev + (result_val - prev) * dt / rule.time_constant
                self._lag_state[lag_key] = new_lag
                result_val = new_lag

            # Build FactorCommand
            cmd = _CouplingFactorCommand(
                target=rule.target_param,
                op=rule.op,
                value=result_val,
                _source=f"coupling:{rule.name}",
            )
            commands.append(cmd)

        return commands

    @property
    def num_rules(self) -> int:
        return len(self._rules)

    @property
    def rules(self) -> list[_CouplingRule]:
        return list(self._rules)


# FactorCommand is imported lazily (simulation.py imports this module)
from dataclasses import dataclass as _dc
from typing import Literal as _Lit


@_dc(frozen=True)
class _CouplingFactorCommand:
    """Internal FactorCommand used by CouplingEngine — mirrors simulation.FactorCommand."""

    target: str
    op: _Lit["multiply", "add", "set"]
    value: float
    _source: str = "coupling"