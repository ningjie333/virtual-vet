#!/usr/bin/env python3
"""
Morris Screening Sensitivity Analysis for VirtualVet coupling coefficients.

Identifies which coupling coefficients have the most impact on key outputs
(MAP, HR, GFR, pH) using the Elementary Effects method.

Usage:
    python tools/dev/sensitivity.py                     # Run analysis
    python tools/dev/sensitivity.py --output report.md  # Save to file
    python tools/dev/sensitivity.py --N 200             # Custom sample size
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

logging.disable(logging.WARNING)

# ── Parameter definitions ──────────────────────────────────────────────────
# Each entry: (name_substring, default_value, bounds)
# name_substring is matched against coupling rule names to find the rule index.

COUPLING_PARAMS = [
    {"name": "RAAS → SVR",     "default": 0.20,  "bounds": [0.05, 0.40]},
    {"name": "RAAS → 心脏收缩力", "default": 0.02,  "bounds": [0.005, 0.10]},
    {"name": "醛固酮 → 血管容积", "default": 0.035, "bounds": [0.01, 0.10]},
    {"name": "MAP → GFR",      "default": 81.0,  "bounds": [60.0, 95.0]},
    {"name": "动脉二氧化碳分压 → 呼吸驱动", "default": 0.035, "bounds": [0.01, 0.08]},
]

OUTPUT_NAMES = ["MAP", "HR", "GFR", "pH"]


def _find_rule_index(rules, name_substring: str) -> int | None:
    for i, r in enumerate(rules):
        if name_substring in r.name:
            return i
    return None


def run_baseline_with_params(params: np.ndarray) -> np.ndarray:
    """
    Run a pneumonia-moderate simulation with modified coupling coefficients.
    Uses disease scenario to activate coupling rules (healthy baseline has dormant RAAS).
    Returns: [MAP, HR, GFR, pH] at t=30s (after disease progression).
    """
    from simulation import VirtualCreature
    from src.diseases import create_disease

    c = VirtualCreature(body_weight_kg=20.0)
    engine = c.coupling_engine

    # Apply parameter overrides directly to rule fn_expr
    for param_info, value in zip(COUPLING_PARAMS, params):
        idx = _find_rule_index(engine.rules, param_info["name"])
        if idx is None:
            continue

        rule = engine.rules[idx]
        old_val = param_info["default"]

        if param_info["name"] == "MAP → GFR":
            old_fn = rule.fn_expr
            new_fn = old_fn.replace(f">= {old_val:.1f}", f">= {value:.1f}")
            new_fn = new_fn.replace(f"/ {old_val - 40:.1f}", f"/ {value - 40:.1f}")
            rule.fn_expr = new_fn
        else:
            old_fn = rule.fn_expr
            new_fn = old_fn.replace(str(old_val), f"{value:.6f}")
            rule.fn_expr = new_fn

    # Hemorrhage: 800mL blood loss at t=2s activates RAAS thresholds
    c.schedule_event(2.0, "blood_loss", {"volume_ml": 800.0})

    # Run 50 steps (5 simulated seconds) — enough for RAAS to activate post-hemorrhage
    for _ in range(50):
        c.step()

    return np.array([
        c.heart.mean_arterial_pressure,
        c.heart.heart_rate,
        c.kidney.GFR,
        c.blood.arterial_pH,
    ])


def morris_sample(problem: dict, N: int, num_levels: int = 4) -> np.ndarray:
    """Generate Morris elementary effects trajectories."""
    D = problem["num_vars"]
    bounds = np.array(problem["bounds"])
    delta = 1.0 / (num_levels - 1)

    samples = []
    for _ in range(N):
        x0 = np.random.uniform(0, 1 - delta, D)
        trajectory = [x0.copy()]
        order = np.random.permutation(D)
        for idx in order:
            x = trajectory[-1].copy()
            step_dir = 1 if np.random.random() > 0.5 else -1
            x[idx] = np.clip(x[idx] + delta * step_dir, 0, 1)
            trajectory.append(x)
        samples.extend(trajectory)

    X = np.array(samples)
    for i in range(D):
        X[:, i] = bounds[i, 0] + X[:, i] * (bounds[i, 1] - bounds[i, 0])
    return X


def morris_analyze(problem: dict, X: np.ndarray, Y: np.ndarray, num_levels: int = 4) -> dict:
    """Compute Morris μ* and σ for each output."""
    D = problem["num_vars"]
    delta = 1.0 / (num_levels - 1)
    n_traj = X.shape[0] // (D + 1)
    n_outputs = Y.shape[1]

    results = {}
    for out_idx in range(n_outputs):
        mu_star = np.zeros(D)
        sigma = np.zeros(D)
        counts = np.zeros(D)

        for traj in range(n_traj):
            start = traj * (D + 1)
            y_traj = Y[start:start + D + 1, out_idx]
            x_traj = X[start:start + D + 1]

            for step in range(D):
                diff = x_traj[step + 1] - x_traj[step]
                changed = np.argmax(np.abs(diff))
                ee = (y_traj[step + 1] - y_traj[step]) / delta
                mu_star[changed] += abs(ee)
                sigma[changed] += ee
                counts[changed] += 1

        for i in range(D):
            if counts[i] > 0:
                mu_star[i] /= counts[i]
                sigma[i] /= counts[i]

        results[OUTPUT_NAMES[out_idx]] = {
            "mu_star": mu_star.tolist(),
            "sigma": sigma.tolist(),
        }

    return results


def main():
    parser = argparse.ArgumentParser(description="Morris sensitivity analysis")
    parser.add_argument("--N", type=int, default=50, help="Number of trajectories")
    parser.add_argument("--output", "-o", help="Output file")
    parser.add_argument("--levels", type=int, default=4, help="Grid levels")
    args = parser.parse_args()

    problem = {
        "num_vars": len(COUPLING_PARAMS),
        "names": [p["name"] for p in COUPLING_PARAMS],
        "bounds": [p["bounds"] for p in COUPLING_PARAMS],
    }

    total_sims = args.N * (problem["num_vars"] + 1)
    print(f"Morris Screening: {args.N} trajectories, {problem['num_vars']} parameters")
    print(f"Total simulations: {total_sims}")

    X = morris_sample(problem, N=args.N, num_levels=args.levels)

    Y = np.zeros((X.shape[0], len(OUTPUT_NAMES)))
    t0 = time.time()
    failed = 0
    for i in range(X.shape[0]):
        try:
            Y[i] = run_baseline_with_params(X[i])
        except Exception:
            Y[i] = np.nan
            failed += 1
        if (i + 1) % 50 == 0:
            elapsed = time.time() - t0
            eta = elapsed / (i + 1) * (X.shape[0] - i - 1)
            print(f"  {i+1}/{X.shape[0]} ({elapsed:.0f}s, ~{eta:.0f}s remaining)")

    elapsed = time.time() - t0
    print(f"Done: {elapsed:.1f}s ({elapsed/X.shape[0]:.2f}s/sim), {failed} failed")

    for j in range(Y.shape[1]):
        col = Y[:, j]
        nan_mask = np.isnan(col)
        if nan_mask.any() and not nan_mask.all():
            col[nan_mask] = np.nanmean(col)

    results = morris_analyze(problem, X, Y, num_levels=args.levels)

    lines = [
        "# Morris Screening Sensitivity Analysis",
        "",
        f"- Trajectories: {args.N}",
        f"- Grid levels: {args.levels}",
        f"- Total simulations: {X.shape[0]}",
        f"- Runtime: {elapsed:.1f}s",
        "",
    ]

    for out_name in OUTPUT_NAMES:
        r = results[out_name]
        lines.append(f"## Output: {out_name}")
        lines.append("")
        lines.append("| Parameter | μ* | σ | Rank |")
        lines.append("|---|---|---|---|")

        mu_stars = np.array(r["mu_star"])
        ranks = np.argsort(-mu_stars) + 1

        for i, param in enumerate(COUPLING_PARAMS):
            lines.append(f"| {param['name']} | {r['mu_star'][i]:.4f} | {r['sigma'][i]:.4f} | #{ranks[i]} |")
        lines.append("")

    report = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + report)


if __name__ == "__main__":
    main()
