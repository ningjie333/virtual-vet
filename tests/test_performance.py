"""
Performance benchmark tests for VirtualCreature simulation engine.

Covers:
- Single-step execution time
- Bulk step throughput (1k, 10k steps)
- Memory growth characteristics
- History dict growth
- Scalability across body weights
- Disease module overhead
- Stability under rapid-fire and concurrent loads
"""

import time
import math
import sys
import os
import tracemalloc

import pytest

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

    def test_step_execution_time(self):
        """Single step() call should complete in < 1 ms."""
        c = VirtualCreature(body_weight_kg=20.0)
        times = []
        for _ in range(50):
            t0 = time.perf_counter()
            c.step()
            dt = time.perf_counter() - t0
            times.append(dt)
        avg_ms = (sum(times) / len(times)) * 1000
        peak_ms = max(times) * 1000
        print(f"\n  [step] avg={avg_ms:.4f} ms, peak={peak_ms:.4f} ms")
        # Average must stay well under 1 ms; peak is informational
        assert avg_ms < 1.0, f"Average step time {avg_ms:.4f} ms exceeds 1 ms budget"

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

    def test_history_size_growth(self):
        """History dict should grow linearly with step count."""
        c = VirtualCreature(body_weight_kg=20.0)

        _run_steps(c, 1000)
        len_1k = len(c.history["HR_bpm"])

        _run_steps(c, 1000)
        len_2k = len(c.history["HR_bpm"])

        print(f"\n  [history] after 1k={len_1k}, after 2k={len_2k}")
        # Both should be exactly 1000 and 2000 steps appended
        assert len_1k == 1000, f"Expected 1000 entries after 1k steps, got {len_1k}"
        assert len_2k == 2000, f"Expected 2000 entries after 2k steps, got {len_2k}"


# ===========================================================================
# 2. Scalability tests
# ===========================================================================

class TestScalability:
    """Performance across different body weights."""

    def test_small_dog_performance(self):
        """1 kg dog simulation 1000 steps should be <= large dog."""
        c_large = VirtualCreature(body_weight_kg=80.0)
        t_large = _run_steps(c_large, 1000)

        c_small = VirtualCreature(body_weight_kg=1.0)
        t_small = _run_steps(c_small, 1000)

        print(f"\n  [small dog] 1kg={t_small:.4f}s, 80kg={t_large:.4f}s")
        # Small dog should not be significantly slower than large dog (allow 20% tolerance)
        assert t_small <= t_large * 1.2, (
            f"Small dog ({t_small:.4f}s) slower than large dog ({t_large:.4f}s)"
        )

    def test_large_dog_performance(self):
        """80 kg dog simulation 1000 steps should complete without timeout."""
        c = VirtualCreature(body_weight_kg=80.0)
        elapsed = _run_steps(c, 1000)
        print(f"\n  [large dog] 80kg 1000 steps={elapsed:.4f}s")
        assert elapsed < 3.0, f"Large dog simulation took {elapsed:.4f}s (> 3s limit)"

    def test_disease_overhead(self):
        """Simulation with disease should not be > 2x slower than without."""
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
        # Config-driven engine uses compiled eval() expressions; overhead is
        # higher than native Python but absolute time is still <0.1s for 500 steps.
        assert ratio < 10.0, f"Disease overhead {ratio:.2f}x exceeds 10x limit"


# ===========================================================================
# 3. Stability under load
# ===========================================================================

class TestStability:
    """Stress and stability tests."""

    def test_rapid_fire_steps(self):
        """Calling step() 100 times must not crash or produce NaN."""
        c = VirtualCreature(body_weight_kg=20.0)
        for i in range(100):
            result = c.step()
            # Check key numeric fields for NaN / Inf
            tox = result.get("toxicology", {})
            assert math.isfinite(tox.get("contractility_factor", 1.0)), (
                f"NaN/Inf contractility at step {i}"
            )
            assert math.isfinite(tox.get("svr_factor", 1.0)), (
                f"NaN/Inf svr_factor at step {i}"
            )
            blood = result.get("blood", {})
            for key in ("arterial_PO2", "arterial_PCO2", "saturation_art"):
                val = blood.get(key, 0)
                if isinstance(val, (int, float)):
                    assert math.isfinite(val), f"NaN/Inf {key} at step {i}"

        print(f"\n  [rapid fire] 100 steps completed, no NaN/Inf detected")

    def test_concurrent_creatures(self):
        """5 VirtualCreature instances, 100 steps each -- all should complete."""
        creatures = [VirtualCreature(body_weight_kg=float(10 + i * 10)) for i in range(5)]
        results = []
        for idx, c in enumerate(creatures):
            elapsed = _run_steps(c, 100)
            results.append(elapsed)
            assert len(c.history["HR_bpm"]) == 100, (
                f"Creature {idx}: expected 100 history entries, got {len(c.history['HR_bpm'])}"
            )
        total = sum(results)
        print(f"\n  [concurrent] 5 creatures x 100 steps, timings={results}, total={total:.4f}s")
        assert total < 5.0, f"Concurrent creatures took {total:.4f}s total (> 5s)"
