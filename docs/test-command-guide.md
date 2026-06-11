# Test Command Guide

One-page operator guide for the current test lanes.

Last reviewed: 2026-06-10

## Default Rule

Prefer `--channel` commands.

Do not use legacy marker commands like:

```bash
python -m pytest -m fast -q
```

They still collect the full suite first, so you will see large `deselected`
counts and can accidentally touch unrelated slow tests.

## Daily Commands

### Fast

Use for:

- formula changes
- config validation
- factor-command wiring
- small runtime seam refactors

Command:

```bash
python -m pytest --channel fast -q
```

Current observed result:

- `442 passed in 8.65s`

### Core

Use for:

- normal engine work
- app/runtime/session/API changes
- disease logic changes before deeper validation

Command:

```bash
python -m pytest --channel core -q
```

If you want the non-overlapping slice only:

```bash
python -m pytest --channel core-only -q
```

## Heavier Validation

### Heavy

Use for:

- realistic integration checks
- scenario flow
- pharmacology/game interaction
- cross-module physiology checks

Preferred approach:

```bash
python -m pytest --channel heavy-only -q
```

But in day-to-day work, targeted files are usually better:

```bash
python -m pytest tests/test_simulation.py -q
python -m pytest tests/test_species_specific.py -q
python -m pytest tests/test_cross_module_coupling.py -q
python -m pytest tests/test_pharmacology.py -q
python -m pytest tests/test_boundary.py -q
python -m pytest tests/test_scenarios.py -q
```

## Long-Run Validation

### Benchmark

`benchmark` is now the lighter long-run lane.

It is for:

- engineering performance checks
- Euler endurance
- untreated short-horizon deterioration checks

Important:

- bare `--channel benchmark` still includes tests promoted by `@pytest.mark.slower`
- if you want the clean file-owned benchmark set, run explicit bundles

Recommended benchmark command:

```bash
python -m pytest --channel benchmark --bundle benchmark-performance --bundle benchmark-performance-observational --bundle benchmark-solver --bundle benchmark-deterioration -q
```

Current observed result:

- `10 passed, 1 xfailed, 2 xpassed in 108.69s`

### Research

`research` is the ultra-heavy lane.

It is for:

- DKA long-horizon regression
- phosphorus long-horizon observation
- Euler/Radau drift comparison
- solver parity research runs
- Radau endurance

Use only when you intentionally want deep validation:

```bash
python -m pytest --channel research -q
```

Or target individual bundles:

```bash
python -m pytest --channel research --bundle research-disease -q
python -m pytest --channel research --bundle research-disease-phosphorus -q
python -m pytest --channel research --bundle research-solver-drift -q
python -m pytest --channel research --bundle research-solver-radau -q
python -m pytest --channel research --bundle research-solver-parity -q
```

Known current cost:

- `tests/test_disease_endurance.py -q` exceeded `300s`
- `tests/test_solver_drift.py -q` exceeded `240s`
- `tests/test_solver_radau_endurance.py -q` exceeded `300s`

## Which One To Run

If you changed:

- small formulas or config: run `fast`
- normal engine/app code: run `fast`, then `core`
- scenario/integration behavior: run `core`, then targeted `heavy`
- lighter long-run validation targets: run benchmark bundles
- solver research or very long disease trajectories: run `research`

## Current Best Practical Stack

For ordinary development:

```bash
python -m pytest --channel fast -q
python -m pytest --channel core -q
```

For a stronger but still practical pass:

```bash
python -m pytest tests/test_simulation.py -q
python -m pytest tests/test_cross_module_coupling.py -q
python -m pytest --channel benchmark --bundle benchmark-performance --bundle benchmark-performance-observational --bundle benchmark-solver --bundle benchmark-deterioration -q
```

## If You See `deselected`

Usually that means you used an old marker-based command.

Preferred replacements:

```bash
python -m pytest --channel fast -q
python -m pytest --channel core -q
```
