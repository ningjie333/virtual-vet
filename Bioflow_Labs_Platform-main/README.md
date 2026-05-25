## Roadmap Progress

### Phase 0 — Repo + Modules ------------------------------------------------------------
**Done when:** imports are clean and boundaries enforced.

- Established v2 package layout:
  - `src/bioflow/core/` (contracts + core utilities)
  - `src/bioflow/engine_app/` (CLI / runner entrypoints)
  - `src/bioflow/db/` (SQLite persistence layer)
  - `tools/` (developer utilities)
  - `tests/` (automated regression tests)
- Added engine versioning via `ENGINE_VERSION`
- Defined canonical unit conventions (documented once; used consistently)
- Added structured logging baseline for deterministic, traceable runs

---

### Phase 1 — Template Schema v2.0 + Validation ------------------------------------------------------------
**Done when:** invalid templates are rejected with clear, actionable errors.

- Implemented JSON Schema (Draft 2020-12) for Template v2.0
- Enforced “runnable” structural rules:
  - required fields present (`template_version`, `resolved_parameters`, `beds`)
  - numeric bounds (e.g., `total_blood_volume_ml > 0`, `R > 0`, `C > 0`)
  - strict field control (`additionalProperties: false` where appropriate)
- Added deterministic template hashing:
  - canonical JSON normalization (stable key ordering / formatting)
  - SHA-256 content hash (`template_hash`) for de-duplication and reproducibility
- Implemented `validate_template()` output contract:
  - `is_valid`
  - `errors[]`
  - `warnings[]`
  - `template_hash`
- Added fixture templates (valid + intentionally invalid) and pytest coverage:
  - valid baseline template fixture
  - invalid missing-field fixture
  - tests for pass/fail validation + deterministic hash behavior

---

## Phase 2 – Persistence Layer ------------------------------------------------------------
- SQLite-backed storage (no ORM)
- Template de-duplication via content hashing
- Run history with samples and structured events
- WAL mode + foreign key enforcement
- Fully covered by pytest integration tests

---

### Phase 3 — Engine Runner (Load → Validate → Run → Log) ------------------------------------------------------------
**Done when:** templates can be executed from multiple entry points and produce a deterministic, fully logged run record.

- Implemented runner orchestration pipeline:
  - load template (DB id, JSON file, or direct object)
  - validate and hard-fail non-runnable templates
  - build deterministic initial state (from `initial_state` or defaults)
  - execute fixed-step simulation loop
  - persist run artifacts to DB
- Added CLI execution paths:
  - run by template DB id
  - run by JSON file path
- Implemented run persistence:
  - immutable run record (`runs`)
  - downsampled time-series samples (`run_samples`)
  - structured runtime events (`run_events`)
  - computed run summary with deterministic `summary_hash`
- Enforced determinism:
  - same template + same run config → identical summary hash
- Ensured referential integrity and connection hygiene:
  - automatic template insertion for FK safety
  - single-connection execution (no double-connect)
  - explicit connection ownership and closure
- Full pytest coverage:
  - deterministic replay test
  - invalid template refusal (no partial run)
  - DB id and JSON file execution paths

  ### Phase 4.0 — Algebraic Multi-Bed Physiology ------------------------------------------------------------
**Done when:** parallel organ beds compete for flow deterministically with stable, conserved behavior.

- Implemented physiology core (engine-isolated from runner):
  - pure algebraic flow solver (no dynamics yet)
  - physiology lives entirely under `engine/physiology/`
  - runner remains physics-agnostic
- Added explicit bed abstraction:
  - per-bed resistance (`R_mmHg_s_per_ml`)
  - parallel beds fed by common arterial pressure
  - single merged venous return
- Implemented deterministic flow computation:
  - `Q_bed = max(0, (P_art − P_ven) / R_bed)`
  - no randomness, no hidden state
  - same inputs → identical outputs
- Added perfusion indexing:
  - baseline flow computed once from template baseline pressures
  - per-bed perfusion index normalized to baseline (`100 = baseline`)
- Expanded engine state:
  - tracked global pressures (`P_art_mmHg`, `P_ven_mmHg`)
  - recorded per-bed flows and perfusion indices in samples
- Enforced stability and safety:
  - negative flows clamped to zero
  - invalid resistance values hard-fail
- Added pytest coverage:
  - Ohm’s-law correctness
  - bed competition (raising one bed’s resistance reduces its flow)
  - conservation of total flow across beds
  - determinism across repeated runs

---

### Phase 4.1 — Volumes + Compliance (Dynamic Circulation) ------------------------------------------------------------
**Done when:** pressures evolve over time via compliant compartments while conserving total blood volume.

- Introduced explicit compartment volumes:
  - arterial volume (`V_art_ml`)
  - venous volume (`V_ven_ml`)
  - total blood volume conserved at all times
- Added linear compliance model:
  - `P = max(0, (V − V0) / C)`
  - separate arterial and venous compliance parameters
- Implemented heart/pump abstraction:
  - constant pump flow (`Q_ml_per_s`) from venous → arterial
  - deterministic, template-controlled (no auto-feedback yet)
- Integrated dynamics into step loop:
  - bed outflow drains arterial volume
  - pump refills arterial volume from venous compartment
  - volumes updated conservatively each step
- Added deterministic safety limiters:
  - flow scaling prevents negative volumes
  - proportional reduction preserves bed competition ratios
- Extended template contract (validated by schema):
  - `resolved_parameters.pump`
  - `resolved_parameters.compartments.{arterial,venous}`
  - optional `initial_state` volumes
- Expanded run summaries:
  - final arterial / venous volumes
  - final total blood volume (conservation check)
- Full pytest coverage:
  - strict volume conservation
  - schema enforcement for new required fields
  - DB cleanup preserves valid templates only
- Result:
  - time-varying pressures
  - stable, conservative physiology
  - outputs now meaningful to visualize

### Phase 5 — Posture, Vascular Tone, and Volume Modifiers ------------------------------------------------------------
**Done when:** physiologically intuitive stressors alter circulation without breaking determinism, conservation, or Phase 4.1 behavior.

- Extended the physiology layer using **pure parameter modifiers** only:
  - no new state variables
  - no feedback control loops
  - no randomness
- All Phase 5 behavior is applied via:
  - template normalization (load-time transforms), or
  - step-time parameter adjustment
- Neutral or disabled settings are **provably identical** to Phase 4.1.

---

**Added physiological controls (schema-validated, optional)**

**Global vascular tone**
- Added `resolved_parameters.vascular_tone_factor`
- Uniformly scales all bed resistances:
  - `R_eff = R * vascular_tone_factor`
- Models deterministic vasoconstriction / vasodilation.
- Neutral value (`1.0`) yields exact Phase 4.1 behavior.

**Hypovolemia / hypervolemia**
- Added `resolved_parameters.blood_volume_factor`
- Applied once at template normalization:
  - scales total blood volume
  - scales initial arterial and venous volumes
- No runtime drift or additional state introduced.
- Neutral value (`1.0`) produces identical Phase 4.1 dynamics.
- Changes correctly affect pressures and flows via existing compliance math.

**Posture (supine vs standing)**
- Added `resolved_parameters.posture ∈ {supine, standing}`
- Minimal, stable posture model:
  - standing increases venous unstressed volume (`V0_ven`)
  - reduces effective venous pressure (preload reduction)
- Implemented as a **parameter shift**, not a volume transfer.
- Supine posture is a strict no-op relative to Phase 4.1.

**Pooling bias gate (optional)**
- Added `resolved_parameters.pooling_bias_enabled`
- Optional per-bed parameter: `pooling_bias`
- When enabled *and* standing:
  - standing venous pooling magnitude is scaled based on mean bed bias
  - higher bias → stronger effective pooling
- Disabled by default.
- No per-bed volumes or additional compartments introduced.

---

#### Architectural guarantees preserved
- Deterministic replay:
  - same template + same run config → identical summary hash
- Strict volume conservation at all times
- Engine runner, DB schema, hashing, and orchestration unchanged
- Phase 4.1 behavior fully preserved under neutral settings

---

#### Test coverage
- Schema validation and default injection for all Phase 5 parameters
- Bounds checking for new knobs
- Hash equivalence:
  - implicit defaults vs explicit neutral values
- Deterministic replay under all Phase 5 configurations
- Proof that:
  - hypovolemia alters outputs
  - standing posture alters outputs
  - pooling bias affects standing behavior only when enabled
  - supine posture and disabled gates are exact regressions

**Result:**  
Phase 5 completes the non-reflexive physiological control layer, enabling posture, tone, volume loss, and pooling tendencies while maintaining full determinism, stability, and backward compatibility.
