# Harness Engineering

This project uses harnesses to make validation repeatable and explicit.
A harness is an outer driver that runs the right checks for the layer being
changed, without turning every edit into a full research validation run.

## Entry Point

Use:

```bash
python tools/dev/harness_check.py <profile>
```

Available profiles:

| Profile | Purpose |
| --- | --- |
| `quick` | Fast pre-commit signal: API/data gate. |
| `contract` | API/data/session contract invariants. |
| `api` | API contract and Flask interface changes. |
| `frontend` | Frontend type contract only. |
| `app` | App/API/session/frontend workflow confidence. |
| `core` | Normal Python core regression confidence. |
| `release` | Core regression plus frontend type confidence. |

List commands without running them:

```bash
python tools/dev/harness_check.py --list
python tools/dev/harness_check.py core --dry-run
```

Each run writes a JSON report by default:

```bash
results/harness/latest.json
```

Override or disable it:

```bash
python tools/dev/harness_check.py app --report results/harness/app.json
python tools/dev/harness_check.py quick --no-report
```

## Routing Rule

- API, session, or `gui_app.py` changes: run `contract`, then `api` or `app` if user-facing.
- Frontend API wrapper or Vue component changes: run `frontend`, then `app`.
- Runtime, action flow, diagnosis, treatment, or report workflow changes: run `app`.
- Broad Python changes: run `core`.
- Broad cross-stack changes: run `release`.
- Solver, disease endurance, long-horizon numerics, or performance changes still need targeted `heavy`, `benchmark`, or `research` commands from `docs/testing.md`.

## Current Harness Invariants

- Session-owned state must have a session lock.
- Session read and write endpoints must acquire the lock.
- Frontend GET calls must not send a request body.
- API route/method drift is checked by `tools/dev/check_api_consistency.py`.
- App-layer tests should use fake runtime/advancer seams unless real physiology is the assertion.

## Width Checks

A profile is too wide when it:

- routinely exceeds its intended budget
- fails far from the edited layer
- repeats the same coverage in multiple slow steps
- is often bypassed by developers

A profile is too narrow when a bug escapes from the risk it claims to cover.
When that happens, add a regression to the narrowest relevant profile first.

Current soft budgets:

| Profile | Budget |
| --- | ---: |
| `quick` | 5s |
| `contract` | 15s |
| `frontend` | 10s |
| `api` | 20s |
| `app` | 60s |
| `core` | 70s |
| `release` | 85s |

## Non-Goals

- The harness does not replace scientific validation.
- The harness should not silently run ultra-heavy research checks.
- The harness should not write generated static assets or experiment outputs.
