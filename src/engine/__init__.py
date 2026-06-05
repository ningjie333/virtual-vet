"""
Engine subpackage — Phase 4 architectural refactor.

This subpackage centralises engine-level data structures and protocols:
- `topology`: module coupling graph (CONNECTIONS, _PARAM_PATHS, future INPUTS/OUTPUTS)
- `factor_pipeline`: FactorCommand dispatch (apply_factor, FactorCommandRegistry)

Phase 1 (this PR): extract these from simulation.py and common_types.py.
Zero behavior change — pure import reorganisation.

Refactor roadmap (post-Phase 1):
- Phase 2: solvers/ extraction (Euler + Radau as SolverStrategy)
- Phase 3: reporter/events/lifecycle/disease extraction
- Phase 4: signal_bus.py + BloodShim (replace self.blood shared mutable bus)
- Phase 5: per-module INPUTS/OUTPUTS declaration migration
- Phase 6: remove BloodShim, pure SignalBus
"""
from .topology import (
    Topology,
    discover_topology,
    CONNECTIONS,
    _PARAM_PATHS,
)
from .factor_pipeline import (
    apply_factor,
    FactorCommandRegistry,
    _get_param_path,
)

__all__ = [
    "Topology",
    "discover_topology",
    "CONNECTIONS",
    "_PARAM_PATHS",
    "apply_factor",
    "FactorCommandRegistry",
    "_get_param_path",
]
