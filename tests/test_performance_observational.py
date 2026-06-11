"""Observation-only performance budgets that are currently too machine-sensitive for hard gating."""

from __future__ import annotations

import os
import sys
import time

import pytest

pytestmark = pytest.mark.slower

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "src"))
sys.path.insert(0, _project_root)

from simulation import VirtualCreature
from src.diseases import create_disease


def _run_steps(creature: VirtualCreature, n: int) -> float:
    t0 = time.perf_counter()
    for _ in range(n):
        creature.step()
    return time.perf_counter() - t0


@pytest.mark.xfail(
    strict=False,
    reason="Local-machine throughput budget is informative only until benchmark policy is formalized.",
)
def test_step_execution_time_budget():
    """Single-step wall time is tracked, but not yet enforced as a stable hard gate."""
    creature = VirtualCreature(body_weight_kg=20.0)
    times = []
    for _ in range(50):
        t0 = time.perf_counter()
        creature.step()
        times.append(time.perf_counter() - t0)

    avg_ms = (sum(times) / len(times)) * 1000
    assert avg_ms < 1.0, f"Average step time {avg_ms:.4f} ms exceeds 1 ms budget"


@pytest.mark.xfail(
    strict=False,
    reason="Absolute disease-path wall time is informative only until benchmark policy is formalized.",
)
def test_disease_path_absolute_budget():
    """Absolute disease-path wall time is tracked separately from the ratio guard."""
    creature = VirtualCreature(body_weight_kg=20.0)
    disease = create_disease("pneumonia", severity="moderate")
    creature.attach_disease(disease)
    elapsed = _run_steps(creature, 500)
    assert elapsed < 4.0, f"Disease path took {elapsed:.4f}s for 500 steps"


@pytest.mark.xfail(
    strict=False,
    reason=(
        "Cross-body-weight runtime ordering is informative only until a "
        "benchmark policy defines whether this should be stable across machines."
    ),
)
def test_small_dog_not_significantly_slower_than_large_dog():
    """Track body-weight runtime ordering without hard-gating the repo on it."""
    c_large = VirtualCreature(body_weight_kg=80.0)
    t_large = _run_steps(c_large, 1000)

    c_small = VirtualCreature(body_weight_kg=1.0)
    t_small = _run_steps(c_small, 1000)

    assert t_small <= t_large * 1.2, (
        f"Small dog ({t_small:.4f}s) slower than large dog ({t_large:.4f}s)"
    )
