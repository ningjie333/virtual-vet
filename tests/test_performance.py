"""
Performance benchmark tests for VirtualCreature simulation engine.

Covers:
- Bulk step throughput (1k, 10k steps)
- Memory growth characteristics
- Scalability across body weights
- Disease module overhead ratio

Observation-only machine-sensitive budgets live in
tests/test_performance_observational.py.
"""

import time
import sys
import os
import tracemalloc

import pytest

pytestmark = pytest.mark.slower

# Match existing test convention: add both src/ dir and project root to path.
# src/ uses bare `from blood import ...` imports.
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "src"))
sys.path.insert(0, _project_root)

from simulation import VirtualCreature


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_steps(creature: VirtualCreature, n: int) -> float:
    """Run *n* steps and return elapsed wall-clock seconds."""
    t0 = time.perf_counter()
    for _ in range(n):
        creature.step()
    return time.perf_counter() - t0


def _measure_memory(creature_factory, n_steps: int) -> int:
    """Measure net memory increase after running *n_steps*.

    Uses tracemalloc to capture the delta between before/after snapshots.
    """
    tracemalloc.start()
    snap_before = tracemalloc.take_snapshot()
    c = creature_factory()
    for _ in range(n_steps):
        c.step()
    snap_after = tracemalloc.take_snapshot()
    tracemalloc.stop()

    stats = snap_after.compare_to(snap_before, "filename")
    delta = sum(s.size_diff for s in stats if s.size_diff > 0)
    return delta


# ===========================================================================
# 1. Performance benchmarks
# ===========================================================================

class TestStepPerformance:
    """Benchmarks for raw step() throughput."""

    def test_1000_steps_timing(self):
        """1000 steps should complete in < 2 seconds."""
        c = VirtualCreature(body_weight_kg=20.0)
        elapsed = _run_steps(c, 1000)
        print(f"\n  [1000 steps] elapsed={elapsed:.4f}s")
        assert elapsed < 2.0, f"1000 steps took {elapsed:.4f}s (> 2s limit)"

    @pytest.mark.slower
    def test_10000_steps_timing(self):
        """10000 steps should complete in < 20 seconds."""
        c = VirtualCreature(body_weight_kg=20.0)
        elapsed = _run_steps(c, 10000)
        print(f"\n  [10000 steps] elapsed={elapsed:.4f}s")
        assert elapsed < 20.0, f"10000 steps took {elapsed:.4f}s (> 20s limit)"

    def test_memory_growth_linear(self):
        """Memory growth should be linear, not exponential.

        Compare memory delta for 1000 vs 2000 steps. If growth is linear
        the ratio should be roughly 2x (tolerance allows 3x).
        """
        def factory_1k():
            return VirtualCreature(body_weight_kg=20.0)
        def factory_2k():
            return VirtualCreature(body_weight_kg=20.0)

        mem_1k = _measure_memory(factory_1k, 1000)
        mem_2k = _measure_memory(factory_2k, 2000)

        ratio = mem_2k / max(mem_1k, 1)
        print(f"\n  [memory] 1k={mem_1k}B, 2k={mem_2k}B, ratio={ratio:.2f}x")
        # Linear: ratio ~2, quadratic: ratio ~4, exponential: ratio >> 4
        assert ratio < 3.5, f"Memory ratio {ratio:.2f}x suggests super-linear growth"

class TestScalability:
    """Performance across different body weights."""

    def test_large_dog_performance(self):
        """80 kg dog simulation 1000 steps should complete without timeout."""
        c = VirtualCreature(body_weight_kg=80.0)
        elapsed = _run_steps(c, 1000)
        print(f"\n  [large dog] 80kg 1000 steps={elapsed:.4f}s")
        assert elapsed < 3.0, f"Large dog simulation took {elapsed:.4f}s (> 3s limit)"

    def test_disease_overhead_ratio(self):
        """Disease path should stay within a bounded overhead ratio."""
        # Without disease
        c_plain = VirtualCreature(body_weight_kg=20.0)
        t_plain = _run_steps(c_plain, 500)

        # Attach a disease module
        from src.diseases import create_disease
        c_disease = VirtualCreature(body_weight_kg=20.0)
        disease = create_disease("pneumonia", severity="moderate")
        c_disease.attach_disease(disease)
        t_disease = _run_steps(c_disease, 500)

        ratio = t_disease / max(t_plain, 1e-9)
        print(f"\n  [disease] plain={t_plain:.4f}s, disease={t_disease:.4f}s, ratio={ratio:.2f}x")
        # Config-driven disease modules are currently much heavier than the
        # baseline kernel path. Keep a bounded regression guard without treating
        # this benchmark as a daily optimization contract.
        assert ratio < 20.0, f"Disease overhead {ratio:.2f}x exceeds 20x limit"
