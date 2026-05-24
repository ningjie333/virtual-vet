# CCF-C Paper — Revised Experiments Roadmap
**Date**: 2026-05-23
**Core Claim**: "Single-step explicit Euler converges (1st-order) for dt≤0.05 but has an explosion threshold at dt≈0.1; sequential coupling (Euler organ loop) introduces an O(1) structural error (~1.3 mmHg) independent of dt; unified-RHS implicit solving (Radau IIA) achieves both stability and accuracy with better efficiency."

---

## Current Status

| Done | Description |
|---|---|
| ✅ | Figure 4 pilot data — coupling comparison (Euler dt={0.001,0.01,0.05,0.1} + Radau rtol=1e-4 + Ref rtol=1e-10) |
| ✅ | Figure 4 Nature-style panels (a)(b)(c)(d) |
| ✅ | Blood volume dydt sign bug fixed |
| ✅ | MAP filtered sync bug fixed |
| ✅ | Figure 5 convergence study — Pure Euler converges (1st-order), Sequential Euler has O(1) structural error |

| Missing | Description |
|---|---|
| ❌ | Convergence study (state-vector L2 norm, proper reference at rtol=1e-10) |
| ❌ | Pure Euler vs Sequential Euler three-way comparison |
| ❌ | Stiffness quantification via Newton iteration counts |
| ❌ | Severity Pareto (200/400/800 mL full curves + spot check) |
| ❌ | Physiological validation (5 quick checks, not 2-3 weeks) |

---

## Priority Tiers

```
P0 (Must-have, Week 1)     ── Core claim proof: convergence + pure vs sequential
P1 (Must-have, Week 1-2)   ── Stiffness + severity Pareto + reference quality check
P2 (Should-have, Week 2)   ── Physiological validation (5 quick checks)
P3 (Nice-to-have)          ── Sobol sensitivity (defer, not core claim)
```

---

## P0 Experiments

### P0-1: Convergence Study (State-Vector L2 Norm)
**Script**: `experiments/convergence_study.py`

**Goal**: Prove that ALL Euler variants plateau at same RMSE (~8-9) due to stability-bound divergence — this is itself a publishable finding. Also establish that Radau at rtol=1e-4 is NOT reference quality (RMSE=0.052 vs rtol=1e-10).

**Design**:
- Reference: `solve_ivp(..., method="Radau", rtol=1e-10, atol=1e-12, max_step=0.1)` — runs once, reuse for all comparisons
- dt grid: `{0.5, 0.25, 0.1, 0.05, 0.025, 0.01, 0.005, 0.0025, 0.001, 0.0005, 0.0001}`
- Two comparison paths:
  - **Pure Euler**: single `y_new = y + dt * f(t, y)` call (ONE unified RHS evaluation per step — no organ loop)
  - **Sequential Euler**: current organ-by-organ loop with `vc.step()` (intermediate state propagation between organs)
- State vector: pack full `y` at each save point, compute L2 norm vs reference trajectory
- L2 norm formula: `sqrt(sum((y_i_ref - y_i_test)^2))` for all state variables at each t, then RMSE over time

**Pass/Fail**:
- PASS: Euler RMSE plateaus at ~8-9 for dt ≤ 0.01 (confirms structural bottleneck)
- PASS: Radau rtol=1e-4 shows RMSE=0.05 vs reference (confirms rtol=1e-10 is needed for reference quality)
- FAIL: Euler dt→0 RMSE→0 → would disprove the core claim (unlikely given pilot data)

**Output**:
- `experiments/convergence_study_data.json` — per-method per-dt: `{dt, method, rmse_L2, rmse_MAP, max_MAP_dev, min_MAP, time_s, newton_iters?}`
- `experiments/figure_convergence.svg/pdf/tiff` — log-log plot, two panels:
  - (a) Full convergence curve: all Euler dt + Radau rtol values
  - (b) Zoom on small-dt region showing Euler plateau vs Radau convergence

**Time estimate**: ~3 hours (reference trajectory computed once, ~4700s; reuse across dt grid)

---

### P0-2: Pure Euler vs Sequential Euler Three-Way Comparison
**Script**: `experiments/pure_vs_sequential_euler.py`

**Goal**: Disambiguate whether the bottleneck is (a) the explicit method itself or (b) the sequential coupling strategy.

**Design** — three-way comparison on 400 mL shock:

| Method | Definition | Implementation |
|---|---|---|
| **Pure Euler** | `y_new = y + dt * f_unified(t, y)` — ONE call to the full unified RHS per step | Patch `simulation.py` to add `pure_euler_step(dt)` that does one `f_unified` call then advances `current_time_s` |
| **Sequential Euler** | Current organ-by-organ: loop over all organs with intermediate state updates | Existing `vc.step()` |
| **Radau** | Unified RHS + Radau IIA | Existing `run_unified_ivp()` |

**What to measure**:
- MAP trajectory, HR trajectory
- L2 state-vector RMSE vs reference
- Computing time

**Pass/Fail**:
- If **Pure Euler ≈ Sequential Euler** → problem is the explicit method, not the coupling strategy
- If **Sequential Euler ≫ Pure Euler** (much worse) → coupling strategy is the bottleneck
- Expected: Pure Euler ≈ Sequential Euler (both are explicit Euler), both ≫ Radau

**Output**:
- `experiments/pure_vs_sequential_data.json`
- `experiments/figure_pure_vs_sequential.svg/pdf/tiff` — three-panel time series (MAP, HR, CO) + error table

**Time estimate**: ~2 hours

---

## P1 Experiments

### P1-1: Stiffness Quantification via Newton Iteration Counts
**Script**: `experiments/stiffness_analysis.py`

**Goal**: Quantify stiffness ratio without computing Jacobian directly. Use Radau Newton iteration count per step as a proxy — directly measurable, no extra code needed.

**Design**:
- Patch `simulation.py` to count Newton iterations in Radau's `_unified_rhs` (or use `scipy.integrate.OdeSolver` stats if available)
- Alternatively: count `J_transpose` formations or function evaluations in Newton loop
- Run on 400 mL shock with Radau rtol=1e-4 and Radau rtol=1e-10
- Plot: iteration count vs time (shows stiffness surge during acute blood loss)

**What to measure**:
- Mean/newton iterations per step (before/during/after shock)
- Stiffness ratio estimate: `iterations_during_shock / iterations_at_rest`

**Pass/Fail**:
- If iterations spike >3× during shock → confirms stiffness problem (justification for implicit method)
- If iterations stay constant → system is not stiff in this regime (would undermine core claim slightly)

**Output**:
- `experiments/stiffness_data.json`
- `experiments/figure_stiffness.svg/pdf` — iteration count time series + histogram

**Time estimate**: ~1 hour

---

### P1-2: Severity Pareto (200/400/800 mL)
**Script**: `experiments/severity_pareto.py`

**Goal**: Show that the Radau advantage holds across severity levels (200 mL = mild, 400 mL = moderate, 800 mL = severe).

**Design**:

| Scenario | Volume | Full curves? | Euler dt values |
|---|---|---|---|
| 200 mL (Class I) | 400 mL (Class II) | 800 mL (Class III-IV) | |
| 200 mL | Full | dt={0.05, 0.01} | 2 curves |
| 400 mL | Full | dt={0.05, 0.01} | 2 curves |
| 800 mL | Spot check only (3 time points: t=10, 30, 60) | dt=0.05 | 1 curve |

Rationale: 800 mL is near-lethal; full Euler curves are expensive and may explode. Spot check confirms same pattern holds.

**What to measure**:
- MAP/HR/CO trajectories for 200 mL and 400 mL (all methods)
- min_MAP, time_to_recover for each severity
- Radau vs Euler Pareto frontier per severity

**Pass/Fail**:
- Radau Pareto-dominates Euler across all three severity levels
- Higher severity → larger Radau speedup (more stiff)

**Output**:
- `experiments/severity_pareto_data.json`
- `experiments/figure_severity_pareto.svg/pdf/tiff` — three-row panel (200/400/800 mL), each with MAP time series + Pareto frontier inset

**Time estimate**: ~2 hours

---

### P1-3: Reference Quality Check (rtol=1e-10 vs rtol=1e-4)
**Script**: `experiments/reference_quality_check.py`

**Goal**: Verify that rtol=1e-10 actually produces different results from rtol=1e-4 — confirming the "reference quality" label is justified.

**Design**:
- Compare Radau rtol=1e-4 vs rtol=1e-10 on 400 mL scenario
- Compute L2 norm difference at all save points
- Check: does rtol=1e-10 produce measurably different min_MAP or transient timing?

**From pilot data**:
- `rmse_MAP` at rtol=1e-4 vs rtol=1e-10 = 0.052 (small but non-zero)
- min_MAP difference: 81.7 (rtol=1e-4) vs ~81.66 (rtol=1e-10) — negligible
- But steady-state error: 0.003 mmHg (rtol=1e-4) vs 0 (rtol=1e-10) — also negligible

**Pass/Fail**:
- If min_MAP differs by >0.5 mmHg → reference quality is justified
- If not → rtol=1e-10 is overkill; rtol=1e-6 might suffice as reference

**Output**:
- `experiments/reference_quality_data.json`
- Short section in paper: "Reference solution validation" with table

**Time estimate**: ~1 hour (already computed in pilot — confirm with new script)

---

## P2 Experiments

### P2-1: Physiological Validation (5 Quick Checks)
**Script**: `experiments/physio_validation.py`

**Goal**: Confirm VetSim produces physiologically plausible responses — reject clearly wrong trajectories. NOT a 2-3 week exhaustive validation.

**5 Checks** (each ~30 min to code + run):

| # | Check | What to measure | Pass criterion | Fail trigger |
|---|---|---|---|---|
| 1 | **MAP shape** | MAP trajectory 0–60s | Starts ~100 mmHg, drops to 40–70 mmHg, recovers toward 90-100 | Flat, rising, or >100 mmHg drop |
| 2 | **HR compensation** | HR at t=30s | >20 bpm above baseline (85→≥105) | Flat or decreasing HR |
| 3 | **CO/BV/SVR consistency** | CO, BV, SVR at t=30s | CO↓ AND BV↓ AND SVR↑ together | Any one moving opposite direction |
| 4 | **Conservation audit** | All state variables | No negatives in blood volume, SV, HR; signs correct | Any negative or wrong sign |
| 5 | **dt sensitivity** | MAP at t=30s for dt={0.1, 0.05, 0.01} | Converged (change <5% between dt values) | Divergent with smaller dt |

**Implementation**: Single script `physio_validation.py` runs all 5 checks, outputs a `PASS/FAIL` row per check. Run once, takes <5 minutes.

**Output**:
- `experiments/physio_validation_data.json` — 5 rows × `{check, passed, details}`
- Results table embedded in paper "Physiological validation" section

**Time estimate**: ~4 hours (code + run + document)

---

## P3 Experiments (Defer)

### Sobol Sensitivity Analysis (Figure 7)
**Keep in roadmap** but deprioritize to Week 3+. Not needed for core claim; can strengthen Discussion section.

---

## Execution Timeline

```
Week 1 (Days 1-5)
  Day 1 AM  ── Write convergence_study.py + pure_vs_sequential_euler.py
  Day 1 PM  ── Run reference trajectory (once, 4700s → run in background)
  Day 2 AM  ── Post-process reference, run all dt values
  Day 2 PM  ── Generate figure_convergence.svg + figure_pure_vs_sequential.svg
  Day 3 AM  ── Write stiffness_analysis.py + severity_pareto.py
  Day 3 PM  ── Run stiffness + severity experiments
  Day 4 AM  ── Write physio_validation.py, run 5 checks
  Day 4 PM  ── Generate all figures, verify pass/fail criteria
  Day 5     ── First draft of Results section

Week 2
  Day 6-7   ── Introduction + Methods writing
  Day 8-9   ── Discussion (relate to physiology literature)
  Day 10    ── Final figure assembly + Appendix
```

---

## File Manifest

```
experiments/
  convergence_study.py          # P0-1
  convergence_study_data.json
  figure_convergence.svg/pdf/tiff

  pure_vs_sequential_euler.py   # P0-2
  pure_vs_sequential_data.json
  figure_pure_vs_sequential.svg/pdf/tiff

  stiffness_analysis.py         # P1-1
  stiffness_data.json
  figure_stiffness.svg/pdf

  severity_pareto.py            # P1-2
  severity_pareto_data.json
  figure_severity_pareto.svg/pdf/tiff

  reference_quality_check.py    # P1-3
  reference_quality_data.json

  physio_validation.py          # P2-1
  physio_validation_data.json

  # Legacy (already done)
  coupling_comparison.py        # (already exists)
  coupling_comparison_data.json
  figure4_nature.svg/pdf/tiff
```

---

## Pass/Fail Criteria Summary

| Experiment | Pass | Fail |
|---|---|---|
| P0-1 Convergence | Euler RMSE plateau ~8-9; Radau rtol=1e-4 RMSE=0.05 vs ref | Euler converges to 0; Radau not better than Euler |
| P0-2 Pure vs Sequential | Pure ≈ Sequential (both ≫ Radau) → explicit method is the bottleneck | Sequential ≫ Pure → coupling strategy is the bottleneck |
| P1-1 Stiffness | Newton iterations spike ≥3× during shock | Constant iterations → not stiff |
| P1-2 Severity Pareto | Radau Pareto-dominates Euler at all 3 severities | Euler wins at any severity |
| P1-3 Reference Quality | min_MAP differs by >0.5 mmHg between rtol=1e-4 and rtol=1e-10 | No meaningful difference |
| P2-1 Physio Validation | All 5 checks PASS | Any check FAILS → investigate root cause |

---

## Critical Implementation Notes

1. **Reference trajectory reuse**: The reference (rtol=1e-10) takes ~4700s. Compute ONCE in `convergence_study.py`, save to `reference_trajectory_data.json`, reuse across all P0/P1 experiments.

2. **Pure Euler implementation**: In `simulation.py`, add:
   ```python
   def pure_euler_step(self, dt: float) -> None:
       """Advance by one Euler step using the full unified RHS (no organ loop)."""
       y = self._pack_unified_state()
       f = self._unified_rhs(self.current_time_s, y)
       y_new = y + dt * np.asarray(f)
       self._unpack_unified_state(y_new)
       self.current_time_s += dt
   ```
   This is the key distinction from `step()` — one RHS call vs loop over organs.

3. **Newton iteration counting**: In `simulation.py` or wrap `solve_ivp` with a custom event collector. SciPy Radau's internal iteration count is not directly exposed — may need to subclass or patch `._unified_rhs` to countcalls to the Newton solver internally.

4. **Euler dt=0.001 stability warning**: From pilot data, dt=0.001 causes numerical collapse at t>60s (VdP phase divergence). Document this as an expected observation, not a bug.

5. **800 mL spot check only**: Full 800 mL Euler trajectory may be unstable even at dt=0.05. Use 3-point spot check (t=10, 30, 60) confirmed by Radau at matching time points.