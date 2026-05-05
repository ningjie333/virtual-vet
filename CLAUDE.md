# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working on this repository.

## Project Overview

**Virtual Vet** — a veterinary clinical diagnosis education game. Players act as veterinarians: order examinations → review reports → diagnose → treat. Built on a realistic multi-organ ODE physiological simulation engine.

**Tech stack**: Python 3 + Flask backend, Vue 3 + TypeScript + Vite frontend. Frontend builds to `static/`, served directly by Flask via `send_from_directory`.

## Commands

```bash
# Install dependencies
uv sync

# Backend (from project root)
python gui_app.py                    # Start Flask at http://127.0.0.1:5000
python -m pytest tests/ -v           # All tests (552 tests)
python -m pytest tests/test_game.py -v  # Specific test file

# Frontend (from vite-project/)
cd vet-game-frontend/vite-project
vp build                             # Build to ../static/ (Flask serves from there)
vp dev                               # Dev server at http://127.0.0.1:5173 (optional)
vp check                             # Format + lint + type-check
```

**Critical**: After every frontend code change, run `vp build` to update `static/`. Flask serves the built files — the dev server is only for hot-reload during development.

## Architecture

### Data Flow

```
Frontend → POST /api/examine {test_type} → process_action() → test_translator.translate()
    → reads VirtualCreature state → returns report dict

Frontend → GET /api/diagnosis → match_diseases(reports) → returns confidence-ranked diseases

Frontend → POST /api/diagnose {diagnosis} → apply_treatment() → drug protocol → win/loss
```

### Core Simulation (`src/`)

**`VirtualCreature`** (`src/simulation.py`): Main engine integrating all organ modules. Each `step(dt)` advances all organs + disease effects.

**FactorCommand pattern** (`src/simulation.py:32`): Unified write interface for all physiological modifications:
```python
@dataclass(frozen=True)
class FactorCommand:
    target: str  # dot-path like "heart.heart_rate"
    op: Literal["multiply", "add", "set"]
    value: float
```
All diseases, drugs, and treatments modify engine state exclusively through `apply_factor(cmd)` which resolves targets via `_PARAM_PATHS` mapping table.

**Organ modules**: `heart.py` (HR, SV, CO, SVR), `lung.py` (ventilation, gas exchange), `kidney.py` (GFR, urine, RAAS), `blood.py` (chemistry), `fluid.py` (3-compartment + pH via Henderson-Hasselbalch).

**Disease modules** (`src/diseases/`): Each disease is an ODE system returning multiplicative factors. Three diseases: pneumonia (4 ODEs: exudate/bacteria/fever/hypoxia), acute renal failure, dilated cardiomyopathy.

### Game Layer (`game/`)

**`action_system.py`**: `GameState` dataclass + `process_action()` — the central game loop. Implements:
- **5-tier AP system**: Tier 1 (0 AP, free exams) → Tier 5 (8 AP, gold-standard tests)
- **AP budget**: `current_ap`/`max_ap` on GameState; regenerates on wait (+2) and per-turn (+1)
- **Combo bonuses**: Related exam groups give AP discounts (e.g., X-ray + ultrasound = -1 AP)
- **Result latency**: Tier 3-5 exams delay results 1-3 turns (`PendingReport` queue)
- **Stress meter**: Invasive procedures add stress (0/2/5/10/15 per tier); >50 unreliable vitals, >80 accelerates deterioration
- **Species modifiers**: Canine (baseline), Feline (+1-2 AP for high-tier), Equine (+1 basic, -1 imaging)

**`diagnosis_engine.py`**: Clue extraction from reports → disease matching via confidence scoring. All disease data loaded from `data/diseases.json`.

**`test_translator.py`**: Converts engine state → human-readable exam reports. 21 exam types across 5 tiers.

**`treatment.py`**: Validates diagnosis + executes drug protocols via `data/diseases.json`.

**`time_manager.py`**: Game clock (starts 08:00), night cycle (22:00-06:00) with HR ×0.85 and disease progression ×0.8.

### Game State (`GameState` in `action_system.py`)

```python
@dataclass
class GameState:
    engine: VirtualCreature
    disease_name: str
    phase: str              # "playing" | "won" | "lost"
    action_count: int
    game_clock_s: float
    death_timer: int | None # moribund countdown (3 actions)
    current_ap: int         # current Action Points
    max_ap: int
    species: str
    stress_level: float     # 0-100
    pending_reports: list[PendingReport]  # delayed results
    recent_exam_types: list[str]  # combo tracking window
```

### Frontend (`vet-game-frontend/vite-project/`)

- **`App.vue`**: Root component — all state management, API calls, `updateFrom()` helper that merges API responses into reactive state
- **`api.ts`**: Typed wrappers for all `/api/*` endpoints
- **`types.ts`**: TypeScript interfaces mirroring backend data structures
- **`components/`**: `CaseSelect`, `PatientCard`, `ExamGrid` (shows AP costs + tier badges), `ReportList`, `DiagnosisPanel`, `VitalCard`, `GameLog`, `GameOverOverlay`

### Data Files (`data/`)

| File | Content |
|------|---------|
| `cases.json` | 3 cases (pneumonia/ARF/DCM), difficulty 1-3, species/weight |
| `examinations.json` | 21 exam types with tier (1-5), AP cost, latency, category |
| `diseases.json` | Disease names, clue definitions, clue→test mapping, treatment protocols, win/loss messages |
| `treatments.json` | 4 treatment options (3 diseases + supportive care) |

## Key Conventions

- **FactorCommand-only writes**: Never modify engine attributes directly in disease/drug code — always through `apply_factor()`
- **Frozen dataclasses**: Use `@dataclass(frozen=True)` for value objects
- **No `print()`**: Use `logging` module
- **Comments**: Explain "why", not "what". Hack workarounds must have `// TODO(YYYY-MM-DD):` or `# TODO(YYYY-MM-DD):`
- **Data externalization**: Disease clues, treatment protocols, and exam definitions live in `data/*.json` — not hardcoded in Python

## Known Issues

1. **Session storage**: In-memory dict in `gui_app.py` — sessions lost on Flask restart
2. **Frontend type safety**: `updateFrom()` uses `Record<string, unknown>` with manual assertions — add new API fields to both `types.ts` and `updateFrom()`
3. **Exam cost=0 still consumes 1 action**: `_get_examine_cost()` returns `max(1, cost)` for action count tracking
4. **Flask serves built frontend only**: Must run `vp build` after frontend changes — Flask doesn't proxy to Vite dev server in production mode

## Adding a New Exam Type

1. Add entry to `data/examinations.json` with `tier` (1-5), `cost` (AP), `category`
2. Add handler to `_EXAM_CONFIG` in `game/action_system.py`: `(ap_cost, tier, latency_turns)`
3. Add report generator function in `game/test_translator.py` + register in `_TEST_DISPATCH`
4. Run `vp build` after frontend changes

## Adding a New Disease

1. Create module in `src/diseases/` extending `DiseaseModule`, returning FactorCommand-compatible factors
2. Register in `src/diseases/__init__.py` `create_disease()` factory
3. Add clues, treatment protocol, and messages to `data/diseases.json`
4. Add case to `data/cases.json`
