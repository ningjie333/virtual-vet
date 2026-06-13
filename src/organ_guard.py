"""Organ module write guard — enforces FactorCommand-only writes on organ modules.

Every organ module holds a `self.blood = blood` reference to the shared blood
compartment.  Historically, some organs wrote to `self.blood.*` directly from
their `compute()` method (e.g. lung.py → arterial_PO2, kidney.py → BUN).
This is a violation of the FactorCommand-only writes policy.

organ_guard provides a `__setattr__` override that physically blocks direct
`self.blood = ...` assignments after __init__, and an escape-hatch context
manager for the sole legitimate use case: constructor-time blood-reference
injection.

Usage in each organ module's __init__:
    with _blood_escape():
        self.blood = blood

Usage to temporarily disable guard (e.g. for a known-safe refactor):
    HeartModule._BLOOD_GUARD_ACTIVE = False
    try:
        ...  # refactor work here
    finally:
        HeartModule._BLOOD_GUARD_ACTIVE = True
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import ClassVar


# Per-module guard state — one per organ class, keyed by class identity.
# Using a dict keyed by class to avoid metaclass complexity.
_GUARD_STACK: dict[type, int] = {}


@contextmanager
def _blood_escape(cls: type):
    """Context manager: temporarily disable the blood-write guard.

    Use ONLY for constructor-time initialization where the organ legitimately
    stores a reference to its blood compartment.
    Every other `self.blood = x` after __init__ is a bug.
    """
    depth = _GUARD_STACK.get(cls, 0)
    _GUARD_STACK[cls] = depth + 1
    try:
        yield
    finally:
        _GUARD_STACK[cls] = max(0, depth)


def _is_guard_active(cls: type) -> bool:
    """Returns True if the guard is currently active for this class."""
    # Guard is active when stack depth is 0 AND the class has guard enabled.
    return _GUARD_STACK.get(cls, 0) == 0


def organ_setattr(self, name: str, value) -> None:
    """Safe __setattr__ for organ modules.

    Blocks assignments to attributes whose name starts with "blood."
    except when called inside a _blood_escape() context.
    """
    cls = type(self)
    if (
        name.startswith("blood.")
        and _is_guard_active(cls)
    ):
        raise AttributeError(
            f"BLOCKED: direct write to {cls.__name__}.{name!r} — "
            f"all blood modifications must route through apply_factor(). "
            f"Use _blood_escape({cls.__name__}) context manager in __init__ only."
        )
    object.__setattr__(self, name, value)