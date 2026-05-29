#!/usr/bin/env python3
"""
Experiment 9: Four-group isolation via subprocess isolation.

Four conditions:
  X (buggy):      FC no dt-scale, chemo in net_HR_add, NO continuous chemo
  Y (A-only):     FC × dt,       chemo in net_HR_add, NO continuous chemo
  W (A+path):     FC × dt,       chemo EXCLUDED,      HAS continuous chemo (gain=10)
  Z (A+B,current):FC × dt,       chemo EXCLUDED,      HAS continuous chemo (gain=15)
  ─────────────────────────────────────────────────────────────────────
  A_contrib = X_range − Y_range     (effect of FC dt-scaling)
  B_contrib = Y_range − W_range     (effect of path consolidation, same gain)
  C_contrib = W_range − Z_range     (effect of gain change 10→15)

Each condition runs in a fresh Python subprocess — no sys.modules pollution.
"""
import subprocess, json, os, sys

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp9_runner.py")
DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
DC_VALUES = [25, 15, 10, 5]
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp9_abc_results.json")

def run(condition, dc, dt, max_retries=2):
    """Run a single condition in a subprocess, with retries."""
    for attempt in range(max_retries + 1):
        try:
            result = subprocess.run(
                [sys.executable, RUNNER, condition, str(dc), str(dt)],
                capture_output=True, text=True, timeout=600
            )
        except subprocess.TimeoutExpired:
            print(f"  TIMEOUT {condition} dc={dc} dt={dt} (attempt {attempt+1})")
            continue
        if result.returncode == 0:
            return json.loads(result.stdout.strip())
        print(f"  FAILED {condition} dc={dc} dt={dt} (attempt {attempt+1})")
        print(f"  stderr: {result.stderr.strip()}")
    return None

# ── Main ────────────────────────────────────────────────────────────────────────
print("=" * 140)
print("  Experiment 9: Four-group isolation — A (FC dt-scaling) vs B (path consolidation) vs C (gain)")
print("  X = buggy:     FC NO dt-scale, chemo in net_HR_add, NO continuous chemo")
print("  Y = A-only:    FC × dt,       chemo in net_HR_add, NO continuous chemo")
print("  W = A+path:    FC × dt,       chemo EXCLUDED,      HAS continuous chemo (gain=10)")
print("  Z = A+B:       FC × dt,       chemo EXCLUDED,      HAS continuous chemo (gain=15)")
print("=" * 140)

CONDITIONS = ["X", "Y", "W", "Z"]
all_results = {cond: {} for cond in CONDITIONS}

for dc in DC_VALUES:
    print(f"\n{'─'*140}")
    print(f"  DC = {dc}")
    print(f"{'─'*140}")
    header = (f"{'dt':>6} | {'X_MAP':>8} {'X_HR':>7} | {'Y_MAP':>8} {'Y_HR':>7} | "
             f"{'W_MAP':>8} {'W_HR':>7} | {'Z_MAP':>8} {'Z_HR':>7}")
    print(header)
    print("-" * 110)

    for dt in DT_SWEEP:
        rX = run("X", dc, dt)
        rY = run("Y", dc, dt)
        rW = run("W", dc, dt)
        rZ = run("Z", dc, dt)

        if rX is None or rY is None or rW is None or rZ is None:
            continue

        key = f"{dc}_{dt}"
        all_results["X"][key] = rX
        all_results["Y"][key] = rY
        all_results["W"][key] = rW
        all_results["Z"][key] = rZ

        print(f"{dt:>6.3f} | {rX['MAP']:>8.2f} {rX['HR']:>7.2f} | "
              f"{rY['MAP']:>8.2f} {rY['HR']:>7.2f} | "
              f"{rW['MAP']:>8.2f} {rW['HR']:>7.2f} | "
              f"{rZ['MAP']:>8.2f} {rZ['HR']:>7.2f}")

# ── Summary ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 140)
print("  Convergence Summary — MAP range across dt sweep (mmHg)")
print("=" * 140)
print(f"{'DC':>5} | {'X_range':>10} {'Y_range':>10} {'W_range':>10} {'Z_range':>10} || "
      f"{'A_contrib':>10} {'B_contrib':>10} {'C_contrib':>10}")
print("-" * 120)
summary_rows = []
for dc in DC_VALUES:
    x_maps = [all_results["X"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    y_maps = [all_results["Y"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    w_maps = [all_results["W"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    z_maps = [all_results["Z"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    x_range = max(x_maps) - min(x_maps)
    y_range = max(y_maps) - min(y_maps)
    w_range = max(w_maps) - min(w_maps)
    z_range = max(z_maps) - min(z_maps)
    a_contrib = x_range - y_range
    b_contrib = y_range - w_range
    c_contrib = w_range - z_range
    print(f"{dc:>5.1f} | {x_range:>10.2f} {y_range:>10.2f} {w_range:>10.2f} {z_range:>10.2f} || "
          f"{a_contrib:>10.2f} {b_contrib:>10.2f} {c_contrib:>10.2f}")
    summary_rows.append({
        "dc": dc,
        "X_range": x_range, "Y_range": y_range, "W_range": w_range, "Z_range": z_range,
        "A_contrib": a_contrib, "B_contrib": b_contrib, "C_contrib": c_contrib
    })

print("\nInterpretation:")
print("  A_contrib = X_range - Y_range:   FC dt-scaling effect")
print("  B_contrib = Y_range - W_range:   path consolidation effect (same gain=10)")
print("  C_contrib = W_range - Z_range:   gain change effect (10→15)")
print("  If A_contrib >> B_contrib ≈ 0 → A is the sole fix; path consolidation and gain are negligible")

out = {
    "description": "4-group isolation: A=FC dt-scaling, B=path consolidation, C=gain 10→15",
    "conditions": {
        "X": "buggy: FC no dt-scale, chemo in net_HR_add, no continuous chemo",
        "Y": "A-only: FC dt-scale, chemo in net_HR_add, no continuous chemo",
        "W": "A+path: FC dt-scale, chemo excluded, has continuous chemo (gain=10)",
        "Z": "A+B:   FC dt-scale, chemo excluded, has continuous chemo (gain=15)",
    },
    "dt_sweep": DT_SWEEP,
    "dc_values": DC_VALUES,
    "t_end": 60.0,
    "summary": summary_rows,
    "raw": all_results,
}
with open(OUT_PATH, "w") as f:
    json.dump(out, f, indent=2)
print(f"\nSaved to {OUT_PATH}")