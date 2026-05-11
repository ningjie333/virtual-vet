# Bioflow Labs Platform — Reference Report

## 1. Project Overview

**Repository**: [codyjustustucker-spec/Bioflow_Labs_Platform](https://github.com/codyjustustucker-spec/Bioflow_Labs_Platform)
**License**: MIT
**Language**: Python 3
**Engine Version**: `2.0.0-dev`
**Status**: Actively developed (last commit 2025-12-22)

A deterministic, template-driven physiology simulation engine with schema-validated inputs, content-addressed templates, and SQLite-backed run history for reproducible experimentation.

---

## 2. Architecture

### Package Layout

```
src/bioflow/
├── core/                    # Contracts + utilities (no deps on engine/db)
│   ├── template_schema.py   # JSON Schema v2.0 (Draft 2020-12)
│   ├── validate_template.py # Validator with Phase5 defaults injection
│   ├── hashing.py           # SHA-256 canonical hashing
│   ├── logging.py           # Structured event logging
│   ├── units.py             # Canonical unit conventions
│   └── version.py           # ENGINE_VERSION constant
│
├── db/                      # SQLite persistence (no ORM)
│   ├── conn.py              # Connection: WAL mode + foreign keys ON
│   ├── schema.py            # DDL (4 tables, 3 indexes)
│   ├── templates.py         # Template CRUD + deduplication by hash
│   └── runs.py              # Run/Sample/Event CRUD
│
├── engine/                  # Execution engine (isolated from DB/CLI)
│   ├── state.py             # GlobalState frozen dataclass
│   ├── runner.py            # Load→Validate→Run→Log orchestration
│   └── physiology/          # Pure physiological computations
│       ├── algebraic.py      # Ohm's law bed flow solver
│       ├── compliance.py     # Phase 4.1 dynamic volumes + limits
│       └── modifiers.py     # Phase 5 posture/tone/volume modifiers
│
├── engine_app/
│   └── cli.py               # CLI: run-file / run-id commands
│
└── tools/
    └── import_templates.py  # Bulk template import utility
```

**Key architectural principle**: `engine/physiology/` has zero imports from `db/` or `engine_app/`. The physiological layer is completely side-effect free and deterministic.

---

## 3. Canonical Units

```
pressure:       mmHg
volume:         mL
flow:           mL/s
resistance:     mmHg·s/mL
compliance:     mL/mmHg
time:           seconds (float), samples store t_ms (int)
```

---

## 4. Phase Roadmap

| Phase | Name | Done Criteria |
|-------|------|--------------|
| 0 | Repo + Modules | Clean imports, boundaries enforced, versioning |
| 1 | Template Schema v2.0 + Validation | Invalid templates rejected with clear errors |
| 2 | Persistence Layer | SQLite WAL, template dedup, run history |
| 3 | Engine Runner | Load→Validate→Run→Log, deterministic replay |
| 4.0 | Algebraic Multi-Bed | Parallel beds compete for flow via Ohm's law |
| 4.1 | Volumes + Compliance | Dynamic circulation, blood volume conservation |
| 5 | Posture/Tone/Volume Modifiers | Non-reflexive stressors, provable no-regression |

---

## 5. Core Modules

### 5.1 `template_schema.py` — JSON Schema v2.0 (Draft 2020-12)

Schema enforces:
- `template_version: "2.0"` (strict version lock)
- `total_blood_volume_ml > 0`
- `R_mmHg_s_per_ml > 0` (resistance must be positive)
- `C_ml_per_mmHg > 0` (compliance must be positive)
- `additionalProperties: false` on most objects (prevents typos)
- Required fields: `resolved_parameters.total_blood_volume_ml`, `resolved_parameters.beds`, `resolved_parameters.pump`, `resolved_parameters.compartments`

Phase 4.1 extended schema adds:
- `resolved_parameters.pump.Q_ml_per_s`
- `resolved_parameters.compartments.arterial.{C_ml_per_mmHg, V0_ml}`
- `resolved_parameters.compartments.venous.{C_ml_per_mmHg, V0_ml}`
- `initial_state.{V_art_ml, V_ven_ml}` (optional)

Phase 5 extended schema adds (all optional, neutral default=1.0):
- `resolved_parameters.vascular_tone_factor` (range 0.2–5.0)
- `resolved_parameters.blood_volume_factor` (range 0.5–1.5)
- `resolved_parameters.posture` (enum: supine|standing)
- `resolved_parameters.pooling_bias_enabled` (boolean)
- Per-bed `pooling_bias` (range 0.0–10.0)

### 5.2 `validate_template.py`

```python
def validate_template(template: dict) -> dict:
    # Returns:
    # {
    #     "is_valid": bool,
    #     "errors": list[str],
    #     "warnings": list[str],
    #     "template_hash": str,        # SHA-256 of normalized template
    #     "normalized_template": dict   # defaults injected
    # }
```

**Critical behavior**: `_apply_phase5_defaults()` injects neutral defaults (factor=1.0, posture=supine) before hashing. This ensures that `{"total_blood_volume_ml": 5000}` and `{"total_blood_volume_ml": 5000, "vascular_tone_factor": 1.0}` produce **identical hashes**.

### 5.3 `hashing.py`

```python
def normalize_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def hash_json(obj: Any) -> str:
    s = normalize_json(obj).encode("utf-8")
    return hashlib.sha256(s).hexdigest()
```

- `sort_keys=True`: stable key ordering regardless of dict insertion order
- `separators=(",", ":")`: compact encoding, no trailing spaces
- SHA-256 → 64-char hex

Template hash used for: deduplication, run identity, summary verification.

### 5.4 `db/schema.py`

```sql
CREATE TABLE templates (
  id INTEGER PRIMARY KEY,
  name TEXT,
  created_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  json TEXT NOT NULL,
  template_version TEXT NOT NULL,
  is_valid INTEGER CHECK (is_valid IN (0,1)),
  validation_errors TEXT,
  template_hash TEXT NOT NULL UNIQUE
);

CREATE TABLE runs (
  id INTEGER PRIMARY KEY,
  started_at TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
  ended_at TEXT,
  template_hash TEXT NOT NULL REFERENCES templates(template_hash),
  template_snapshot_json TEXT NOT NULL,
  engine_version TEXT NOT NULL,
  run_config_json TEXT NOT NULL,
  summary_json TEXT
);

CREATE TABLE run_samples (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
  t_ms INTEGER NOT NULL,
  global_state_json TEXT NOT NULL
);

CREATE TABLE run_events (
  id INTEGER PRIMARY KEY,
  run_id INTEGER REFERENCES runs(id) ON DELETE CASCADE,
  t_ms INTEGER NOT NULL,
  level TEXT NOT NULL,
  code TEXT NOT NULL,
  message TEXT NOT NULL
);
```

Indexes:
- `idx_templates_is_valid ON templates(is_valid)`
- `idx_samples_run_id_t ON run_samples(run_id, t_ms)`
- `idx_events_run_id_t ON run_events(run_id, t_ms)`

### 5.5 `db/conn.py`

```python
def connect(db_path: str | Path) -> sqlite3.Connection:
    p = Path(db_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row  # dict-like access
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    return conn
```

- `WAL mode`: 写操作不阻塞读，支持并发
- `foreign_keys = ON`: 强制外键约束
- `row_factory = sqlite3.Row`: 行支持 `row["col"]` 访问

### 5.6 `db/templates.py`

- `insert_template()`: deduplicates by `template_hash` (UNIQUE constraint)
- `fetch_template_by_hash()`: used by runner to avoid re-inserting
- `delete_invalid_templates()`: cleanup utility
- `list_runnable_templates()`: UI 用途

### 5.7 `db/runs.py`

- `create_run()`: 创建 run record (不 finalize)
- `append_sample()`: 批量 buffer 采样
- `append_event()`: 结构化事件 (level/code/message)
- `finalize_run()`: 写入 ended_at + summary_json
- `commit_buffer()`: 显式 commit

### 5.8 `engine/state.py`

```python
@dataclass
class GlobalState:
    t_s: float
    V_art_ml: float
    V_ven_ml: float
    P_art_mmHg: float
    P_ven_mmHg: float
    bed_Q_ml_per_s: Dict[str, float]
    bed_perfusion_index: Dict[str, float]

    def to_json(self) -> dict:
        return asdict(self)
```

Note: uses `@dataclass` (not frozen), because state is mutated step-to-step. Frozen dataclasses used for **parameter** objects (BedParameters, CompartmentParameters).

### 5.9 `engine/physiology/algebraic.py`

```python
@dataclass(frozen=True)
class BedParameters:
    bed_id: str
    R_mmHg_s_per_ml: float
    pooling_bias: float = 0.0

def compute_bed_flows(
    *, P_art_mmHg, P_ven_mmHg, beds, baseline_flows_ml_per_s
) -> List[BedFlowResult]:
    # Q_bed = max(0, (P_art - P_ven) / R_bed)
    # perfusion_index = clamp(100 * Q / Q_baseline, 0, 200)
    for bed in beds:
        if bed.R_mmHg_s_per_ml <= 0:
            raise ValueError(f"Bed '{bed.bed_id}' has non-positive resistance")
        raw_Q = deltaP_mmHg / bed.R_mmHg_s_per_ml
        Q_ml_per_s = raw_Q if raw_Q > 0 else 0.0
        ...
```

Key design:
- Baseline flows computed **once** from template baseline pressures
- `perfusion_index = 100` when at baseline conditions (normalization anchor)
- Hard fail on invalid resistance (no silent clamp)

### 5.10 `engine/physiology/compliance.py`

```python
def pressure_mmHg(*, V_ml, C_ml_per_mmHg, V0_ml) -> float:
    P = (V_ml - V0_ml) / C_ml_per_mmHg
    return P if P > 0.0 else 0.0  # floor at 0

def step_phase41_compliance(*, prev_state, dt_s, beds, ...) -> (GlobalState, dict):
    # 1. Compute pressures from current volumes
    # 2. Compute algebraic bed flows
    # 3. Deterministic safety limiters:
    #    - max_pump = Q_out + V_ven/dt
    #    - if Q_out > max_out: proportional scale all bed flows (preserves competition ratios)
    # 4. Conservative volume update: dV_art = (Q_pump - Q_out) * dt
    #    V_art_next = V_art + dV_art
    #    V_ven_next = V_ven - dV_art   # total conserved
    # 5. Recompute pressures at next volumes
```

### 5.11 `engine/physiology/modifiers.py`

```python
@dataclass(frozen=True)
class EffectiveModifiers:
    vascular_tone_factor: float = 1.0
    blood_volume_factor: float = 1.0
    posture: str = "supine"
    bed_v0_shift_ml: Optional[Dict[str, float]] = None

def apply_vascular_tone_to_beds(beds, vascular_tone_factor):
    if vascular_tone_factor == 1.0: return beds  # fast path, no allocation
    return [replace(b, R_mmHg_s_per_ml=b.R_mmHg_s_per_ml * vascular_tone_factor) for b in beds]

def effective_standing_venous_v0_shift_ml(posture, pooling_bias_enabled, beds):
    if posture == "supine": return 0.0
    base = 500.0  # mL venous pooling when standing
    if not pooling_bias_enabled: return base
    avg_bias = mean(pooling_bias for b in beds)
    scale = clamp(1.0 + 0.25 * avg_bias, 1.0, 3.0)
    return base * scale
```

Constraints:
- Pure transforms only (no randomness, no feedback)
- factor=1.0 → mathematically identical to Phase 4.1 (provable)

### 5.12 `engine/runner.py`

Orchestration pipeline:

```python
def run_template(*, template, db_path, dt, duration_s, sample_rate_hz, conn=None):
    1. validate_template() → RunnerError if invalid
    2. connect() + init_db()
    3. fetch/insert template (dedupe by hash)
    4. create_run() → run_id
    5. _build_initial_state(template)
    6. _build_bed_parameters_from_template()
    7. _compute_baseline_flows()  # once, from baseline pressures
    8. for step in range(steps+1):
         if t >= next_sample_t:
             append_sample(conn, run_id, t_ms, state.to_json())
         state, metrics = step_phase41_compliance(prev_state=state, ...)
    9. commit_buffer()
    10. summary = {final_t_s, final_P_*, final_V_*, final_total_volume, summary_hash}
    11. finalize_run(conn, run_id, summary)
    12. return {run_id, template_hash, engine_version, run_config, summary}
```

**Determinism guarantee**: `summary_hash = hash_json({template_hash, run_config, summary})`. Same inputs → same hash. Verified by `test_same_template_twice_identical_summary_hash`.

**Error handling**: exception → `append_event(ERROR, code="run_failed")` → no finalize (partial runs not marked success).

### 5.13 `engine_app/cli.py`

```bash
# Run from JSON file
python -m bioflow.engine_app.cli run-file template.json --db data/bioflow.db --dt 0.01 --duration 10.0 --sample-rate 10.0

# Run by database template ID
python -m bioflow.engine_app.cli run-id 42 --db data/bioflow.db --dt 0.01 --duration 10.0 --sample-rate 10.0
```

---

## 6. Test Coverage

| Test File | Coverage |
|-----------|----------|
| `test_template_validation.py` | Pass/fail validation, hash determinism |
| `test_db_runs.py` | Template dedup, run persistence |
| `test_db_template.py` | FK integrity, cleanup |
| `test_runner_phase3.py` | Deterministic replay (same hash twice), invalid template hard fail, DB/JSON paths |
| `test_phase41_conservation.py` | Total blood volume conservation |
| `test_phase5_*.py` | Tone/posture/hypovolemia effects, pooling bias gate, no-regression neutral settings, hash equivalence |

**Key test patterns**:
```python
def test_same_template_twice_identical_summary_hash(tmp_path):
    a = run_template(template=t, ...)
    b = run_template(template=t, ...)
    assert a["summary"]["summary_hash"] == b["summary"]["summary_hash"]

def test_run_invalid_template_hard_fails_no_run_row_created(tmp_path):
    try:
        run_template(template=invalid_t, ...)
        assert False
    except RunnerError:
        pass
    n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()["n"]
    assert n == 0  # no partial run
```

---

## 7. Design Patterns

| Pattern | Usage in Bioflow |
|---------|-----------------|
| **frozen dataclass** | `BedParameters`, `BedFlowResult`, `CompartmentParameters`, `EffectiveModifiers` — immutable parameter bundles |
| **algebraic over numerical** | Phase 4.0 pure algebraic (no ODE integration) — always stable |
| **hard fail on invalid physics** | R ≤ 0, C ≤ 0, dt ≤ 0 → `ValueError`, no silent clamping |
| **neutral default injection** | Phase 5 defaults applied at validate time, hash stable regardless of explicit/implicit neutral |
| **conservative updates** | Volume conservation: `V_art_next + V_ven_next = V_art + V_ven` always |
| **proportional limiter** | When outflow exceeds safe limit, scale all bed flows proportionally (preserves competition ratios) |
| **template normalization** | Defaults injected before hashing → same semantics always produces same hash |
| **baseline once** | Perfusion baseline computed once at startup → guarantees `index=100` at baseline |

---

## 8. Phase 5 Modifier Detail

Implemented purely as parameter transforms, no new state variables:

| Modifier | Parameter | Effect | Neutral |
|---------|-----------|--------|---------|
| Vascular tone | `vascular_tone_factor` | `R_eff = R × factor` | 1.0 |
| Blood volume | `blood_volume_factor` | `TBV × factor`, load-time only | 1.0 |
| Posture | `posture` | Standing: `V0_ven += 500ml` (pooling) | supine |
| Pooling bias | `pooling_bias_enabled` + per-bed `pooling_bias` | `scale = 1 + 0.25 × avg_bias`, clamp [1, 3] | disabled |

All modifiers are **load-time or step-time parameter shifts** — no hidden state, no feedback loops, no randomness.

---

## 9. Reference Links

- Repository: https://github.com/codyjustustucker-spec/Bioflow_Labs_Platform
- JSON Schema Draft 2020-12: https://json-schema.org/
- SQLite WAL mode: https://www.sqlite.org/wal.html