# Coupling Mechanism Drift Inventory

> Solver Refactor Roadmap v3, Step 5. Created 2026-06-14.
> This document records the **two parallel coupling mechanisms** in the engine,
> their semantic differences, the drift between them, and the known dead routes
> / behavioral quirks. It is the prerequisite for any future "true unification".

## TL;DR

The engine has **two coupling mechanisms that are NOT two implementations of
the same thing** — they have different semantics, triggers, and coverage:

| | CONNECTIONS (`_unified_rhs`) | CouplingEngine (`resolve`) |
|---|---|---|
| **Path** | Radau only | Euler only |
| **Role** | Intra-step data flow (ODE integration loop) | Post-step rule engine |
| **Trigger** | Every RHS eval (many × per step via Newton) | Once per step (actually 2× — see below) |
| **What it routes** | module.derivatives() outputs → `_cached_inputs` | published signals → `fn_expr` rules → FactorCommands |
| **Strategy** | Gauss-Seidel semi-implicit (Newton converges it) | Explicit rule evaluation + first-order lag |
| **Source of truth** | `src/engine/topology.py` CONNECTIONS (hand-maintained) | `data/coupling_rules.json` (16 rules, 5 enabled) |
| **Module coverage** | 12 modules (heart/lung/kidney/fluid/gut/liver/endocrine/neuro/immune/coagulation/lymphatic + disease) | 6 modules publish signals (heart/lung/kidney/blood/fluid/liver) |

**They cannot be merged in one step** — merging would require either (a) folding
the RAAS-style rules into the implicit integration (changing Radau's Jacobian
structure) or (b) pulling the CONNECTIONS data flow out of the integration loop
(breaking the semi-implicit convergence). Roadmap D4: *"先用 twin-run 验证
当前行为，再动耦合"* — twin-run (Step 4) is now the safety net.

---

## Mechanism 1: CONNECTIONS (Radau path, intra-step)

**Code:** `src/engine/state_vector.py::unified_rhs` (Step C, ~L396-402)
**Table:** `src/engine/topology.py::CONNECTIONS` (34 entries)

### How it works
1. Each RHS eval calls every module's `derivatives(**inputs_from_cache)`.
2. Each module emits an `outputs` dict → collected into `all_outputs`.
3. CONNECTIONS routes `all_outputs[src][src_var] → _cached_inputs[tgt][tgt_var]`.
4. Next RHS eval (Newton sub-iteration or next step) reads those cached inputs.
5. The `if val is not None` guard silently skips entries whose source key is
   absent (the dead routes below).

### Gauss-Seidel ordering (intra-call direct hand-offs)
Modules are evaluated in fixed order: heart → lung → kidney → gut → liver →
endocrine → neuro → immune → coagulation → lymphatic → fluid. Within a single
RHS call, gut's outputs are passed **directly** to liver as `gut_state`
(`state_vector.py:325`), bypassing the cache. All other cross-module deps go
through `_cached_inputs` (one-iteration lag).

### Why this converges with Radau
Radau's Newton iteration calls RHS repeatedly; each call updates
`_cached_inputs`, so the inputs relax toward a fixed point. No explicit
coupling Jacobian is needed — the function-value iteration handles it. This is
the standard semi-implicit / Gauss-Seidel-on-the-coupling pattern.

---

## Mechanism 2: CouplingEngine (Euler path, post-step)

**Code:** `src/organs/coupling.py::CouplingEngine.resolve` + `src/engine/step_common.py::run_coupling` + `_publish_*_signals`
**Rules:** `data/coupling_rules.json` (16 rules total, **5 enabled**)

### How it works
1. `run_coupling(engine, dt, signal_time)` calls `_publish_<organ>_signals()`
   for heart/lung/kidney/blood/fluid/liver → fills each organ's OrganContext.
2. `coupling_engine.resolve(ctx, dt)` flattens all signals into `_signal_map`,
   iterates enabled rules in priority order, evaluates each rule's `fn_expr`
   (Python expression via `eval`), applies optional first-order lag, emits
   `_CouplingFactorCommand`s.
3. Commands applied via `engine.apply_factor(cmd)`.

### The 5 enabled rules (the ones that actually fire)
- `kidney_cv/raas_svr`: renin_activity → heart.SVR (multiply)
- `kidney_cv/raas_contractility`: angiotensin_II → heart.contractility (multiply)
- `kidney_cv/gfr_bun`: GFR → blood.BUN (multiply)
- `kidney_cv/map_gfr`: MAP → kidney.GFR (multiply)
- `pulmonary_cv/co2_ventilation`: arterial_PCO2 → lung.respiratory_rate (multiply)

The other 11 rules (blood_ph loop, liver_coag loop, cvp_renal) are
`enabled: false`.

---

## Coverage Drift (the core problem)

The two mechanisms cover **different** physiological relationships. Key gaps:

| Relationship | CONNECTIONS | CouplingEngine |
|---|---|---|
| heart.cardiac_output → kidney/lung/gut (perfusion) | ✅ `topology.py:42` | ❌ no rule |
| heart.MAP → kidney/fluid/neuro (map_input) | ✅ `topology.py:43` | ⚠️ partial (MAP→GFR only) |
| kidney.renin/angiotensin → heart.SVR/contractility (RAAS) | ❌ | ✅ enabled rules |
| kidney.GFR → blood.BUN | ❌ | ✅ enabled rule |
| blood.PCO2 → lung.respiratory_rate (chemoreflex) | ❌ | ✅ enabled rule |
| kidney.ADH/urine → fluid | ✅ `topology.py:63-64` | ❌ no rule |
| immune.cytokine → neuro/liver/coag/lymph | ✅ `topology.py:85` | ❌ (immune publishes no signal) |
| liver.* → blood.* (albumin, PT, fibrinogen, ALT) | ✅ `topology.py:99-101` | ⚠️ 4 rules exist but all disabled |
| endocrine/neuro/gut/lymphatic/coagulation as signal sources | ✅ in CONNECTIONS | ❌ these organs publish NO signals |

**Concrete divergence examples:**
- **RAAS feedback** (kidney → heart SVR/contractility): Euler has it (enabled
  rules), Radau does not. A hemorrhagic-shock scenario thus behaves
  differently between solvers — Radau's heart doesn't see the RAAS
  vasoconstriction that Euler's does.
- **CO perfusion** (heart → kidney/lung/gut): Radau has it (CONNECTIONS),
  Euler does not via CouplingEngine (CO reaches kidney in Euler through
  `kidney.compute(dt, MAP, CVP, CO)` direct arg passing in `_step_euler`, not
  through the rule engine — so it's covered, just by a third mechanism).

---

## CONNECTIONS Dead Routes

These entries have a `src_var` that the source module's `derivatives()` **never
emits**, so `all_outputs[src_mod].get(src_var)` returns `None` and the route is
silently skipped every call. They are **behaviorally inert today** (no effect
because they never fire), but they are misleading documentation of intent.

| src_var in CONNECTIONS | actual emit key | module:line |
|---|---|---|
| `("liver", "glucose_output")` | `glucose_output_g_min` | `liver.py:299` |
| `("gut", "portal_flow")` | `portal_blood_flow_mL_min` | `gut.py:151` |
| `("gut", "fat_absorption_active")` | `fat_absorption_g_min` | `gut.py:150` |
| `("neuro", "heart_rate_bpm")` | (not in derivatives outputs) | `neuro.py:143-150` |
| `("lung", "respiratory_rate")` | (only in compute(), not derivatives()) | `lung.py:197-210` |
| `("fluid", "V_vascular_mL")` | (not in outputs) | `fluid.py:228-235` |
| `("fluid", "V_isf_mL")` | (not in outputs) | `fluid.py:228-235` |

Additionally, **all routes targeting `blood`** are dead because `blood` is not
in `UNIFIED_MODULES` — its `derivatives()` is never called on the Radau path,
so `blood`-keyed cache entries are written but never consumed:
- `("lung", "arterial_PO2_mmHg") → [("blood", "arterial_PO2"), ...]`
- `("blood", "potassium_mEq_L") → [..., ("heart", "potassium_mEq_L")]` (also
  note `blood` is the *source* here, so this never fires at all)
- `("coagulation", "PT_sec") → [("blood", "PT_sec")]` etc.

**Not removed in Step 5** because removal would change Radau-path behavior, and
real `solve_ivp(Radau)` cannot be verified locally (hangs >5min/step on
Python 3.14 + scipy 1.17 — environment issue, baseline-confirmed). Left as
recorded debt for the future "true unification" step.

---

## Behavioral Quirk: Euler Double-Resolve (Step 4.95)

`src/simulation.py::_step_euler` calls `coupling_engine.resolve()` **twice**:

1. **Step 4.95** (`simulation.py:631`): runs BEFORE `run_post_dispatch`, so it
   resolves against the **previous step's** published signals (stale by one
   step).
2. **Step 8** (inside `run_post_dispatch → run_coupling`, `simulation.py:688`):
   runs AFTER publish, resolves against **current step's** fresh signals.

**Initial assumption (Step 5 plan):** the first resolve was a stale-signal bug
to remove. **Empirically disproven by twin-run harness:** removing Step 4.95
flips `blood_loss_severe` from PASS to FAIL (GFR max-rel-error 0.066 → 0.142).
The two resolves together form an **intentional 2-substep Gauss-Seidel-style
relaxation** that the Euler numerics depend on.

**Resolution:** Step 4.95 is kept; the misleading comment was corrected
(`simulation.py:629`) to document the 2-substep relaxation semantics and the
twin-run evidence. A future "true unification" should formalize this as a
single explicit substep loop rather than two ad-hoc resolve calls.

---

## Known Limitations

1. **H20 (Newton sub-iteration cache mutation):** `_cached_inputs` mutates
   across Radau's Newton sub-iterations within a single step. "Previous call's
   outputs" is therefore loosely defined. Currently acceptable — Radau's
   adaptive step size limits sub-iteration amplitude. Flagged in
   `docs/archive/audit_report_2026-06-04.md:415-425`.

2. **Euler signal-publish coverage gap:** only 6 of 12 modules publish signals.
   CouplingEngine rules therefore cannot express any coupling whose source is
   endocrine/neuro/immune/coagulation/gut/lymphatic. This is why most
   relationships live in CONNECTIONS instead.

3. **`_CouplingFactorCommand` vs `FactorCommand` type drift:**
   `coupling.py:242` constructs `_CouplingFactorCommand` (a frozen re-definition
   at L283) while type annotations say `FactorCommand`. Structurally identical,
   distinct types. The `_source` field exists only on the coupling variant.
   Cosmetic, not behavioral.

---

## Future "True Unification" Directions (out of scope for Step 5)

Three plausible directions, listed for the record (NOT implemented here):

1. **CONNECTIONS → derived from module INPUTS/OUTPUTS declarations.** This is
   the original Phase 5 plan (`topology.py::discover_topology` placeholder).
   Each module declares `INPUTS`/`OUTPUTS` class attrs; CONNECTIONS is
   auto-derived. Eliminates the dead-route drift mechanically. Does NOT merge
   the two mechanisms — just makes CONNECTIONS self-consistent.

2. **Fold RAAS-style rules into the implicit integration.** Express
   kidney→heart feedback as additional ODE state or as part of the derivatives
   coupling, so Radau sees it. Large change to Radau's effective system;
   requires a runnable Radau environment to validate.

3. **Unify on a single post-step rule engine for both paths.** Pull
   CONNECTIONS data flow out of the RHS, run coupling as an explicit post-step
   pass on both Euler and Radau. Breaks the semi-implicit convergence story;
   would need careful tolerance re-validation.

Any of these needs (a) a runnable Radau environment and (b) the twin-run
harness as the regression gate. Step 4 (harness) + this inventory are the
prerequisites.
