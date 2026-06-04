# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working in this repository.

## Project Overview

**Virtual Vet** — a veterinary clinical diagnosis education game. Players act as veterinarians: order examinations → review reports → diagnose → treat. Built on a realistic multi-organ ODE physiological simulation engine.

**Tech stack**: Python 3 + Flask backend, Vue 3 + TypeScript + Vite frontend. Frontend builds to `static/`, served directly by Flask via `send_from_directory`.

## Commands

**Always use `uv run` to run Python commands** — keeps the project isolated in `.venv/`
(per `pyproject.toml` + `uv.lock`). Never use bare `python` or `python -m` for project work.

```bash
# Install dependencies (creates .venv/ if missing)
uv sync

# Backend (from project root) — always via `uv run`
uv run python gui_app.py             # Start Flask at http://127.0.0.1:5000
uv run pytest tests/ -v              # All tests
uv run pytest tests/test_game.py -v  # Specific test file

# Lint / Format (Python) — also via `uv run`
uv run ruff check .                  # Lint
uv run ruff format .                 # Format

# Frontend (from vite-project/)
cd vet-game-frontend/vite-project
vp build                             # Build to ../../static/ (Flask serves from there)
vp dev                               # Dev server at http://127.0.0.1:5173 (optional)
vp check                             # Format + lint + type-check (Oxfmt + Oxlint + vue-tsc)

# Gate check (pre-commit / CI)
python tools/dev/gate_check.py --quick   # Fast check: API + data consistency (<5s)
python tools/dev/gate_check.py --full    # Full check: + type consistency (<10s)
python tools/dev/gate_check.py --fix     # Auto-fix: data + type sync
```

**Critical**: After every frontend code change, run `vp build` to update `static/`. Flask serves the built files — the dev server is only for hot-reload during development.

**Git pre-commit hook** is installed. It runs `gate_check.py --quick` before each commit. Skip with `GATE_SKIP=1 git commit ...` or `git commit --no-verify`.

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

**Additional modules**: `cardiac_electrophysiology.py` (detailed cardiac EP), `respiratory_rhythm.py` (respiratory rhythm generator with chemoreceptor drive), `noble_purkinje.py` (Purkinje fiber model), `toxicology.py` (cocaine kinetics), `pharmacology.py` (drug PK/PD), `organ_health.py` (irreversible damage tracking).

**Config-driven report pipeline**: `exam_registry.py` loads exam definitions from `data/examinations.json`; `report_engine.py` generates reports from `data/exam_templates.json`; `vitals_config.py` loads parameter ranges from `data/vitals_ranges.json`. No Python code needed for new exam types.

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

**`test_translator.py`**: Converts engine state → human-readable exam reports. Delegates to `report_engine.py` (config-driven via `data/exam_templates.json`).

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
| --- | --- |
| `cases.json` | Clinical cases (pneumonia/ARF/DCM/phosphorus poisoning/etc.), difficulty 1-3, species/weight |
| `examinations.json` | 21 exam types with tier (1-5), AP cost, latency, category |
| `diseases.json` | Disease names, clue definitions, clue→test mapping, treatment protocols, win/loss messages |
| `ode_diseases.json` | Declarative ODE definitions for all diseases (state variables, severity presets, output mappings) |
| `exam_templates.json` | Report generation templates (vitals, extra_params, findings_rules, tag_rules) — fully config-driven |
| `vitals_ranges.json` | Physiological parameter normal ranges, critical thresholds, and clue_flags |
| `game_config.json` | Game design constants: AP system, stress, species modifiers, combo bonuses, phase thresholds |
| `treatments.json` | Treatment options |

## Key Conventions

- **FactorCommand-only writes**: Never modify engine attributes directly in disease/drug code — always through `apply_factor()`
- **Frozen dataclasses**: Use `@dataclass(frozen=True)` for value objects
- **No `print()`**: Use `logging` module
- **Comments**: Explain "why", not "what". Hack workarounds must have `# TODO(YYYY-MM-DD):`
- **Data externalization**: Disease ODE models, clues, treatment protocols, and exam definitions live in `data/*.json` — not hardcoded in Python
- **Config-driven diseases**: New diseases are added by editing `data/ode_diseases.json` — no Python class needed
- **Config-driven exams**: New exam types are added by editing `data/examinations.json` + `data/exam_templates.json` — no Python code needed

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

## Gate Check System (`tools/dev/`)

Three static analysis scripts run pre-commit and can be invoked manually:

- **`gate_check.py`**: Unified entry point. `--quick` (API + data), `--full` (+ types), `--fix` (auto-fix), `--install-hook`
- **`check_api_consistency.py`**: AST-based Flask route vs `api.ts` call validation. `--fix` syncs missing fields to `types.ts`
- **`check_data_consistency.py`**: Cross-validates 7 JSON data files (cases→diseases→clues→exams→vitals→ODE paths). `--fix` auto-generates missing `clue_descriptions`

Auto-fixable issues: missing `clue_descriptions` (pattern-based Chinese generation), missing `types.ts` interface fields (backend response field sync).

---

## Scientific Agent Skills（科研论文产出优先）

本项目**优先使用**以下已安装的 agent skill，确保论文产出质量：

### Skill 来源（优先级排序）

| 来源 | 安装位置 | 数量 | 用途 |
|------|---------|------|------|
| [academic-research-skills](https://github.com/Imbad0202/academic-research-skills) (v3.9.4) | `~/.claude/skills/academic-research-skills/` | 4 skill + 13 命令 | **全流程**：研究→写作→审稿 |
| [nature-skills](https://github.com/Yuan1z0825/nature-skills) (11.1k stars) | `~/.claude/skills/nature-skills/` | 9 skill | Nature 风格专用 |
| [scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) (25.5k stars) | `~/.claude/skills/scientific-agent-skills/` | 139 skill | 补充工具 |
| [nature-writing](https://github.com/SyntaxSmith/nature-writing-skill) | `~/.claude/skills/nature-writing/` | 44 篇 OA 语料库 | Nature 写作模板 |

### 核心 Skill 命令

| Skill | 触发命令 | 用途 |
|-------|---------|------|
| **academic-research** | `/ars-plan` | Socratic 对话规划论文结构 |
| | `/ars-lit-review "topic"` | 系统性文献调研 |
| | `/ars-full` | 全流程论文写作 |
| | `/ars-reviewer` | 多视角同行评审 |
| **nature-figure** | `/nature-figure` | Nature 风格多面板图 |
| **nature-polishing** | `/nature-polishing` | 学术 prose 润色 |
| **nature-citation** | `/nature-citation` | CNS 引用检索 |
| **nature-reader** | `/nature-reader` | 双语对照论文阅读 |
| **nature-response** | `/nature-response` | 审稿回复信 |
| **hypothesis-generation** | `/hypothesis-generation` | 设计实验方案 |
| **literature-review** | `/literature-review` | 系统性文献调研 |
| **peer-review** | `/peer-review` | 同行评审 |
| **matplotlib** | `/matplotlib` | 科学数据可视化 |

### 使用方式

在 Claude Code 对话中直接 slash 触发：

```text
/ars-plan              → Socratic 对话规划论文章节结构
/ars-lit-review        → 系统性文献调研
/ars-full              → 全流程论文写作（从大纲到投稿）
/ars-reviewer          → 多视角同行评审（EIC + 3审稿人 + 魔鬼代言人）
/ars-abstract          → 双语摘要 + keywords
/nature-figure         → 绘制 publication-grade 曲线
/nature-polishing      → 润色学术 prose
/nature-citation       → 补齐参考文献
/nature-reader         → 读论文生成双语对照
/hypothesis-generation → 设计实验方案
```

### 论文产出重点

- **结构规划**：`/ars-plan` Socratic 对话 → 明确论文贡献点
- **Figure 1-4**：`/nature-figure` + `/matplotlib` 生成 MAP/HR/SVR 时序图 + 11 模块架构图
- **Introduction/Results**：`/ars-full` 或 `/nature-polishing` 把 simulation results 写成学术 prose
- **参考文献**：`/ars-lit-review` + `/nature-citation` 补齐 baroreflex/Frank-Starling/CVP 相关引用
- **同行评审**：`/ars-reviewer` 做多视角自我评审，识别论证漏洞
- **审稿回复**：`/nature-response` 写逐点回复信

### 完整性保证

academic-research-skills 包含 7-mode 阻塞检查清单（Lu et al. 2026, Nature 651:914-919 的 AI Scientist 失败模式），在 Stage 2.5/4.5 integrity gates 自动运行，防止：
- 实现 bug、幻觉结果、捷径依赖
- Bug-as-insight 重构、方法论编造
- Frame-lock、引用幻觉

不需要全部激活，按需触发，按场景使用。
