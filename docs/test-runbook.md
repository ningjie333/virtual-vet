# Test Runbook

Detailed operator reference for the current test channels.

If you want the shortest answer to "what should I run right now?", use
[test-command-guide.md](test-command-guide.md) first.

This file is the deeper reference:

- bundle inventory
- measured timings
- hotspot tracking
- split-run recipes

Last reviewed: 2026-06-10

## One Rule First

Use this file as the timing and split-run ledger.

If you want:

- the shortest "what do I run?" answer, use [test-command-guide.md](test-command-guide.md)
- the lane-policy explanation, use [testing.md](testing.md)

## Canonical Channels

| Channel | Intent | Command | Current observed status |
|---|---|---|---|
| `fast` | smallest daily gate | `python -m pytest --channel fast -q` | `441 passed`; recently observed around `8-15s` |
| `core` | cumulative normal regression gate | `python -m pytest --channel core -q` | `750` selected tests; recently observed around `25-45s` |
| `core-only` | exact core split without re-running fast | `python -m pytest --channel core-only -q` | `309 passed in 31.18s` |
| `heavy` | cumulative validation lane | `python -m pytest --channel heavy -q` | `908` selected tests; full lane exceeded `300s` |
| `heavy-only` | exact heavy split without re-running fast/core | `python -m pytest --channel heavy-only -q` | `158 passed in 180.60s` |
| `benchmark` | moderate long-run validation | `python -m pytest --channel benchmark -q` | lighter than before; not a daily lane |
| `research` | ultra-heavy validation | `python -m pytest --channel research -q` | use sparingly |
| `all` | everything under `tests/` except explicit `collect_ignore` | `python -m pytest --channel all -q` | use sparingly |

## Thematic Bundles

`--bundle` is the thematic splitter.

Current bundle inventory:

| Bundle | Typical command | Current size / status |
|---|---|---|
| `fast-engine` | `python -m pytest --channel fast-only --bundle fast-engine -q` | `390` tests |
| `fast-runtime` | `python -m pytest --channel fast-only --bundle fast-runtime -q` | `47` tests |
| `core-engine` | `python -m pytest --channel core-only --bundle core-engine -q` | `92` tests in exact core mode |
| `core-runtime` | `python -m pytest --channel core-only --bundle core-runtime -q` | `216 passed in 36.30s` in exact core mode; `242` tests if all promoted items are included |
| `core-solver` | `python -m pytest --channel core-only --bundle core-solver -q` | `1 passed in 4.37s` |
| `heavy-engine` | `python -m pytest --channel heavy-only --bundle heavy-engine -q` | `43 passed in 40.41s` in exact heavy mode; `46` tests total |
| `heavy-runtime` | `python -m pytest --channel heavy-only --bundle heavy-runtime -q` | `78 passed in 88.13s` |
| `benchmark-performance` | `python -m pytest --channel benchmark --bundle benchmark-performance -q` | hard engineering performance checks |
| `benchmark-performance-observational` | `python -m pytest --channel benchmark --bundle benchmark-performance-observational -q` | currently `1 xfailed, 2 xpassed` |
| `benchmark-solver` | `python -m pytest --channel benchmark --bundle benchmark-solver -q` | Euler-only endurance checks |
| `benchmark-deterioration` | `python -m pytest --channel benchmark --bundle benchmark-deterioration -q` | `3 passed in 28.43s` |
| `research-disease` | `python -m pytest --channel research --bundle research-disease -q` | DKA-only hard validation |
| `research-disease-phosphorus` | `python -m pytest --channel research --bundle research-disease-phosphorus -q` | phosphorus-only long-horizon checks; one assertion is observation-only |
| `research-solver-drift` | `python -m pytest --channel research --bundle research-solver-drift -q` | dual-solver drift comparison |
| `research-solver-parity` | `python -m pytest --channel research --bundle research-solver-parity -q` | parity concept; still expensive |
| `research-solver-radau` | `python -m pytest --channel research --bundle research-solver-radau -q` | Radau-only endurance check; very expensive |

This is now the preferred way to split a full validation story without hand-maintaining file lists.

For the exact generated lane/bundle ownership table, see
[test-manifest-summary.md](test-manifest-summary.md).

## Heavy Is Still Too Large To Be One Default Command

`heavy` is now the right place for realistic progression and integration validation, and it no longer carries solver parity workloads that behave like benchmark research jobs. It is still too broad to be your routine second command.

Measured heavy subchannels on the current machine:

| File / subchannel | Command | Current result |
|---|---|---|
| boundary validation | `python -m pytest tests/test_boundary.py -q` | `27 passed in 40.54s` |
| cross-module coupling | `python -m pytest tests/test_cross_module_coupling.py -q` | `6 passed in 20.90s` |
| pharmacology integration | `python -m pytest tests/test_pharmacology.py -q` | `46 passed in 21.27s` |
| scenario integration | `python -m pytest tests/test_scenarios.py -q` | `33 passed in 45.27s` |
| toxicology / simulation checks | `python -m pytest tests/test_simulation.py -q` | `8 passed in 17.17s` |
| species-specific checks | `python -m pytest tests/test_species_specific.py -q` | `5 passed in 4.83s` |
Recommended heavy order:

1. `python -m pytest tests/test_simulation.py -q`
2. `python -m pytest tests/test_species_specific.py -q`
3. `python -m pytest tests/test_cross_module_coupling.py -q`
4. `python -m pytest tests/test_pharmacology.py -q`
5. `python -m pytest tests/test_boundary.py -q`
6. `python -m pytest tests/test_scenarios.py -q`
If you want to split a full run into non-overlapping channels, use:

1. `python -m pytest --channel fast-only -q`
2. `python -m pytest --channel core-only -q`
3. `python -m pytest --channel heavy-only -q`
4. `python -m pytest --channel benchmark -q`
5. `python -m pytest --channel research -q`

If you want the fully split thematic version instead, use:

1. `python -m pytest --channel fast-only --bundle fast-engine -q`
2. `python -m pytest --channel fast-only --bundle fast-runtime -q`
3. `python -m pytest --channel core-only --bundle core-engine -q`
4. `python -m pytest --channel core-only --bundle core-runtime -q`
5. `python -m pytest --channel core-only --bundle core-solver -q`
6. `python -m pytest --channel heavy-only --bundle heavy-engine -q`
7. `python -m pytest --channel heavy-only --bundle heavy-runtime -q`
8. `python -m pytest --channel benchmark --bundle benchmark-deterioration -q`
9. `python -m pytest --channel benchmark --bundle benchmark-performance -q`
10. `python -m pytest --channel benchmark --bundle benchmark-performance-observational -q`
11. `python -m pytest --channel benchmark --bundle benchmark-solver -q`
12. `python -m pytest --channel research --bundle research-disease -q`
13. `python -m pytest --channel research --bundle research-disease-phosphorus -q`
14. `python -m pytest --channel research --bundle research-solver-drift -q`
15. `python -m pytest --channel research --bundle research-solver-radau -q`
16. `python -m pytest --channel research --bundle research-solver-parity -q`

## Benchmark Lane

The benchmark lane is intentionally separated because it contains explicit endurance and performance work, not ordinary regression checks.

Current benchmark files:

- `tests/test_performance.py`
- `tests/test_performance_observational.py`
- `tests/test_solver_endurance.py`
- `tests/test_untreated_deterioration.py`

Current research files:

- `tests/test_disease_endurance.py`
- `tests/test_phosphorus_endurance.py`
- `tests/test_solver_drift.py`
- `tests/test_solver_numerics.py`
- `tests/test_solver_radau_endurance.py`

Current observations:

| File / subchannel | Command | Current result |
|---|---|---|
| untreated deterioration sweep | `python -m pytest tests/test_untreated_deterioration.py -q` | `3 passed in 20.53s` |
| clean file-owned benchmark bundle set | `python -m pytest --channel benchmark --bundle benchmark-performance --bundle benchmark-performance-observational --bundle benchmark-solver --bundle benchmark-deterioration -q` | `10 passed, 1 xfailed, 2 xpassed in 108.69s` |
| DKA endurance | `python -m pytest tests/test_disease_endurance.py -q` | exceeded `300s` timeout |
| phosphorus endurance | `python -m pytest tests/test_phosphorus_endurance.py -q` | long; one assertion currently `xfail` by design |
| Euler endurance | `python -m pytest tests/test_solver_endurance.py -q` | `2 passed in 81.52s` |
| solver drift | `python -m pytest tests/test_solver_drift.py -q` | exceeded `240s` timeout in isolated timing attempts |
| Radau endurance | `python -m pytest tests/test_solver_radau_endurance.py -q` | exceeded `300s` timeout |
| solver parity | `python -m pytest tests/test_solver_numerics.py -q` | each measured case exceeded `120s` timeout |

Current observation-only performance budgets:

- `test_step_execution_time_budget`
  - tracked as observation-only because local wall-clock noise is too sensitive
- `test_disease_path_absolute_budget`
  - tracked separately from the still-enforced disease overhead ratio guard

## Not Collected On Purpose

These files are intentionally outside ordinary pytest collection in `tests/conftest.py`:

- `collect_disease_progression.py`
- `debug_symptoms.py`
- `test_warmup_check.py`

They are diagnostic or research utilities, not ordinary regression gates.
