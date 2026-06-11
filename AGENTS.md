# Agent Guide

Project-level instructions for automated coding agents working in this repo.
Keep this file concise; use linked docs for full rationale.

## Architecture

- Treat `README.md` and `docs/architecture.md` as the current source of truth.
- The physiology kernel is the core product.
- `src/` owns kernel and clinical interpretation code.
- `game/`, `gui_app.py`, and `vet-game-frontend/` are outer application layers.
- Allowed dependency direction: app/game -> interpretation -> kernel.
- Do not introduce imports from `src/` back into `game/`, `gui_app.py`, Flask, or frontend code.
- Gameplay pacing must not redefine kernel time, solver meaning, or disease rates.
- Prefer `GameRuntime` seams for app-layer tests and workflows.

## Session And API Rules

- Any endpoint that reads or writes session-owned state must use the session lock.
- Treat a session without a lock as invalid, even if `_game_sessions` still has state.
- State-changing endpoints include `examine`, `administer-drug`, `diagnose`, and `wait`.
- Snapshot/read endpoints such as `game-state`, `hint`, and `diagnosis` should also lock.
- Frontend GET calls must pass parameters in the query string, never in a request body.
- Query values from the frontend should use `encodeURIComponent`.
- Keep API contract checks in `tools/dev/check_api_consistency.py` current when adding endpoint patterns.

## Testing

- Quick gate before committing:
  `python tools/dev/gate_check.py --quick`
- Core app/runtime/API confidence:
  `python -m pytest --channel core -q`
- Frontend type check:
  `.\node_modules\.bin\vue-tsc.cmd -b` from `vet-game-frontend/vite-project`
- For narrow API work, also run targeted interface tests:
  `python -m pytest tests/test_interface.py -q`
- Use heavy, benchmark, or research channels only when touching solver, disease endurance, long-horizon numerics, or performance behavior.
- App-layer tests should use fake runtime/advancer seams unless real physiological progression is the assertion.

## Frontend

- The frontend has its own local guide at `vet-game-frontend/vite-project/AGENTS.md`.
- Use existing Vue/Vite+ patterns; do not replace the toolchain.
- Do not rely on generated `static/index.html` or hashed assets as source changes unless explicitly publishing a build.

## Data And Generated Files

- Do not commit failed experiment outputs, traceback-filled JSON, local caches, or generated dependency folders.
- Be careful with experiment JSON files; large numeric diffs should be intentional and explained.
- `static/` is ignored except tracked legacy files; avoid committing only an HTML hash update without assets.
- External reference folders such as `Medicina-main/`, `Bioflow_Labs_Platform-main/`, and `cvs-reference/` are not normal project code.

## Git Hygiene

- The worktree may contain user changes; never revert unrelated edits.
- Keep commits focused by concern.
- Use non-interactive git commands.
- Do not use destructive commands such as `git reset --hard` or `git checkout --` unless explicitly asked.

## When Unsure

- Prefer small, conservative changes that preserve the kernel/app boundary.
- Add or update tests for new invariants.
- If a rule seems wrong, update the authoritative docs and this guide together.
