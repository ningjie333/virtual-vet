"""validate_lsoda.py — LSODA vs Euler deviation matrix for all 10 scenarios.

Offline validation script. NOT in CI (LSODA is ~120-400× slower than Euler).
Run once to establish LSODA-specific tolerances, then update
SCENARIO_SPECIFIC_RADAU_MULTIPLIERS in src/engine/twin_run.py.

Usage:
    python tools/dev/validate_lsoda.py
"""

from __future__ import annotations

import sys
import os
import json
import time
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "src"))

from src.engine.twin_run import (
    run_twin,
    TwinRunConfig,
    SCENARIOS,
    VITAL_TOLERANCES,
    SCENARIO_MULTIPLIERS,
    SCENARIO_SPECIFIC_MULTIPLIERS,
)

# Use a shorter config for faster validation (30 steps = 3 seconds)
CONFIG = TwinRunConfig(reference_solver="radau", n_steps_prod=30, dt_prod=0.1)

# Beijing timezone for timestamps
TZ = timezone(timedelta(hours=8))

def main():
    print(f"LSODA validation run — {datetime.now(TZ).strftime('%Y-%m-%d %H:%M')} (Beijing)")
    print(f"Config: {CONFIG.n_steps_prod} steps × dt={CONFIG.dt_prod}s = {CONFIG.n_steps_prod * CONFIG.dt_prod}s")
    print(f"Reference solver: LSODA (radau)")
    print()

    results = {}
    for scenario in sorted(SCENARIOS):
        print(f"[{scenario}] ", end="", flush=True)
        t0 = time.perf_counter()
        result = run_twin(scenario, CONFIG)
        elapsed = time.perf_counter() - t0
        status = "PASS" if result.converged else "FAIL"
        print(f"{status} ({elapsed:.1f}s) worst={result.worst_vital}={result.worst_rel_error:.4f}")

        # Calculate needed multiplier for each vital
        _kind, _ = SCENARIOS[scenario]
        base_mult = SCENARIO_SPECIFIC_MULTIPLIERS.get(scenario, SCENARIO_MULTIPLIERS[_kind])

        needed = {}
        for vital, base in VITAL_TOLERANCES.items():
            err = result.max_rel_error.get(vital, 0.0)
            if err > 0:
                # Multiplier needed to make this vital pass: err / base
                needed[vital] = round(err / base, 2)

        results[scenario] = {
            "converged": result.converged,
            "elapsed_s": round(elapsed, 1),
            "worst_vital": result.worst_vital,
            "worst_error": result.worst_rel_error,
            "current_multiplier": base_mult,
            "needed_multiplier": max(needed.values()) if needed else 1.0,
            "max_rel_error": {k: round(v, 4) for k, v in result.max_rel_error.items()},
            "needed_per_vital": needed,
        }

        if not result.converged:
            for vital, base in VITAL_TOLERANCES.items():
                err = result.max_rel_error.get(vital, 0.0)
                tol = base * base_mult
                if err > tol:
                    print(f"  !! {vital:20s} err={err:.4f} tol={tol:.4f} need_mult={err/base:.1f}")

    print()

    # Summary table
    print(f"{'Scenario':35s} {'Conv':>5s} {'Current':>8s} {'Need':>8s} {'Worst':>12s} {'Time':>6s}")
    print("-" * 80)
    for scenario in sorted(results):
        r = results[scenario]
        flag = "✓" if r["converged"] else "✗"
        print(f"{scenario:35s} {flag:>5s} {r['current_multiplier']:>8.1f} {r['needed_multiplier']:>8.1f} "
              f"{r['worst_vital']}={r['worst_error']:.4f} {r['elapsed_s']:>5.1f}s")

    print()
    print("Suggested SCENARIO_SPECIFIC_RADAU_MULTIPLIERS (min = max(needed, current) + 10%):")
    print()
    for scenario in sorted(results):
        r = results[scenario]
        need = r["needed_multiplier"]
        current = r["current_multiplier"]
        suggested = max(need, current) * 1.1
        # Round up to nearest 0.5
        suggested = int(suggested * 2 + 0.5) / 2
        if r["converged"]:
            print(f"  # {scenario}: already passes with mult={current}")
        else:
            print(f'  "{scenario}": {suggested:.1f},  # need={need:.1f} current={current:.1f}')

    # Save results
    out_dir = "results/lsoda_validation"
    os.makedirs(out_dir, exist_ok=True)
    ts = datetime.now(TZ).strftime("%Y%m%d-%H%M%S")
    out_path = os.path.join(out_dir, f"{ts}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {out_path}")


if __name__ == "__main__":
    main()