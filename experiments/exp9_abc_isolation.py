#!/usr/bin/env python3
"""
Experiment 9: Three-group isolation via subprocess isolation.

Three conditions:
  X (buggy):    FC no dt-scale, chemo in net_HR_add, NO continuous chemo
  Y (A-only):   FC × dt,       chemo in net_HR_add, NO continuous chemo
  Z (A+B, current): FC × dt,   chemo EXCLUDED,      HAS continuous chemo

Each condition runs in a fresh Python subprocess — no sys.modules pollution.
"""
import subprocess, json, os, sys

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp9_runner.py")
DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]
DC_VALUES = [25, 15, 10, 5]
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "exp9_abc_results.json")

def run(condition, dc, dt):
    """Run a single condition in a subprocess."""
    result = subprocess.run(
        [sys.executable, RUNNER, condition, str(dc), str(dt)],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"FAILED {condition} dc={dc} dt={dt}")
        print(result.stderr)
        return None
    return json.loads(result.stdout.strip())

# ── Main ────────────────────────────────────────────────────────────────────────
print("=" * 130)
print("  Experiment 9: Three-group isolation — A (FC dt-scaling) vs B (redundant path removal)")
print("  X = buggy:    FC NO dt-scale, chemo in net_HR_add, NO continuous chemo")
print("  Y = A-only:   FC × dt,       chemo in net_HR_add, NO continuous chemo")
print("  Z = A+B:      FC × dt,       chemo EXCLUDED,      HAS continuous chemo")
print("=" * 130)

all_results = {cond: {} for cond in ["X","Y","Z"]}

for dc in DC_VALUES:
    print(f"\n{'─'*130}")
    print(f"  DC = {dc}")
    print(f"{'─'*130}")
    header = (f"{'dt':>6} | {'X_MAP':>8} {'X_HR':>7} | {'Y_MAP':>8} {'Y_HR':>7} | "
             f"{'Z_MAP':>8} {'Z_HR':>7} || {'X→Y':>8} {'Y→Z':>8}")
    print(header)
    print("-" * 100)

    for dt in DT_SWEEP:
        rX = run("X", dc, dt)
        rY = run("Y", dc, dt)
        rZ = run("Z", dc, dt)

        if rX is None or rY is None or rZ is None:
            continue

        key = f"{dc}_{dt}"
        all_results["X"][key] = rX
        all_results["Y"][key] = rY
        all_results["Z"][key] = rZ

        dXY = rY["MAP"] - rX["MAP"]
        dYZ = rZ["MAP"] - rY["MAP"]
        print(f"{dt:>6.3f} | {rX['MAP']:>8.2f} {rX['HR']:>7.2f} | "
              f"{rY['MAP']:>8.2f} {rY['HR']:>7.2f} | "
              f"{rZ['MAP']:>8.2f} {rZ['HR']:>7.2f} || "
              f"{dXY:>+8.2f} {dYZ:>+8.2f}")

# ── Summary ─────────────────────────────────────────────────────────────────────
print("\n" + "=" * 130)
print("  Convergence Summary — MAP range across dt sweep (mmHg)")
print("=" * 130)
print(f"{'DC':>5} | {'X_range':>10} {'X_last':>9} | {'Y_range':>10} {'Y_last':>9} | "
      f"{'Z_range':>10} {'Z_last':>9} || {'A_contrib':>10} {'B_contrib':>10}")
print("-" * 120)
summary_rows = []
for dc in DC_VALUES:
    x_maps = [all_results["X"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    y_maps = [all_results["Y"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    z_maps = [all_results["Z"][f"{dc}_{dt}"]["MAP"] for dt in DT_SWEEP]
    x_range = max(x_maps) - min(x_maps)
    y_range = max(y_maps) - min(y_maps)
    z_range = max(z_maps) - min(z_maps)
    a_contrib = x_range - y_range
    b_contrib = y_range - z_range
    print(f"{dc:>5.1f} | {x_range:>10.2f} {x_maps[-1]:>9.2f} | "
          f"{y_range:>10.2f} {y_maps[-1]:>9.2f} | "
          f"{z_range:>10.2f} {z_maps[-1]:>9.2f} || "
          f"{a_contrib:>10.2f} {b_contrib:>10.2f}")
    summary_rows.append({"dc": dc, "X_range": x_range, "Y_range": y_range, "Z_range": z_range,
                          "A_contrib": a_contrib, "B_contrib": b_contrib})

print("\nInterpretation:")
print("  A_contrib = X_range - Y_range: how much MAP range improves from FC dt-scaling alone")
print("  B_contrib = Y_range - Z_range: additional improvement from removing redundant chemo path")
print("  If A_contrib >> B_contrib → A is the primary fix, B is marginal")
print("  If A_contrib ≈ B_contrib → both A and B contribute meaningfully")
print("  If B_contrib < 0         → B actually worsens things (double-counting hurts)")

out = {
    "description": "3-group isolation: A=FC dt-scaling, B=chemo redundant path removal",
    "conditions": {
        "X": "buggy: FC no dt-scale, chemo in net_HR_add, no continuous chemo",
        "Y": "A-only: FC dt-scale, chemo in net_HR_add, no continuous chemo",
        "Z": "A+B:   FC dt-scale, chemo excluded, has continuous chemo",
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