#!/usr/bin/env python3
"""Test SVR multiply dt-dependency using subprocess isolation."""
import subprocess, json, os, sys

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_svr_runner.py")
DT_SWEEP = [0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001]

def run(condition, seizure_active):
    """Run one condition in subprocess."""
    result = subprocess.run(
        [sys.executable, RUNNER, condition, "seizure" if seizure_active else "baseline"],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        print(f"FAILED {condition} rc={result.returncode}")
        print(result.stderr[:300])
        return {}
    try:
        return json.loads(result.stdout.strip())
    except json.JSONDecodeError:
        print(f"BAD JSON {condition}: {result.stdout[:200]}")
        return {}

# Baseline seizure OFF — current code
print("Testing SVR multiply dt-dependency via subprocess isolation")
print("="*80)
print(f"\n{'dt':>6} | {'Base_SVR':>10} | {'S_noDT':>10} {'S_DT':>10} | {'noDT_range':>10} {'DT_range':>10}")
print("-"*80)

base_svrs = []
s_noDT = []
s_dt = []

for dt in DT_SWEEP:
    r_base = run("baseline", False)
    r_noDT = run("no_dt", True)
    r_DT = run("with_dt", True)

    base_svrs.append(r_base.get(dt, {}).get("SVR", None))
    s_noDT.append(r_noDT.get(dt, {}).get("SVR", None))
    s_dt.append(r_DT.get(dt, {}).get("SVR", None))

    print(f"{dt:>6.3f} | {str(r_base.get(dt,{}).get('SVR','-')):>10} | "
          f"{str(r_noDT.get(dt,{}).get('SVR','-')):>10} {str(r_DT.get(dt,{}).get('SVR','-')):>10} | "
          f"{str(r_noDT.get('svr_range','-')):>10} {str(r_DT.get('svr_range','-')):>10}")

# Summary
valid = [x for x in s_noDT if x]
if valid:
    print(f"\nSVR_noDT range: {max(valid)-min(valid):.4f}")
    print(f"SVR_DT range:  {max(s_dt)-min(s_dt):.4f}")