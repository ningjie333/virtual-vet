"""Numerics helpers — shared by all organ modules and solver paths.

These functions are the single source of truth for common numerical patterns.
Avoid dt-sensitive Euler discretizations (dt/tau) in favour of the exact
exponential solution (1 - exp(-dt/tau)).
"""

import math


def first_order_lag(current: float, target: float, dt: float, tau: float) -> float:
    """Exact exponential solution for dS/dt = (target - S) / tau.

    Uses 1 - exp(-dt/τ) instead of Euler's dt/τ to eliminate dt-sensitivity.
    When tau <= 0, returns target instantly (no lag).

    Called by:
      - heart._first_order_relax
      - kidney._apply_RAAS (renin lag)
      - coupling._resolve_rules (first-order lag)
      - diseases._solve_first_order_lag (Euler path)
    """
    if tau <= 0.0:
        return target
    alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
    return current + (target - current) * alpha