"""
Engine subpackage — architectural refactor.

This subpackage centralises engine-level data structures and protocols:
- `topology`: parameter registry (_PARAM_PATHS)
- `factor_pipeline`: FactorCommand dispatch (apply_factor, FactorCommandRegistry)
- `step_contract`: StepGuard runtime ordering contracts (R3)
"""
from .topology import (
    Topology,
    discover_topology,
    _PARAM_PATHS,
)
from .factor_pipeline import (
    apply_factor,
    FactorCommandRegistry,
    _get_param_path,
)
from .step_contract import (
    StepGuard,
    StepContractError,
)

__all__ = [
    "Topology",
    "discover_topology",
    "_PARAM_PATHS",
    "apply_factor",
    "FactorCommandRegistry",
    "_get_param_path",
    "StepGuard",
    "StepContractError",
]
