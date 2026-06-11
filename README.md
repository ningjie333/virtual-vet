# Virtual Vet

Veterinary multi-organ physiology kernel with an outer clinical/game application layer.

## Positioning

`Virtual Vet` is organized around a physiology engine first, not a game first.

- The **kernel** models coupled cardiovascular, respiratory, renal, fluid, metabolic, neuro-immune, and disease dynamics in physical time.
- The **clinical interpretation layer** turns engine state into observable signs, structured reports, and teaching-facing summaries.
- The **application layer** provides case orchestration, diagnosis gameplay, time budgeting, sessions, and UI.

The project is best described as a **literature-informed, clinically grounded physiology engine with a teaching application built around it**. Validation is ongoing; the documentation avoids treating gameplay abstractions as kernel truths.

## Document Map

- Start with [docs/architecture.md](docs/architecture.md) for the current authoritative rules.
- Read [docs/kernel-first-design.md](docs/kernel-first-design.md) for the integrated design narrative.
- Use [docs/testing.md](docs/testing.md) for the executable test split and regression workflow.
- Use [docs/README.md](docs/README.md) for the full docs index.

The rest of this `README` stays intentionally concise. It is an entry document, not the full architecture note.

## Time Semantics

The project uses three distinct notions of time.

- **Physical time** is kernel-native truth.
- **Scenario time** is outer-layer pacing and action cost.
- **Presentation time** is display-only clock/UI labeling.

Current rule:

- gameplay pacing must not redefine kernel biology

Current direction:

- keep disease and organ rates in physical units
- let the outer app choose how much physical time to advance
- move pre-encounter disease history into explicit encounter-state construction seams instead of hidden global multipliers

The first concrete builder seam now lives in `src/presentation_state.py` via `PresentationRequest` and `build_presented_engine(...)`.

For the full rationale, read:

- [docs/kernel-first-design.md](docs/kernel-first-design.md)
- [docs/kernel-time-architecture-sketch.md](docs/kernel-time-architecture-sketch.md)

## Current Solver Status

As of 2026-06-09:

- the repository contains both **Euler** and **Radau** paths
- the public gameplay application currently instantiates `VirtualCreature` with the default solver path, which is **Euler**
- Radau APIs and solver numerics tests remain important for validation and research-facing work

This means the gameplay shell should not be documented as if it were already running the full research solver path by default.

## Testing Model

The suite intentionally contains both cheap regression channels and explicit validation channels.

- Fast channels protect development speed.
- Heavy and benchmark channels protect physiological credibility and numerics work.
- App/API tests should usually validate orchestration through fake runtime seams or coarser test-only step sizes.
- Real long-horizon progression should stay explicit and marked.

Recommended workflow:

- everyday edits -> `python -m pytest --channel fast -q`
- app/runtime/API work -> `python -m pytest --channel core -q`
- kernel/time/disease changes -> `python -m pytest --channel core -q`, then targeted heavy files
- split full non-overlapping test execution -> `fast-only`, `core-only`, `heavy-only`, then `benchmark`
- high-impact changes -> targeted heavy and benchmark files before any full sweep

As of 2026-06-10, the daily `fast` channel currently runs `441` tests and has recently completed in roughly `8-15` seconds on the development machine.

The normal cumulative `core` channel currently runs `750` selected tests and has recently completed in roughly `25-45` seconds.

The heavier validation files are intentionally no longer treated as one monolithic default command. Use the targeted heavy and benchmark subchannels in [docs/testing.md](docs/testing.md) and [docs/test-runbook.md](docs/test-runbook.md) for solver, disease-endurance, survival, toxicology, and performance validation.

If you still see large `deselected` counts, you are probably using an older marker-based command such as `-m fast`; one recent run produced `441 passed, 495 deselected`, while the `--channel` commands stay clean.

If you want a finer-grained full sweep, the suite also supports thematic `--bundle` slicing inside each channel, for example `core-runtime`, `core-solver`, `benchmark-solver-parity`, and `benchmark-performance`.

See [docs/testing.md](docs/testing.md) for the current fake-runtime, marker, and channel conventions.

## Running

```bash
python gui_app.py
```

Then open `http://127.0.0.1:5000`.

## Key Documents

- [docs/architecture.md](docs/architecture.md): current authoritative architecture rules
- [docs/kernel-first-design.md](docs/kernel-first-design.md): main design narrative
- [docs/testing.md](docs/testing.md): test split and command guide
- [docs/clinical-interpretation-layer.md](docs/clinical-interpretation-layer.md): interpretation seam sketch
- [CLAUDE.md](CLAUDE.md): contributor-oriented repository guidance

## Historical Note

Some older project documents describe earlier game-time/AP models or older `/api/wait` semantics. Treat the root `README.md` and [docs/architecture.md](docs/architecture.md) as the current architectural source of truth.
