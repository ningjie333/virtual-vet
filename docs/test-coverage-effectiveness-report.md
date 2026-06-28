# Test Coverage & Effectiveness Report

Comprehensive audit of the virtual-vet test suite covering both **code coverage**
(pytest-cov runtime collection) and **semantic coverage / effectiveness** (constraint
ratings from `docs/test-constraint-audit.md` cross-validated with runtime data).

- Generated: 2026-06-27
- Data window: 2026-06-27 (fast/core/heavy lanes collected same day)
- Collector: `tools/dev/check_test_effectiveness.py` + pytest-cov 7.1.0 on Python 3.12.13
- Source coverage config: `pyproject.toml` `[tool.coverage.run]` (`source = ["src","game"]`, `branch = true`, `fail_under = 0`)

---

## 1. Executive Summary

The suite is a solid **engineering safety net** but is **not yet a clinical-credibility
gate**. Coverage scales with lane depth (fast → core → heavy) and every collected lane
is green (0 failures), but several passed tests carry weak or misleading assertions
that can hide real model drift.

### Headline numbers

| Lane | Tests | Pass | Skip | Duration | Line % | Branch % | Missing stmts |
|---|---:|---:|---:|---:|---:|---:|---:|
| fast  |  591 |  576 | 15 | 167.29s | 67.11 | 51.07 | 2503 / 7610 |
| core  |  913 |  892 | 21 | 184.98s | 78.25 | 61.88 | 1655 / 7610 |
| heavy | 1071 | 1050 | 21 | 341.42s | 81.29 | 66.97 | 1424 / 7610 |
| benchmark | — | — | — | — | — | — | not collected (cost) |
| research  | — | — | — | — | — | — | not collected (cost) |

- Going fast → heavy adds 480 tests and lifts line coverage by **+14.18 pp** and branch
  coverage by **+15.90 pp**, while still leaving 1424 statements and 681 branches uncovered.
- Branch coverage lags line coverage by **~14 pp** at every lane, indicating systematic
  under-exercise of conditional branches.
- The single dominant hotspot `tests/test_comorbidity_cases.py` consumes
  **109.86s (32% of heavy wall time)** across only 9 tests.

### One-line verdict
Green suite, real engineering value, but a non-trivial layer of weak/misleading
assertions means "all tests pass" must not be read as "the kernel is right".

**Important caveat on raw coverage percentages**: several modules with 0% line coverage
are display/CLI/utility code (`heart_v2.py` = ASCII animation, `cli.py`/`cli_common.py`
= argparse shims, `logger_config.py` = logging setup) — these are **not** core engine
and their low coverage is harmless. What matters are the **core engine modules with
significant gaps**: `engine/solvers/radau.py` (21.82%, the production solver), `simulation.py`
(73.07%, 136 uncovered lines), `diseases/config_driven.py` (72.11%), and `lifecycle_curves.py`
(68.00%). See §4.2 for the split.

---

## 2. Methodology

Two independent assessment tracks were combined.

### 2.1 Code coverage (runtime)

- Tooling: `pytest-cov>=4.1.0` (resolved to 7.1.0) via `uv run`.
- Config: `pyproject.toml` `[tool.coverage.run]` with `branch = true`,
  `source = ["src","game"]`, `fail_under = 0` (baseline collection, not a hard gate).
- Omitted: tests/, tools/, frontend/, experiments/, `src/db/*`, `src/textual_monitor.py`,
  `src/ascii_dashboard.py`, and entry-point shims (`main.py`, `gui_app.py`,
  `cli_daemon.py`, `cli_shim.py`, `vet_monitor.py`).
- Invocation is **opt-in** through `tools/dev/check_test_effectiveness.py --cov`; the
  default `pytest` loop is unchanged and does not pay the coverage overhead.
- Output: `--cov-report=xml:` (Cobertura `coverage.xml`, gitignored) + junit-xml parsed
  into JSON reports under `results/test_effectiveness/` (gitignored).

### 2.2 Semantic coverage / effectiveness (static + cross-validation)

- Authority: `docs/test-constraint-audit.md` (last reviewed 2026-06-10), which defines
  the five-level rubric `Strong / Useful / Weak / Misleading / Missing Alarm`.
- Cross-validation: runtime per-file coverage, hotspot ledger, and literature comparison
  in `tools/dev/validation_report.md` (19 PASS / 6 WARN / 0 FAIL).

### 2.3 Data sources

| Source | Role |
|---|---|
| `results/test_effectiveness/20260627-162836_fast.json` | fast runtime |
| `results/test_effectiveness/20260627-163156_core.json` | core runtime |
| `results/test_effectiveness/20260627-164640_heavy.json` | heavy runtime |
| `docs/test-constraint-audit.md` | effectiveness rubric + ratings |
| `tools/dev/validation_report.md` | literature comparison |
| `tests/test_manifest.json` | lane/bundle ownership map |
| `pyproject.toml` | coverage config + pytest markers |

---

## 3. Collection Status

| Lane | Status | Tests | Duration | Notes |
|---|---|---:|---:|---|
| fast | ✅ collected | 591 | 167s | 576 pass / 15 skip / 0 fail |
| core | ✅ collected | 913 | 185s | 892 pass / 21 skip / 0 fail |
| heavy | ✅ collected | 1071 | 341s | 1050 pass / 21 skip / 0 fail |
| benchmark | ⏸ not collected | — | — | cost too high; effectiveness drawn from `docs/test-constraint-audit.md` (mostly `Useful` as engineering guardrail, `Weak` as scientific evidence) and `test_performance.py` is an engineering budget, not a truth criterion |
| research | ⏸ not collected | — | — | cost too high; `test_solver_numerics.py::TestEulerRadauParity` is `Strong conceptually` but operationally under-exercised |

The heavy collection completed within the 900s timeout budget; no degradation was
required. Heavy is a strict superset of fast + core plus 6 heavy-only files
(`test_scenarios.py`, `test_cross_module_coupling.py`, `test_pharmacology.py`,
`test_boundary.py`, `test_simulation.py`, `test_species_specific.py`).

---

## 4. Code Coverage Results

### 4.1 Lane-over-lane comparison

| Lane | Line % | Δ vs prev | Branch % | Δ vs prev | Missing stmts | Missing branches |
|---|---:|---:|---:|---:|---:|---:|
| fast  | 67.11 | — | 51.07 | — | 2503 | 1009 |
| core  | 78.25 | +11.14 | 61.88 | +10.81 | 1655 | 786 |
| heavy | 81.29 | +3.04 | 66.97 | +5.09 | 1424 | 681 |

- The fast → core jump (+11.14 pp line) is the highest-yield coverage delta per added
  test, indicating core tests target genuinely uncovered code.
- The core → heavy jump is smaller on line (+3.04 pp) but larger on branch (+5.09 pp),
  meaning heavy tests exercise more conditional paths rather than just more lines.
- Branch coverage lags line coverage by **16.04 pp (fast) / 16.37 pp (core) / 14.32 pp
  (heavy)** — a consistent signal that error/edge branches are under-tested everywhere.

### 4.2 Per-module coverage gaps — core engine vs. display/utility

Not all 0% coverage is equal. Modules fall into two categories:

**A. Core engine modules with significant gaps (need tests)**

These are the actual coverage concerns — subsystems that are part of the physiological
kernel, solver, or simulation pipeline and should be exercised more thoroughly.

| Module | Line % | Branch % | Missing | Role | What's missing |
|---|---:|---:|---:|---:|---|
| `engine/solvers/radau.py` | 21.82 | 8.70 | 86 | production Radau solver | only fallback path exercised; no parity test actually runs Radau on a tractable window |
| `lifecycle_curves.py` | 68.00 | 50.00 | 16 | species/age curve fitting | curve extrapolation branches untested |
| `diseases/config_driven.py` | 72.11 | 61.70 | 70 | disease config dispatch | ~30% of disease config branches unexercised |
| `simulation.py` | 73.07 | 61.67 | 136 | **main simulation driver** | 136 uncovered lines — the largest core-engine gap |
| `config_validation.py` | 73.97 | 66.43 | 82 | JSON schema validation | edge-case schema rejection paths |
| `clinical_signs_engine.py` | 77.07 | 63.16 | 88 | clinical signs production | sign-specific thresholds and edge cases |
| `fluid.py` | 85.17 | 43.33 | 31 | fluid compartment model | 43% branch gap — compartmental flow transitions |
| `report_engine.py` | 82.25 | 70.94 | — | clinical report generation | improved from 60.96% (core) via heavy, still moderate gaps |
| `toxicology.py` | 89.29 | 50.00 | — | drug toxicity modeling | line coverage good (89%), branch coverage poor (50%) — half the conditional paths untested |

**B. Non-core modules where low coverage is acceptable**

These are display/CLI/utility layers that are not part of the physiological kernel.
Their low coverage does not affect the clinical credibility of the engine.

| Module | Line % | Branch % | Missing | Role | Why acceptable |
|---|---:|---:|---:|---:|---|
| `heart_v2.py` | 0.00 | 0.00 | 301 | ASCII heart animation (curses renderer) | pure display; no physiological logic; run manually via `vet-monitor heart` |
| `cli.py` | 0.00 | 0.00 | 78 | `vet-monitor` argparse entry point | thin dispatch shim; no business logic |
| `cli_common.py` | 0.00 | 0.00 | 84 | CLI helpers (aliases, factory, ANSI) | shared utility code; no kernel logic |
| `parameter_refs.py` | 0.00 | 0.00 | 38 | literature reference lookup utility | used by `gate_check --verify-refs`; low-risk, could benefit from a minimal import+enumeration test |
| `logger_config.py` | 60.00 | 50.00 | 4 | logging setup (20 lines) | trivial config; the 4 uncovered lines are the `INFO`-level branch |
| `test_translator.py` | 0.00 | 100.00 | 7 | test translation stub | stub; the single branch is fully covered; not a real gap |

**Recommendation**: `heart_v2.py`, `cli.py`, and `cli_common.py` should be explicitly
added to `[tool.coverage.run].omit` in `pyproject.toml` so they don't drag down the
aggregate coverage numbers. `parameter_refs.py` could benefit from a trivial import
test (it's only 38 lines and is used by gate_check).

### 4.3 Notable coverage lifts from core → heavy

The heavy-only tests materially raise coverage on modules the core lane leaves cold:

| Module | core line % | heavy line % | Δ | Driver |
|---|---:|---:|---:|---|
| `toxicology.py` | 46.43 | 89.29 | +42.86 | `test_pharmacology.py` |
| `report_engine.py` | 60.96 | 82.25 | +21.29 | `test_scenarios.py` |
| `case_generator.py` | 0.00 | 59.26 | +59.26 | `test_scenarios.py` |
| `action_system.py` | 89.06 | 97.40 | +8.34 | heavy integration tests |
| `clinical_signs_engine.py` | 76.53 | 77.07 | +0.54 | marginal |

### 4.4 Fully covered modules (heavy lane, line_pct = 100%)

`__init__.py`, `blood.py`, `clinical_snapshot.py`, `clinical_stage.py`,
`noble_purkinje.py`, `presentation_state.py`, `runtime.py`,
`runtime_composition.py`, `treatment.py`, `engine/__init__.py`,
`organs/__init__.py`.

### 4.5 Special case: `test_translator.py`

`line_pct = 0.00` but `branch_pct = 100.00`. This is the test-translation stub whose
importable lines are not executed (so 0% line) but whose single conditional branch is
fully hit. Should be read as "stub, not a coverage concern" rather than a gap.

---

## 5. Effectiveness Ratings

Transcribed from `docs/test-constraint-audit.md` (2026-06-10). The rubric:

| Level | Meaning |
|---|---|
| `Strong` | checks exact formulas / invariants / mappings / tight numeric relationships; failure strongly implies a real bug; hard to satisfy accidentally |
| `Useful` | checks direction / monotonicity / boundedness / meaningful integration outcomes; catches real regressions; leaves room for model drift |
| `Weak` | shape / existence / loose range / "did not crash" checks; easy to pass while behavior is wrong |
| `Misleading` | name or comments imply validation strength the assertion does not support; creates false confidence |
| `Missing Alarm` | important failure mode not meaningfully guarded, or current tests too weak to detect it |

### 5.1 Ratings by area

| Area | Files (representative) | Rating |
|---|---|---|
| Kernel formulas & invariants | `test_blood.py`, `test_lung.py`, `test_kidney.py`, `test_coupling_lag_state.py` | `Strong` |
| Protocol / mapping / mutation | `test_factor_command.py`, `test_pharmacology_factor_commands.py`, `test_blood_volume_conservation.py`, `test_session_persistence.py`, `test_config_validation.py` | `Strong` |
| Short-horizon solver parity | `test_solver_numerics.py::TestEulerRadauParity` | `Strong conceptually`, operationally under-exercised |
| Organ subsystem directionality | `test_heart.py`, `test_neuro.py`, `test_immune.py`, `test_endocrine.py`, `test_organ_health.py`, `test_cross_module_coupling.py` | `Useful` |
| Disease progression | `test_diseases.py`, `test_disease_endurance.py`, `test_phosphorus_endurance.py` | `Useful` (some `Weak`/`Misleading` mixed in) |
| Coupling integration | `test_coupling.py`, `test_cross_module_coupling.py` | `Useful` (upgraded from weaker state) |
| Interface / API contracts | `test_interface.py`, parts of `test_pharmacology.py` | `Useful` for contracts, `Weak` as physiology evidence |
| Game-layer workflow | `test_game.py`, `test_scenarios.py`, `test_time_management.py`, `test_action_runtime_seam.py` | `Useful` for orchestration, `Weak` for kernel truth |
| Boundary / no-crash | `test_boundary.py`, parts of `test_simulation.py` | `Useful` as safety rail, `Weak` as correctness evidence |
| Performance | `test_performance.py` | `Useful` as guardrail, `Weak` as evidence |
| Untreated deterioration | `test_untreated_deterioration.py` | improved from `Misleading` to `Useful` (60s deterioration vs healthy control, disease-specific magnitude windows) |
| Lifecycle literature | `test_lifecycle_literature.py` | `Strong` as documentation integrity, `Weak`/`Misleading` if read as engine-vs-literature validation |

### 5.2 P0 misleading tests (must be upgraded before being trusted as evidence)

These passed tests can hide real regressions because their assertions are weaker than
their names imply. **Listed only — not modified in this audit.**

| Test | Current assertion | Problem | Rating |
|---|---|---|---|
| `test_species_specific.py::test_pneumonia_raises_hr_in_all_species` | `assert vc.heart.heart_rate > 0` | an inert disease model would still pass as long as HR stays positive | `Misleading` |
| `test_diseases.py` pneumonia / ARF HR offset tests | `assert hr_offset > 0.0` | comments describe a specific formula but assertion only checks sign | `Misleading` |
| `test_coupling.py` residual command-existence checks | `current_time_s > 0`, signal exists, `len(commands) >= 1` | proves the pipeline runs, not that coupling magnitude / sign / downstream effect is right | `Weak` to `Misleading` |
| `test_gate_contract.py` | asserts existence of tests / asserts / markers | useful anti-rot guard, no model-truth value | `Weak` |

### 5.3 Missing alarms (P1 / P2 gaps)

From `docs/test-constraint-audit.md` §"Highest-Priority Missing Alarms":

1. **Quantitative disease trajectory checkpoints** — disease-specific expected windows
   at multiple physical times (pneumonia @ 5 min / 30 min / 2 h; ARF @ 10 min / 60 min
   / 6 h; phosphorus early / mid / late). Currently only "worse than before".
2. **Intervention response truth tables** — after intervention X, variable Y should
   improve/worsen by Z within T (fluid bolus → MAP/CVP/urine; epinephrine →
   HR/SVR/MAP onset & decay; O2/ventilation → blood gases).
3. **Cross-module quantitative conservation** — beyond blood volume sync: acid-base
   bookkeeping, electrolyte/mass balance, fluid redistribution accounting.
4. **Quantitative coupling effect tests** — not just "RAAS emits commands" but "defined
   renin input produces bounded expected SVR / volume response".
5. **Clinical endpoint validation** — endpoint timing windows, endpoint criterion
   windows, reversible vs irreversible transition checks.

---

## 6. Hotspots & Duration

### 6.1 Top hotspots (heavy lane, by total wall time)

| # | File | Tests | Total s | Max s | Lane/Bundle | Slowest test |
|---|---|---:|---:|---:|---|---|
| 1 | `test_comorbidity_cases.py` | 9 | 109.86 | 29.97 | fast/fast-engine | `test_ckd_pneumonia_case_attaches_both_diseases` |
| 2 | `test_scenarios.py` | 32 | 31.30 | 12.14 | heavy/heavy-runtime | `test_generate_case_different_seeds_different` |
| 3 | `test_immune.py` | 16 | 24.93 | 17.83 | core/core-engine | `test_severe_infection_raises_cytokine` |
| 4 | `test_cross_module_coupling.py` | 6 | 23.62 | 6.31 | heavy/heavy-engine | `test_arf_hyperkalemia` |
| 5 | `test_pharmacology.py` | 46 | 17.60 | 4.93 | heavy/heavy-runtime | `test_e2e_arf_full_flow` |
| 6 | `test_time_management.py` | 20 | 16.90 | 11.65 | core/core-runtime | `test_death_timer_decreases_in_moribund` |
| 7 | `test_game.py` | 155 | 13.07 | 4.75 | core/core-runtime | `test_arf_has_bun_entry` |
| 8 | `test_twin_run.py` | 18 | 12.63 | 3.52 | core/core-solver | `test_twin_run_scenario[arf_severe]` |
| 9 | `test_diseases.py` | 35 | 11.26 | 4.91 | core/core-engine | `test_pneumonia_oxygenation_checkpoint_after_60s` |
| 10 | `test_mechanism_b_rr.py` | 1 | 11.04 | 11.04 | core/core-engine | `test_rr_after_mechanism_b` |

### 6.2 Observations

- `test_comorbidity_cases.py` alone accounts for **32% of the heavy lane wall time**
  across only 9 tests (mean 12.21s, p95 25.81s, max 29.97s). This is the single highest-
  leverage target for either optimization or splitting.
- `test_immune.py::test_severe_infection_raises_cytokine` (17.83s) and
  `test_time_management.py::test_death_timer_decreases_in_moribund` (11.65s) are
  individual long tests worth profiling.
- `test_mechanism_b_rr.py` is a single test taking 11.04s — a candidate for either
  shortening or being moved to a heavier lane if it is not a daily gate.

### 6.3 Heavy-only file contribution

| File | Tests | Total s | Bundle |
|---|---:|---:|---|
| `test_scenarios.py` | 32 | 31.30 | heavy-runtime |
| `test_cross_module_coupling.py` | 6 | 23.62 | heavy-engine |
| `test_pharmacology.py` | 46 | 17.60 | heavy-runtime |
| `test_boundary.py` | 26 | 5.55 | heavy-engine |
| `test_simulation.py` | 6 | 2.77 | heavy-engine |
| `test_species_specific.py` | 5 | 2.72 | heavy-engine |

These 6 files add 158 tests and ~83s of wall time, and are responsible for the
coverage lifts on `toxicology.py`, `report_engine.py`, and `case_generator.py` noted
in §4.3.

---

## 7. Semantic Coverage

### 7.1 Lane / bundle manifest coverage

Source: `tests/test_manifest.json`.

- **60 test files** registered.
- **5 lanes**: `fast` (33 files), `core` (12), `heavy` (6), `research` (5), `benchmark` (4).
- **16 bundles** (e.g. `fast-engine`, `fast-runtime`, `core-engine`, `core-runtime`,
  `core-solver`, `heavy-engine`, `heavy-runtime`, `benchmark-performance`,
  `benchmark-performance-observational`, `benchmark-solver`, `benchmark-deterioration`,
  `research-disease`, `research-disease-phosphorus`, `research-solver-drift`,
  `research-solver-parity`, `research-solver-radau`).
- A parallel `tier0`–`tier3` marker set exists in `pyproject.toml` for cost-based
  tiering; it is orthogonal to the lane model (lane = importance, tier = cost).

### 7.2 Literature comparison coverage

Source: `tools/dev/validation_report.md`.

- **25 variable comparisons** across 4 scenarios (healthy / arf / hemorrhage / pneumonia).
- **19 PASS, 6 WARN, 0 FAIL.**
- WARN items requiring calibration:
  - healthy `Albumin` 3.0 g/dL vs 3.2–4.1 (Cornell Vet Lab)
  - arf `BUN` 20.3 vs 25–60, `Creatinine` 1.4 vs 1.5–4.0, `K+` 4.2 vs 4.5–6.0 (Nelson & Couto 5e Ch53)
  - pneumonia `HR` 180.8 vs 100–160, `PaO2` 91.5 vs 50–80 (Nelson & Couto 5e Ch11)
- The `## Issues Requiring Calibration` section at the end of the file is **empty** —
  the WARNs above have not yet been triaged into actionable calibration tickets.

### 7.3 Reference sources cited

Nelson & Couto 5e, Guyton 14e, Cornell Vet Lab, Iowa State Vet Path, IDEXX Catalyst.

---

## 8. Documentation Debt

`docs/README.md` Testing section promises 9 test documents. Only 2 actually exist on
disk; 7 are promised-but-missing links.

| Promised doc | Exists? | Referenced elsewhere? |
|---|---|---|
| `harness-engineering.md` | ❌ no | — |
| `test-command-guide.md` | ❌ no | **`AGENTS.md` and `pyproject.toml:22` both link to it as a first-pass reading order entry** |
| `testing.md` | ❌ no | `pyproject.toml:43` references `tests/debug_symptoms.py` "per docs/testing.md" |
| `test-runbook.md` | ❌ no | `pyproject.toml:22-28` comment block references it for the 60s timeout rationale |
| `test-manifest-summary.md` | ✅ yes | generated from `tests/test_manifest.json` |
| `heavy-test-triage.md` | ❌ no | — |
| `test-constraint-audit.md` | ✅ yes | source of this report's effectiveness ratings |
| `literature-backed-testing-plan.md` | ❌ no | — |
| `test-evidence-registry.md` | ❌ no | — |

The `docs/archive/` subdirectory linked from `docs/README.md` also does not exist on
disk. Additionally, 4 un-indexed docs exist (`CODE_WIKI.md`, `coupling_inventory.md`,
`disease-symptom-timelines.md`, `physiology_audit.md`).

**Impact**: the two cross-referenced missing docs (`test-command-guide.md`,
`test-runbook.md`) are actively misleading — `AGENTS.md` sends new contributors to a
file that does not exist, and `pyproject.toml`'s timeout rationale cites a doc that
cannot be opened.

---

## 9. Recommendations

Listed by priority. **These are recommendations only — none are implemented in this
audit.** Scope and ordering follow `docs/test-constraint-audit.md` §"Concrete Priority
List".

### P0 — rewrite or demote misleading tests
- `test_untreated_deterioration.py` — already improved from `Misleading` to `Useful`;
  decide whether it stays a short-horizon deterioration file or becomes a real
  endpoint-window validation file.
- Sign-only disease assertions in `test_diseases.py` (`hr_offset > 0.0`) → replace
  with magnitude-window assertions matching the documented formula.
- `test_species_specific.py::test_pneumonia_raises_hr_in_all_species`
  (`heart_rate > 0`) → assert disease-specific HR elevation window.
- Residual command-exists-only assertions in `test_coupling.py` → upgrade to exact
  command-value + post-application effect checks (the recent
  `renin_activity=2.0 → SVR ×1.4` and `MAP=70 → GFR ×30/41` upgrades show the pattern).

### P1 — create quantitative disease trajectory checkpoints
Sampled natural-history gold suite with sparse checkpoints and tolerance bands
(pneumonia @ 5 min / 30 min / 2 h; ARF @ 10 min / 60 min / 6 h; phosphorus
early / mid / late). This is the single biggest missing piece for kernel credibility.

### P1 — split lifecycle evidence
Split `test_lifecycle_literature.py` into:
- reference-data integrity tests (string / constant / PMID presence)
- engine-against-reference behavior tests

These are different kinds of evidence and currently sit in one file.

### P1 — add intervention-response validation
After intervention X, variable Y should change by Z within T. Fluid bolus →
MAP/CVP/urine; epinephrine → HR/SVR/MAP onset & decay; O2/ventilation → blood gases.

### P2 — formalize benchmark policy
For `test_performance.py`: define environment, define statistics, decide hard gate vs
informational benchmark.

### P2 — close core-engine coverage gaps
- **`engine/solvers/radau.py`** (21.82% / 8.70%) — the production Radau path is barely
  exercised; only the fallback is tested. Add a parity test that actually runs Radau
  on a tractable window (e.g. 30s simulation comparing Radau vs Euler state divergence).
- **`simulation.py`** (73.07%, 136 uncovered lines) — the main simulation driver has the
  largest core-engine gap. Profile the uncovered lines to identify which code paths
  (boundary handling, error recovery, edge-case disease states) are missing test coverage.
- **`fluid.py`** (85.17% line, 43.33% branch) — the worst branch gap in core engine.
  The compartmental flow transitions (volume shifts between intravascular / interstitial /
  intracellular) need dedicated branch-coverage tests.
- **`toxicology.py`** (89.29% line, 50.00% branch) — half the conditional paths
  (drug metabolism, toxicity thresholds, clearance curves) are not exercised.
- **`diseases/config_driven.py`** (72.11%) and **`lifecycle_curves.py`** (68.00%) —
  medium gaps; the disease config dispatch and species/age curve fitting need more
  exhaustive parameter-space coverage.

### P2 — explicitly omit non-core modules from coverage
- Add `src/heart_v2.py`, `src/cli.py`, `src/cli_common.py`, `src/logger_config.py` to
  `[tool.coverage.run].omit` in `pyproject.toml`. These are display/CLI/utility code
  with no core-engine logic; keeping them in the coverage source set drags down the
  aggregate numbers without providing any clinical-credibility signal.
- `src/parameter_refs.py` — borderline case. It's a utility referenced by `gate_check
  --verify-refs`. A minimal import + `all_param_refs()` enumeration test (38 lines, <1s)
  would be cheap and give it 100% coverage. Consider omitting it only if that test is
  not worth writing.

### P2 — close documentation debt
- Either create or remove the 7 promised-but-missing test docs.
- At minimum, fix the two actively-misleading cross-references:
  `AGENTS.md` → `test-command-guide.md` and `pyproject.toml:22` → `test-runbook.md`.
- Populate the empty `## Issues Requiring Calibration` section in
  `tools/dev/validation_report.md` with the 6 WARN items.

---

## 10. Verification

### 10.1 Data integrity

- All coverage percentages in this report are read directly from the three JSON
  reports under `results/test_effectiveness/`; no value is computed or estimated.
- `fast.json` reports `line_pct = 67.11`, `branch_pct = 51.07` ✅
- `core.json` reports `line_pct = 78.25`, `branch_pct = 61.88` ✅
- `heavy.json` reports `line_pct = 81.29`, `branch_pct = 66.97` ✅
- Effectiveness ratings and the P0/Missing-Alarm lists are transcribed verbatim from
  `docs/test-constraint-audit.md` (2026-06-10); the rubric text is unchanged.
- Literature comparison numbers are transcribed from `tools/dev/validation_report.md`.

### 10.2 Configuration sanity

- `pyproject.toml` `[tool.coverage.run]` present with `branch = true`,
  `source = ["src","game"]`, `fail_under = 0` ✅
- `pytest-cov>=4.1.0` in `[tool.uv].dev-dependencies` (resolved to 7.1.0) ✅
- `.gitignore` ignores `.coverage`, `coverage.xml`, `htmlcov/`,
  `results/test_effectiveness/` ✅ (so collected artifacts will not be committed)

### 10.3 Out-of-scope (explicitly not done in this audit)

- No P0 misleading test was modified.
- No 0%-coverage module was given new tests.
- `fail_under` was not changed (still 0; baseline collection, not a hard gate).
- `check_test_effectiveness.py` was not wired into `gate_check.py` (coverage gating
  is a separate future decision).
- benchmark / research lanes were not collected at runtime (cost; their effectiveness
  is drawn from the static audit).
- The 7 missing test docs were not created.

---

## Appendix A — Collected artifact locations

```
results/test_effectiveness/
├── 20260627-162836_fast.json        # fast runtime report
├── 20260627-162836_fast_stdout.txt  # fast pytest stdout
├── 20260627-163156_core.json        # core runtime report
├── 20260627-163156_core_stdout.txt  # core pytest stdout
├── 20260627-164640_heavy.json       # heavy runtime report
├── 20260627-164640_heavy_stdout.txt# heavy pytest stdout
└── coverage.xml                      # last-run Cobertura XML (overwritten each run)
```

All entries above are gitignored; they are reproducible by re-running
`tools/dev/check_test_effectiveness.py --lane {fast,core,heavy} --cov`.

## Appendix B — Reproduction commands

```bash
# fast lane
uv run python tools/dev/check_test_effectiveness.py --lane fast  --cov --timeout 600

# core lane
uv run python tools/dev/check_test_effectiveness.py --lane core  --cov --timeout 900

# heavy lane
uv run python tools/dev/check_test_effectiveness.py --lane heavy --cov --timeout 900

# compare against previous report in results/test_effectiveness/
uv run python tools/dev/check_test_effectiveness.py --lane core --cov --compare
```
