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
python -m pytest tests/ -v           # All tests (566 tests)
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

**Disease modules** (`src/diseases/`): Config-driven ODE system. All disease logic is defined declaratively in `data/ode_diseases.json` and executed by a single universal engine (`ConfigDrivenDiseaseModule`). Four diseases: pneumonia, acute renal failure, dilated cardiomyopathy, phosphorus poisoning.

### Disease System (Config-Driven)

**Architecture**: Instead of one Python class per disease, all diseases are defined as JSON data and solved by a universal ODE engine.

```
data/ode_diseases.json  →  ConfigDrivenDiseaseModule  →  list[FactorCommand]
     (declarative)            (universal solver)           (engine writes)
```

**`data/ode_diseases.json`**: Each disease entry contains:
- `severity_presets`: `mild` / `moderate` / `severe` parameter sets (ODE rate constants)
- `state_variables`: Named ODE variables with `ode_type`, `params`, `clamp` bounds, and expression strings (`fn`, `derivative_fn`, `target_fn`)
- `outputs`: FactorCommand declarations mapping state variables to engine parameter modifications

**Built-in ODE types** (extensible via `register_ode_type(name, solver_fn)`):
- `logistic`: dS/dt = rate · S · (1 − S/K) + seed_boost
- `algebraic`: S = fn(other_vars) — pure algebraic mapping
- `first_order_lag`: dS/dt = (target − S) / τ
- `custom`: dS/dt = arbitrary fn(state_vars, params)

**Factory pattern**:
```python
from src.diseases import create_disease
disease = create_disease("pneumonia", severity="moderate")
creature.attach_disease(disease)
```

**`register_disease(name, cls, **extra)`** stores `(cls, extra)` tuples; `create_disease()` merges name+extra+kwargs for construction.

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
    death_timer: int | None # moribund countdown (3 actions)
    current_ap: int         # current Action Points (= 时间预算)
    max_ap: int
    total_ap_spent: int     # 累计消耗 AP → 游戏时间 = total_ap_spent × 60s
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
| `cases.json` | 4 cases (pneumonia/ARF/DCM/phosphorus poisoning), difficulty 1-3, species/weight |
| `examinations.json` | 21 exam types with tier (1-5), AP cost, latency, category |
| `diseases.json` | Disease names, clue definitions, clue→test mapping, treatment protocols, win/loss messages |
| `ode_diseases.json` | Declarative ODE definitions for all 4 diseases (state variables, severity presets, output mappings) |
| `treatments.json` | Treatment options |
| `vitals_ranges.json` | Physiological parameter normal ranges, critical thresholds, and clue_flags |
| `exam_templates.json` | Report generation templates (vitals, extra_params, findings_rules, tag_rules) — replaces 21 hardcoded `_gen_*` functions |
| `game_config.json` | Game design constants: AP system, stress, species modifiers, combo bonuses, phase thresholds |

## Key Conventions

- **FactorCommand-only writes**: Never modify engine attributes directly in disease/drug code — always through `apply_factor()`
- **Frozen dataclasses**: Use `@dataclass(frozen=True)` for value objects
- **No `print()`**: Use `logging` module
- **Comments**: Explain "why", not "what". Hack workarounds must have `# TODO(YYYY-MM-DD):`
- **Data externalization**: Disease ODE models, clues, treatment protocols, and exam definitions live in `data/*.json` — not hardcoded in Python
- **Config-driven diseases**: New diseases are added by editing `data/ode_diseases.json` — no Python class needed

## Known Issues

1. **Session storage**: In-memory dict in `gui_app.py` — sessions lost on Flask restart
2. **Frontend type safety**: `updateFrom()` uses `Record<string, unknown>` with manual assertions — add new API fields to both `types.ts` and `updateFrom()`
3. **Exam cost=0 still consumes 1 action**: `_get_examine_cost()` returns `max(1, cost)` for action count tracking
4. **Flask serves built frontend only**: Must run `vp build` after frontend changes — Flask doesn't proxy to Vite dev server in production mode

## Adding a New Exam Type

1. Add entry to `data/examinations.json` with `tier` (1-5), `cost` (AP), `latency_turns`, `category`
2. Add report template to `data/exam_templates.json` with `vitals`, `extra_params`, `findings_rules`, `tag_rules`
3. Run `vp build` after frontend changes
4. No Python code needed — `report_engine.py` and `exam_registry.py` are fully config-driven

## Adding a New Disease

1. Add entry to `data/ode_diseases.json` with:
   - `severity_presets` (`mild`/`moderate`/`severe` with ODE rate constants)
   - `state_variables` (each with `ode_type`, `params`, `clamp`, and expression strings)
   - `outputs` (each with `target`, `op`, `fn`, optional `condition`)
2. Add clues, treatment protocol, and messages to `data/diseases.json`
3. Add case to `data/cases.json`
4. No Python code needed — `ConfigDrivenDiseaseModule` handles everything automatically

**Custom ODE types**: If built-in types are insufficient, register a custom solver:
```python
from src.diseases import register_ode_type
register_ode_type("my_ode", lambda value, params, state_vars, engine_state, dt: new_value)
```

## Game 层重构计划

Game 层（translator / diagnosis_engine / action_system）仍存在大量硬编码，新增疾病/检查类型需要改多个 Python 文件。

详见 [`docs/refactor_game_layer.md`](docs/refactor_game_layer.md) — 包含问题诊断、配置文件设计、解耦机制、分阶段迁移路径。

**目标**：新增疾病/检查类型只改 `data/*.json`，不改任何 Python 代码。
