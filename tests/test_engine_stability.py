"""Engine stability and non-crash contracts that are not pure benchmarks."""

import math
import os
import sys

_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_project_root, "src"))
sys.path.insert(0, _project_root)

from simulation import VirtualCreature


def _run_steps(creature: VirtualCreature, n: int) -> None:
    for _ in range(n):
        creature.step()


class TestHistoryGrowth:
    """History growth is correctness, not a performance budget."""

    def test_history_size_growth(self):
        """History dict should grow linearly with step count."""
        c = VirtualCreature(body_weight_kg=20.0)

        _run_steps(c, 1000)
        len_1k = len(c.history["HR_bpm"])

        _run_steps(c, 1000)
        len_2k = len(c.history["HR_bpm"])

        assert len_1k == 1000, f"Expected 1000 entries after 1k steps, got {len_1k}"
        assert len_2k == 2000, f"Expected 2000 entries after 2k steps, got {len_2k}"


class TestStability:
    """Stress and non-crash contracts."""

    def test_rapid_fire_steps(self):
        """Calling step() 100 times must not crash or produce NaN."""
        c = VirtualCreature(body_weight_kg=20.0)
        for i in range(100):
            result = c.step()
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

    def test_concurrent_creatures(self):
        """5 VirtualCreature instances, 100 steps each -- all should complete."""
        creatures = [VirtualCreature(body_weight_kg=float(10 + i * 10)) for i in range(5)]
        for idx, creature in enumerate(creatures):
            _run_steps(creature, 100)
            assert len(creature.history["HR_bpm"]) == 100, (
                f"Creature {idx}: expected 100 history entries, got "
                f"{len(creature.history['HR_bpm'])}"
            )
