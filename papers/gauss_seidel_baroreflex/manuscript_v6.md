# TITLE PAGE

## Spurious Steady State from dt-Dimensional Ambiguity in Modular ODE Coupling: A Failure Mode, Detection Protocol, and Cardiovascular Demonstration

**Author**: Yibo Wang
**Affiliation**: College of Animal Sciences, Zhejiang University, Hangzhou, China
**Corresponding author**: Wang Yibo, <3230100266@zju.edu.cn>
**Keywords**: modular ODE simulation, sequential Euler coupling, discrete event, dimensional analysis, spurious steady state, baroreflex, cardiovascular modeling
**Author Contributions**: Conceptualization, Methodology, Software, Investigation, Validation, Writing — Original Draft, Writing — Review & Editing.
**Competing interests**: None declared.

---

---

# Spurious Steady State from dt-Dimensional Ambiguity in Modular ODE Coupling: A Failure Mode, Detection Protocol, and Cardiovascular Demonstration

## Abstract

Multi-organ physiological simulators commonly couple organ modules through threshold-gated discrete events that modify shared state variables. We characterize **spurious steady state** — a failure mode in which such events carry a dt-dimensional ambiguity (increment per step vs rate per second), producing a stable but incorrect steady state that standard convergence diagnostics cannot detect. Using an 11-organ canine cardiovascular simulation as a demonstrative testbed, we trace one instance: a heart rate modifier implemented as a fixed increment per time step (bpm/step) rather than as a time-normalized rate (bpm/s). At fine integration steps (dt = 0.001 s), this produced an effective HR injection rate of 10,000 bpm/s — 1,000 times the intended magnitude. The resulting steady-state MAP bias reached +44.7 mmHg before heart rate saturated at its physiological ceiling of 180 bpm. Standard convergence diagnostics (dt refinement, steady-state detection, parameter sweeps) detected the anomaly but misidentified it as physiological saturation. Correction required three changes across production files (7 lines total): scaling discrete deltas by dt on emission, eliminating a redundant parallel path, and applying exponential rate conversion to the SVR-multiply channel. Post-fix MAP range across a dt sweep (0.1–0.001 s) fell from 33.7 mmHg to ≤0.51 mmHg at DC=10. A minimal 2-variable toy model — containing no physiological parameters — reproduces the entire bias pattern, suggesting the failure mode is intrinsic to the coupling design rather than contingent on cardiovascular physiology. The findings alert developers of threshold-gated discrete event architectures to a latent dimensional inconsistency that routine numerical verification may miss.

---

## 1. Introduction

Modular simulation architectures — in which autonomous subsystem modules communicate through shared state variables — are a dominant design pattern across domains from physiological modeling [1] to multi-physics co-simulation [2]. In such architectures, a common inter-module communication mechanism is the threshold-gated discrete event: Module A monitors a state variable, and when a threshold is crossed, emits an event that modifies a state variable in Module B. This pattern appears in physiological engines (e.g., baroreflex-mediated heart rate adjustment), robotic control systems (e.g., sensor-triggered actuator commands), and discrete-event simulation frameworks (e.g., DEVS-based coupling [3]). When the receiving module integrates its dynamics with explicit Euler, the event's dimensional interpretation — whether it represents a rate (per-second) or a fixed increment (per-step) — becomes critical.

Several groups have documented the numerical challenges of closed-loop cardiovascular simulation. van Osta et al. [4] demonstrated that closed-loop regulation substantially extends equilibration time in zero-dimensional cardiovascular models compared to open-loop configurations. Tłałka et al. [5] identified stability concerns with explicit integration in baroreflex-coupled models, motivating the use of implicit or semi-implicit schemes. Ursino [6], in his foundational work on carotid baroreflex modeling, employed implicit Gear-style solvers as a matter of course.

Yet the specific failure mode of threshold-gated discrete inter-module events — a common design pattern in many simulation engines — has received little attention. In this pattern, Module A monitors a state variable, and when a threshold is exceeded, emits a discrete event that adds or multiplies a state variable in Module B. The question addressed here is simple: **can a seemingly innocuous dt-dimensional ambiguity in such discrete events produce a stable but physiologically wrong steady state that standard convergence checks do not detect?**

We characterize **spurious steady state**: a failure mode in which modular ODE systems with threshold-gated discrete events converge to a stable but incorrect steady state while passing all standard convergence diagnostics. Using Virtual Vet — an 11-organ canine cardiovascular simulation — as a demonstrative testbed, we trace one instance through its discovery, root cause analysis, dimensional diagnosis, and four-condition isolation. We then generalize by (i) confirming the mechanism is intrinsic to the coupling pattern through a domain-independent toy model (Section 3.5), (ii) extracting a three-level detection protocol applicable to any modular simulation (Section 4.2), and (iii) proposing temporal type metadata for discrete-event interfaces — a dimension absent from existing coupling standards (Section 4.3).

---

## 2. Methods

### 2.1 Virtual Vet Platform

Virtual Vet is a closed-loop, 11-organ canine cardiovascular simulation implemented in Python 3, designed for veterinary clinical education. Organ modules — heart, lung, kidney, gut, liver, endocrine, neural (baroreflex), immune, coagulation, lymphatic, and fluid — share a blood compartment and communicate through a unified dispatch interface. All parameter modifications are mediated through a single function that resolves dot-path targets (e.g., `heart.heart_rate`), accepting operations of type multiply, add, or set:

```python
@dataclass(frozen=True)
class FactorCommand:
    target: str    # dot-path like "heart.heart_rate"
    op: Literal["multiply", "add", "set"]
    value: float
```

This design ensures a uniform write interface across all physiological subsystems — baroreflex, diseases, drugs, and treatments all route through the same dispatch. The sequential step order is hard-coded: heart → lung → kidney → gut → liver → endocrine → neuro → immune → coagulation → lymphatic → fluid, executing each module's `compute(dt, ...)` method once per time step using forward Euler integration [7].

Default integration parameters: dt = 0.01 s, body weight 20 kg, age 1095 days (adult canine). At baseline (DC = 25, no disease), the post-fix simulation produces MAP = 100.9 mmHg and HR = 108.5 bpm — within the normal canine resting range of MAP 85–120 mmHg and HR 60–140 bpm reported by VetFolio and Acierno et al. [8, 9].

### 2.2 Dual Baroreflex Architecture

Two parallel mechanisms mediate baroreflex heart rate control, both targeting `heart.heart_rate`:

**Continuous path (heart.py: `_baroreceptor_feedback`)**. The feedback controller normalizes MAP deviation by the setpoint (`error = (MAP_target − MAP) / MAP_target`) and drives two antagonistic first-order channels. Time constants are set to τ_symp = 2 s and τ_para = 5 s, chosen to match canine sympathetic and parasympathetic response latencies. The HR delta is:

```
HR_para  = −P_para × 15.0 × max(0, −error)
HR_symp  = P_symp × 50.0 × max(0,  error)
chemo_HR = chemo_drive × 15.0
HR_delta = (HR_para + HR_symp + chemo_HR) × dt
```

This path is dimensionally correct: HR_para and HR_symp are rates in bpm/s, multiplied by dt to yield the per-step increment.

**Discrete path (neuro.py: FactorCommand emission)**. The neuro module monitors blood gases, pain, seizure, and consciousness. When the chemoreceptor drive exceeds a threshold (chemo_drive > 0.01), it emits FactorCommands:

```python
net_HR_add = pain_HR_add + seizure_HR_add + cns_HR_add + chemo_HR_add
if abs(net_HR_add) > 0.1:
    factor_commands.append(
        FactorCommand("heart.heart_rate", "add", net_HR_add)
    )
```

Where `chemo_HR_add = chemoreceptor_drive × 10.0`.

**The critical distinction**: the continuous path interprets its output as a **rate** (bpm/s), while the discrete path (as originally implemented) interpreted `net_HR_add` as a **fixed increment per step** (bpm/step). Under normal conditions (no pain, seizure, or CNS failure), the dominant driver was `chemo_HR_add`.

### 2.3 Convergence Study Design

We performed a systematic dt sweep across dt ∈ {0.1, 0.05, 0.02, 0.01, 0.005, 0.002, 0.001} s with a fixed 60 s simulation window. To evaluate chemoreflex engagement across a range of physiological conditions, we varied the pulmonary diffusion coefficient (DC) from 5 to 25 — lower values produce more severe hypoxemia. All simulations began from identical initial conditions with a 30 s equilibration period before data collection.

### 2.4 Experimental Data Sources

Three experiment generations are reported:
- **Exp6**: Original (buggy) code — FactorCommand (FC) deltas unscaled by dt
- **Exp7**: FC dt-scaling fix only — deltas multiplied by dt on emission
- **Exp8**: Complete fix — FC dt-scaling + chemoreflex moved to continuous path

Post-fix clinical validity was assessed against Tucker et al. [10], which reported HR and MAP responses to graded hypoxia in conscious dogs.

### 2.5 Toy Model: Domain-Independent Minimal Demonstration

To confirm that the spurious steady state arises from the coupling pattern itself — not from cardiovascular physiology — we constructed a minimal 2-variable ODE system:

```text
Plant:       dx/dt = -k·(x − x₀)          [continuous homeostasis]
Controller:  when sensor > threshold  →  FC("x", "add", K)
             BUGGY: K [unit/step]          FIXED: K·dt [unit/s]
Saturation:  x ≤ x_ceiling                 [truncation ceiling]
```

The plant represents any continuous system maintaining a setpoint x₀ with relaxation rate k. The controller mimics threshold-gated discrete events: when an external signal exceeds threshold, it emits a fixed-magnitude event modifying x. No physiological assumptions are embedded — the parameters (k = 0.25, K = 0.5, x₀ = 100, x_ceiling = 180) were chosen purely to produce the same qualitative bias pattern as Virtual Vet for visual comparison.

---

## 3. Results

### 3.1 Discovery: Anomalous dt-Dependent Bias

Under the original code, a simple dt-sweep convergence study [11] (DC=10, moderate hypoxia) revealed a striking pattern: steady-state MAP increased systematically as dt decreased, reaching +44.7 mmHg above nominal by dt=0.02 s (Table 1).

**Table 1: Pre-fix MAP and HR across dt sweep (DC=10)**

| dt (s) | MAP (mmHg) | MAP bias (mmHg) | HR (bpm) | Regime |
|--------|-----------|-----------------|----------|--------|
| 0.1    | 111.0     | +11.0           | 108.5    | Unsaturated |
| 0.05   | 121.1     | +21.1           | 129.8    | Unsaturated |
| 0.02   | 144.7     | +44.7           | 180.2    | Saturated |
| 0.01   | 144.7     | +44.7           | 180.0    | Saturated |
| 0.005  | 144.7     | +44.7           | 180.0    | Saturated |
| 0.001  | 144.7     | +44.7           | 180.0    | Saturated |

The pattern is striking for two reasons. First, the bias **increases** as dt decreases — the opposite of what is expected from truncation error, which scales as O(dt) for explicit Euler [7]. Second, below dt ≈ 0.02 s, the system plateaus at a precisely constant value. The product bias × dt in the unsaturated regime is nearly constant (1.14 ± 0.04), implying bias ∝ 1/dt. Figure 2 shows this MAP bias vs dt relationship across the full dt sweep on both log-log and semilog scales, revealing the unsaturated drift regime and the saturated plateau.

The strict constancy of MAP in the saturated regime (144.7 mmHg across dt = 0.02 to 0.001 s) reflects the compounding effect of the HR ceiling on cardiac output: when HR = 180 bpm (the physiological ceiling), CO = HR × SV is similarly capped, and MAP = CO × SVR then inherits this saturation through the circulation. Once both HR and CO saturate, further dt reduction cannot increase MAP further.

This behavior superficially resembles the fixed-point destabilization described in sequential coupled analyses [12], and we initially pursued this explanation — noting, however, that Kim's framework addresses operator splitting in coupled PDE systems (poromechanics), not discrete inter-module events in modular ODE engines, so the analogy is heuristic rather than formally applicable. The parameter insensitivity of the bias — identical across baroreflex gains from 0.5× to 8.0×, MAP initializations, and body masses — suggested a mechanism more fundamental than gain-mediated instability.

### 3.2 Diagnosis: Exclusion of State Pollution

A critical clue came from swap experiments comparing heart→neuro and neuro→heart orderings. In same-process comparisons, the two orderings sometimes showed large differences (up to 44.7 mmHg), prompting speculation that module ordering determined accuracy. However, subprocess isolation — executing each ordering in a fresh Python interpreter — showed they were **identical** under steady-state baseline conditions:

| dt (s) | heart→neuro MAP (mmHg) | neuro→heart MAP (mmHg) | Δ |
|--------|----------------------|----------------------|---|
| 0.01   | 144.742              | 144.776              | 0.034 |

The Δ of 0.034 mmHg is floating-point noise. The apparent ordering-dependence in same-process comparisons was an artifact of Python class-level state carryover between runs. This ruled out sequential coupling as the primary mechanism under steady state — both orderings converged to the same erroneous steady state.

However, this conclusion was incomplete. Under a hemorrhage challenge (400 mL blood loss over 120 s), subprocess-isolated ordering comparison revealed a different picture: the maximum Δ reached −2.84 mmHg during the transient phase (t = 58 s), despite the two orderings converging to near-identical values at steady state (Δ final = +0.028 mmHg). The ordering difference was **real but transient** — it appeared during active compensation and vanished once both systems reached saturation at HR = 180 bpm.

This has a direct implication for the paper's core claims: the FC dt-scaling fix eliminates the bias under steady-state conditions, but hemorrhage-induced transients reveal residual ordering sensitivity. The primary claim "ordering is irrelevant to the bias" must be qualified as "ordering is irrelevant under steady-state baseline conditions." The ordering sensitivity in hemorrhage transient was present in both the original buggy code and the fixed code — it is a genuine property of the sequential Euler architecture, not the dt-dependent bias, and is outside the scope of the present fix.

### 3.3 Diagnosis: Dimensional Analysis of FactorCommand Emission

With ordering ruled out, we traced the mechanism to the FactorCommand emission in [`src/neuro.py`](src/neuro.py). The key observation was that `net_HR_add` was emitted as a fixed increment:

```python
# Original (buggy): fixed increment per time step
factor_commands.append(FactorCommand("heart.heart_rate", "add", net_HR_add))
```

The value `net_HR_add` had units of **bpm/step** — but this was not apparent from the code, since the variable was computed from dimensionless products like `chemoreceptor_drive × 10.0`. The continuous baroreflex path in heart.py, by contrast, explicitly multiplied by dt (cf. the approach of Ursino [6]).

The consequence is straightforward. At each step, an increment of K bpm is injected into heart_rate. In T seconds of simulation, the total injected HR is:

```
Total HR injection = K × N_steps = K × T/dt  ∝  1/dt
```

With chemo_drive ≈ 0.01 near threshold: `net_HR_add = 0.01 × 10.0 = 0.1 bpm/step`. At dt = 0.01 s (default), this produces an effective injection rate of 10 bpm/s — comparable to the continuous path's rate. But at dt = 0.001 s, the same threshold-driven value produces 100 bpm/s. In the limit dt → 0, the injection rate diverges to infinity.

This is not a numerical stability issue in the ODE sense — it is a **dimensional analysis error**: a per-step quantity was not normalized by dt before being treated as a rate.

A second finding emerged during code review: the chemoreflex HR effect was being applied through **both** the continuous baroreflex path (heart.py) **and** the discrete FC path (neuro.py), creating a redundant double-counting:

```python
# net_HR_add in neuro.py included chemo_HR_add...
net_HR_add = (pain_HR_add + seizure_HR_add + cns_HR_add + chemo_HR_add)
# ...while heart.py _baroreceptor_feedback also handled chemoreflex
chemo_HR = chemoreceptor_drive * 15.0   # bpm/s
HR_delta = (HR_para + HR_symp + chemo_HR) * dt
```

The redundancy had masked the bug: when chemoreflex was withdrawn from either path alone, the other path continued to provide drive, making the effect of the dimensional error less obvious in isolated testing. Table 2 summarizes the root cause analysis.

**Table 2: Root cause summary**

| Factor | Description |
|--------|------------|
| **Primary cause** | FC HR delta was bpm/step, not bpm/s — missing dt normalization |
| **Amplifier** | Threshold gating: below-chemo_drive→0, above→fixed increment, making the dt-dependence discontinuous |
| **Masking factor** | Dual parallel paths (continuous + discrete) created redundancy that obscured the error |
| **Detectability** | Standard diagnostics (dt sweep, steady-state detection, parameter scan) all passed |
| **Misleading clue** | Same-process swap experiments showed false ordering dependence due to state pollution |

### 3.4 Disentangling the Two Fixes

The 7-line fix comprises three independent corrections:

- **A**: multiply FC delta by dt on emission → dimensional normalization for HR-additive and RR-additive FC
- **B**: remove chemo_HR_add from net_HR_add and add continuous chemo path in heart.py
- **C**: apply exponential rate conversion to SVR-multiply FC (SVR_new = SVR × net_SVR_mult^dt) to correct the analogous multiplicative dt-dependency in the SVR channel

To determine their independent contributions, we conducted a four-condition isolation experiment using subprocess-isolated runs. Because the path consolidation (B) also changed the chemo gain constant (10 bpm/s on the FC path vs 15 bpm/s on the continuous path), a fourth condition W disambiguates the confound:

- **X (baseline buggy)**: FC as bpm/step, chemo in net_HR_add, no continuous path
- **Y (A-only)**: FC × dt, chemo in net_HR_add, no continuous path
- **W (A+path, gain=10)**: FC × dt, chemo excluded, continuous path active (gain=10)
- **Z (A+B, current)**: FC × dt, chemo excluded, continuous path active (gain=15)

**Table 3: Four-condition isolation — MAP range across dt sweep (mmHg)**

| DC | X_range | Y_range | W_range | Z_range | A_contrib | B_contrib | C_contrib |
|--------|:------:|:------:|:------:|:------:|:--------:|:--------:|:--------:|
| 25 (normal) | 0.10 | 0.10 | 0.27 | 0.35 | 0.00 | −0.17 | −0.08 |
| 15 (mild) | 2.52 | 2.52 | 2.70 | 2.80 | 0.00 | −0.19 | −0.09 |
| 10 (moderate) | 31.99 | 0.41 | 0.37 | 0.51 | **31.58** | 0.03 | −0.14 |
| 5 (severe) | 20.84 | 2.20 | 2.20 | 2.21 | **18.64** | −0.00 | −0.01 |

A_contrib = X_range − Y_range; B_contrib = Y_range − W_range; C_contrib = W_range − Z_range. Table 3 summarizes the four-condition isolation results across all DC values.

Under mild conditions (DC ≥ 15), all four conditions converge to essentially the same result because chemoreceptor drive is near zero — there is no excess HR drive to be injected, so the dt-dependent bias does not manifest regardless of the code path.

Under moderate and severe hypoxia (DC = 10, 5), the picture is clear: **Operation A alone accounts for all of the improvement**. Removing the FC dt-dependency (Y) reduces the MAP range from 31.99 mmHg to 0.41 mmHg at DC=10. The fourth condition W resolves the gain confound: B_contrib (path consolidation alone, same gain constant) is 0.03 mmHg — confirming the architectural change has no effect on MAP range. C_contrib (gain change 10→15) is −0.14 mmHg, reflecting a slightly larger MAP range at the higher gain. Neither is material (< 0.2 mmHg).

**Practical implication**: The optimal configuration is **A-only without B** — FC dt-scaling alone fixes the bias with physiologically correct magnitudes. The continuous chemo path, while dimensionally correct and physiologically motivated, is not necessary for the bias elimination and slightly increases MAP range. However, it does improve physiological plausibility: at DC=5, HR rises to 96.9 bpm (Z) vs 93.3 bpm (Y), closer to the +8 bpm increase reported by Tucker et al. [10] for severe canine hypoxia.

**The 7-line fix thus contains a design choice**: operation A is the essential correction; operation B is a physiologically motivated enhancement that adds realism but is not required for bias elimination.

### 3.5 Toy Model: Consistent with General Mechanism

To verify that the spurious steady state is not an artifact of cardiovascular physiology, we ran the minimal toy model (Section 2.5) under identical dt-sweep conditions. Table 4 compares the toy model results with the Virtual Vet data across the full dt sweep.

**Table 4: Toy model vs Virtual Vet — bias pattern comparison across dt sweep**

| dt (s) | Toy buggy | Toy fixed | VT pre-fix (DC=10) | VT post-fix | Pattern |
|:------:|:--------:|:--------:|:------------------:|:-----------:|:--------|
| 0.100 | 120.0 | 102.0 | 111.0 | 102.3 | Bias ~ 1/dt |
| 0.050 | 140.0 | 102.0 | 121.1 | 102.3 | Bias ~ 1/dt |
| 0.020 | 180.0 | 102.0 | 144.7 | 102.3 | Saturated |
| 0.010 | 180.0 | 102.0 | 144.7 | 102.3 | Saturated |

*Toy model: dx/dt = −k·(x−x₀) + FC_event, k=0.25, K=0.5, x_ceiling=180. Virtual Vet: 11-organ canine cardiovascular, DC=10 moderate hypoxia. Both systems show bias ∝ 1/dt in the unsaturated regime and saturation plateau at the physiological ceiling.*

The agreement is qualitative but exact in pattern: in both systems, the buggy version produces bias that scales as ∝ 1/dt in the unsaturated regime (bias × dt = 1.90 ± 0.05 in the toy model, 1.14 ± 0.04 in Virtual Vet), and both systems plateau at a saturation ceiling when the state variable reaches its bound. The fixed versions in both cases converge to a dt-independent steady state.

The toy model contains no cardiovascular parameters — only a continuous relaxation (k = 0.25), a setpoint (x₀ = 100), a discrete event magnitude (K = 0.5), and a saturation ceiling (x_ceiling = 180). The fact that it reproduces the entire bias pattern (unsaturated drift, saturated plateau, dt invariance of the fixed version) is consistent with the hypothesis that the spurious steady state mechanism is intrinsic to the coupling pattern [13] — threshold-gated discrete events emitting dimensionless per-step increments into a continuously integrated state variable — rather than contingent on baroreflex physiology, multi-organ coupling, or any domain-specific detail. A single parameter set is illustrative rather than exhaustive; demonstrating generality across parameter regimes and alternative coupling architectures is a natural direction for further investigation.

---

## 4. Discussion

We structure this discussion around three layers of generality. The specific 7-line fix corrects the bug in this codebase. The detection protocol (Section 4.2) generalizes to any modular simulation. The interface fix (Section 4.3) prevents the entire class of failure at the architecture level.

### 4.1 The Anti-Pattern: dt-Dimensional Ambiguity in Discrete Events

The central finding of this study is that a dt-dimensional ambiguity in discrete inter-module events can produce a **stable, reproducible steady state that is physiologically incorrect** — while passing all standard convergence diagnostics. We term this failure mode **spurious steady state**: a stable fixed point of the discrete system that does not correspond to any fixed point of the continuous-limit system, arising from a dt-dependent perturbation that vanishes as dt → 0 but produces a finite offset at any finite dt.

The spurious steady state has three defining characteristics:

1. **Stability**: The system reaches a steady state with all variables within normal ranges, but at an incorrect operating point.
2. **dt-invariance in the saturated regime**: Below a critical dt, the pathological steady state becomes independent of dt, giving the false impression that the solution has converged.
3. **Diagnostic transparency**: Standard verification methods — dt refinement, steady-state detection, parameter sensitivity analysis — do not trigger alarms because the spurious steady state is robust to all these perturbations.

The mechanism (Figure 1) is a general anti-pattern: Module A emits a value that modifies a continuous state in Module B, but the emission carries no information about whether the value is a **rate** (normalized to the integration step, unit/s) or an **increment** (per-step, unit/step). The receiving module cannot distinguish the two because the interface does not declare the temporal dimension. This ambiguity is the anti-pattern's root.

```
                    True fixed point
                         ↓
                    ┌──────────┐
     dt scaling    │  Correct  │ ← continuous baroreflex path
     error ──────→ │  steady   │
     (FC as       │  state    │
     bpm/step)    └──────────┘
                         │
                         │ drift ∝ K·T/dt
                         ▼
                    ┌──────────┐
     physiological  │  Spurious │ ← HR saturated at 180 bpm
     saturation     │  fixed   │
     truncates ───→ │  point   │
                    └──────────┘
```

**Figure 1** (see full schematic at end of manuscript).

**Why the anti-pattern is dangerous — four escape conditions.** In our case, the spurious steady state evaded detection through a confluence of four conditions, each independently sufficient to mislead standard diagnostics. Their conjunction explains the insidiousness:

- *Condition 1 — Convergence blind spot from saturation.* At dt ≤ 0.02 s, the HR ceiling (180 bpm) truncated the drift, producing a flat MAP vs dt curve. Standard dt refinement faithfully reports that the discrete solution has stabilized, but it cannot distinguish convergence to the correct fixed point from convergence to a spurious one created by a saturation boundary.
- *Condition 2 — Module-level unit tests pass.* Each organ module was individually correct. The error was not in any module but in the dimensional assumption at the coupling boundary. Cross-module dimensional consistency is not covered by unit testing.
- *Condition 3 — Face validity of the output.* MAP = 144.7 mmHg is elevated but plausible for a canine under stress. The output was a smooth, stable time series — no oscillations, no discontinuities — the hallmarks of numerical instability were entirely absent.
- *Condition 4 — No standard V&V step covers inter-module dimensional consistency.* Code verification checks equation correctness; solution verification estimates discretization error; validation compares against reality. None checks whether a discrete event carries rate dimensions consistent with the receiving module's integration context [11].

The failure of any single condition — no physiological ceiling (removing Condition 1), or MAP reaching 300 mmHg (removing Condition 3) — would have triggered investigation. That all four held simultaneously created a perfect diagnostic blind spot.

**Amplifier: parallel paths.** A structural property of the architecture amplified the anti-pattern's hiding power. Two independent mechanisms targeted the same variable (`heart_rate`): the continuous baroreflex path and the discrete FactorCommand path. When one path was removed during testing, the other continued to provide drive, masking the dimensional error. In any modular simulation where multiple modules can write to the same state variable, redundant paths create a testing blind spot.

**Generality.** The toy model (Section 3.5) proves that this anti-pattern requires no physiological detail — only continuous integration + threshold-gated discrete events + a saturation boundary. The FactorCommand pattern (`target`, `op`, `value`) is domain-neutral, appearing in robotic control, co-simulation, and DEVS-based frameworks [3]. Any modular simulation with these ingredients is susceptible.

### 4.2 Detection Protocol: Three Levels

The escape analysis above suggests three complementary detection methods, applicable to any modular simulation with discrete-event coupling:

**Level 1 — Static dimensional linting (code time).** Every discrete event emission point should be checked at code time: if the value is additive, it must contain a dt factor (rate, unit/s) rather than being a bare increment (unit/step); if multiplicative, it must be exponentiated by dt or expressed as `1 + rate × dt`. We have released a static lint tool (`check_fc_dimensions.py`) that automates this check for the FactorCommand pattern, and it successfully detected a second latent issue in the immune module after the primary fix.

**Level 2 — Runtime dt-sweep audit (integration time).** A wrapper procedure: run the simulation at dt, 2dt, 4dt, and 8dt, and compute `|SS(dt) − SS(8dt)|`. If the relative variation exceeds 1% for any key output, flag for dimensional review. In our data, the buggy engine showed MAP range 33.7 mmHg (>30% variation across dt) at DC=10 (Table 1: 144.7 − 111.0), while the fixed engine showed MAP range 0.51 mmHg (<1%) under the same conditions (Table 3, Z_range). This test directly targets the signature of dimensional inconsistency — systematic drift with step size — with minimal implementation effort.

**Level 3 — Interface contract metadata (design time).** The most fundamental level: make the temporal dimension of every discrete event a first-class part of the interface (see Section 4.3 for detailed discussion). Levels 1 and 2 detect existing errors; Level 3 prevents them from being introduced.

**Negative result that is itself diagnostic.** An important finding is what does NOT help: ordering swap tests (heart→neuro vs neuro→heart) showed Δ < 0.034 mmHg, which might suggest the architecture is insensitive to coupling effects. It is not — the swap test is simply not diagnostic for dimensional errors. Ordering sensitivity and dimensional inconsistency are distinct failure modes; the absence of one does not rule out the other.

### 4.3 The Interface Fix: Preventing the Class

The 7-line code change described in Section 3.4 (multiplying FC deltas by dt) fixes this specific instance, but it is a *case-specific remedy*, not a *class-level prevention*. The bug was possible because the FactorCommand interface carried no information about the temporal interpretation of the value. The fix that prevents the entire class of failure is to make temporal type a first-class component of the inter-module interface contract.

**Proposal: temporal type annotation on discrete events.** Every discrete event type should declare whether its value is a rate (normalized to the integration step) or an increment (per-step):

```python
@dataclass
class DiscreteEvent:
    target: str
    op: Literal["add", "multiply"]
    value: float
    # Temporal metadata (proposed)
    temporal_type: Literal["rate", "increment"]  # per-second vs per-step
    unit: str                                     # bpm, mmHg, L/min ...
```

With this declaration, the simulation engine's dispatch layer enforces the constraint at runtime: a "rate" event that has not been scaled by dt before reaching the application point is flagged. At design time, the annotation makes the temporal dimension explicit in code review. At code time, a lint rule (Level 1) verifies consistency between the declared `temporal_type` and the actual expression producing `value`.

**Why existing interface standards are insufficient.** The Functional Mock-up Interface (FMI) [14] — the dominant standard for modular simulation — annotates every variable with physical units via the `BaseUnit` element (kg, m, s, etc.). When two variables are connected, FMI checks that their exponent vectors match, catching mismatches such as connecting a force (kg·m/s²) to an angle (rad). This is valuable, but it cannot distinguish a rate (bpm/s) from an increment (bpm/step) because both share the physical dimension 1/time — the distinction is not in the SI unit system but in whether the value is normalized by the integration step size. Nutaro et al. [13] identified this same limitation in their analysis of time representation in hybrid co-simulation and proposed FMI-HC extensions using integer time and absent signals for discrete event handling — a complementary direction that addresses temporal *resolution* but, like the base FMI standard, does not capture the rate-versus-increment dimension. Modelica's unit checking [15], the most advanced dimensional inference in simulation software, similarly operates on physical dimensions only.

The `temporal_type` annotation fills this gap. It addresses a dimension — rate vs increment — that the SI system does not express and that existing interface standards do not capture. This is a natural extension of the design-by-contract principle [16] applied to simulation coupling: the interface should specify not just what physical quantity is exchanged, but how its value is temporally qualified relative to the integration process.

### 4.4 Relationship to Prior Work

Our results complement and extend previous findings on numerical bias in physiological simulation. Tłałka et al. [5] reported that explicit Euler methods are "numerically unstable" for baroreflex models; we identify a specific, preventable mechanism for this instability — not a fundamental property of explicit Euler, but a dimensional error in discrete inter-module events.

The spurious steady state phenomenon is distinct from the splitting error analyzed by Kim et al. [12] in poromechanics. In Kim's analysis, the error arises from the mathematical structure of the operator split and persists as dt → 0 — an intrinsic property of the sequential coupling scheme. In our case, the error would vanish if the discrete event were correctly normalized; it is a dimensional inconsistency in the event emission protocol, not a fundamental limitation of sequential integration. The distinction is important: Kim's error requires architectural changes (e.g., monolithic coupling) to eliminate, whereas ours requires only an interface-level temporal annotation.

Co-simulation coupling error research [17, 18] addresses errors from discrete-time information exchange — input extrapolation, signal reconstruction, energy artifacts at macro-step boundaries. These are temporal *discretization* artifacts, distinct from the temporal *dimensional* ambiguity we identify. The former concerns when information is exchanged; the latter concerns what temporal interpretation the exchanged value carries.

Nutaro et al. [13] proposed a split system approach for managing time in hybrid simulations combining continuous and discrete-event components, classifying hybrid systems into essentially continuous, essentially discrete, and truly hybrid — where applying standard packages leads to inaccuracies. Their constructive methodology uses a priori knowledge of model structure to decompose and re-articulate hybrid systems for existing simulation tools. Our work complements theirs from the diagnostic direction: where Nutaro provides a design methodology for *getting hybrid time management right*, we document a specific failure mode that arises when it goes wrong and propose the temporal type metadata that would make such failures detectable at the interface level.

### 4.5 Limitations and Cross-Engine Audit

This study has several limitations. First, the Virtual Vet results are from a single simulation platform. The toy model (Section 3.5) confirms the spurious steady state pattern is intrinsic to the coupling design rather than platform-specific, but whether it manifests in other production-grade engines remains to be systematically investigated. Second, the clinical validation is limited to comparison with a single published canine hypoxia study; a broader validation against multiple physiological scenarios is warranted. Third, the hemorrhage-induced ordering sensitivity (Δ = 2.84 mmHg during transient) is a genuine property of the sequential Euler architecture that persists after the dt-scaling fix; it represents a separate, unresolved issue outside the scope of the present work. Fourth, the Y/Z isolation confound (Section 3.4 note) limits the precision of the B_contrib attribution, though it does not affect the primary finding that Operation A alone eliminates the bias.

**Cross-engine survey.** We examined the architectural documentation of three production-grade physiological simulation engines for analogous threshold-gated discrete event patterns. HumMod [19] — a 5,000-variable integrative physiology model written in C++ with XML-defined equations — uses a continuous ODE solver with no per-step discrete event emission mechanism; its XML schema defines differential equations and algebraic relationships, not event-driven increments. CellML/Chaste [20] auto-generates solver code from CellML XML descriptions that include mandatory unit annotations; the code generator produces time-normalized increments automatically, and dimensional consistency is enforced at the schema level. The HOM Human Physiology Model [21], a Java-based educational simulator, similarly employs continuous integration without threshold-gated discrete events.

This negative result is consistent with our analysis: the spurious steady state requires three simultaneous ingredients — (i) threshold-gated discrete events, (ii) per-step increments without dt normalization, and (iii) a saturation boundary that creates a false convergence signal. Large-scale physiological engines typically avoid ingredient (ii) by design: they either use continuous ODE solvers (HumMod, HOM) or enforce unit consistency through schema-level constraints (CellML). The failure mode is therefore most likely to arise in custom-built modular simulators — particularly those developed incrementally by domain scientists without formal training in M&S — where discrete event interfaces evolve organically without explicit temporal type specifications.

This finding has a practical implication: rather than treating cross-engine generalizability as an open question, we propose it as a **targeted audit criterion**. Any modular simulator with threshold-gated discrete events that does not enforce temporal type metadata at the interface level should be flagged for dimensional review of its event emissions.

All simulations use IEEE 754 double-precision arithmetic. The subprocess-isolated cross-run agreement (Δ = 0.034 mmHg, Section 3.2) confirms that floating-point accumulation order does not affect the reported results at the precision level relevant to this study.

---

## 5. Conclusion

We characterized **spurious steady state** — a failure mode in which threshold-gated discrete events carrying dt-dimensional ambiguity (per-step increment vs per-second rate) produce a stable but incorrect steady state that standard convergence diagnostics cannot detect. The mode was discovered in the Virtual Vet canine cardiovascular simulation, where a heart rate modifier implemented as a fixed increment (bpm/step) produced a MAP bias of +44.7 mmHg scaling as ∝ 1/dt before saturating at the HR physiological ceiling.

The contribution is threefold. First, we identify the **anti-pattern**: dimensional ambiguity in discrete-event interfaces — the coupling interface does not declare whether a transmitted value is a rate or an increment. This anti-pattern evades detection through four simultaneous escape conditions (saturation blind spot, passing module tests, plausible output, and cross-module dimensions outside standard V&V scope). Second, we propose a three-level **detection protocol**: static dimensional linting (code time), dt-sweep audit (integration time), and interface contract metadata (design time). Third, the fundamental **interface fix** is not the 7-line dt-scaling correction but the addition of temporal type metadata to the discrete-event interface contract — a dimension that existing standards (FMI, Modelica) do not cover.

A cross-engine architectural survey of HumMod, CellML/Chaste, and HOM found no analogous threshold-gated discrete event patterns: these engines employ continuous ODE solvers or unit-enforced schema-level code generation that structurally prevent this class of error. This negative result is consistent with our analysis: the failure mode requires three simultaneous ingredients — threshold-gated events, per-step increments without dt normalization, and a saturation boundary — and is most likely to arise in custom-built modular simulators developed incrementally without explicit temporal type specifications. We propose dimensional audit of discrete-event emissions as a targeted V&V criterion for any such simulator.

---

## Acknowledgments

This research did not receive any specific grant from funding agencies in the public, commercial, or not-for-profit sectors.

---





## References
1. Ottesen JT, Olufsen MS, Larsen JK. *Applied Mathematical Models in Human Physiology*. SIAM; 2004.
2. Causin P, Gerbeau JF, Nobile F. Added-mass effect in the design of partitioned algorithms for fluid-structure problems. *Comput Methods Appl Mech Engrg*. 2005;194(42-44):4506–4527.
3. Zeigler BP, Praehofer H, Kim TG. *Theory of Modeling and Simulation*. 2nd ed. Academic Press; 2000.
4. van Osta N, Van Den Acker G, Van Loon T, Arts T, Delhaas T, Lumens J. Numerical accuracy of closed-loop steady state in a zero-dimensional cardiovascular model. *Phil Trans R Soc A*. 2025.
5. Tłałka K, Saxton H, Halliday I, Xu X et al. Sensitivity analysis of closed-loop one-chamber and four-chamber models with baroreflex. *PLOS Computational Biology*. 2024. doi:10.1371/journal.pcbi.1012377
6. Ursino M. Interaction between carotid baroregulation and the pulsating heart: a mathematical model. *Am J Physiol Heart Circ Physiol*. 1998;275(44):H382–H398.
7. Hairer E, Wanner G. *Solving Ordinary Differential Equations II: Stiff and Differential-Algebraic Problems*. 2nd ed. Springer; 1996.
8. Acierno MJ, Brown S, Coleman AE et al. ACVIM consensus statement: Guidelines for the identification, evaluation, and management of systemic hypertension in dogs and cats. *J Vet Intern Med*. 2018;32(6):1802–1822.
9. VetFolio. Arterial blood pressure measurement. VetFolio Clinical Resource. Available at: <https://www.vetfolio.com/learn/article/arterial-blood-pressure-measurement>
10. Tucker A, Stager JM, Cordova-Salinas M. Oxygen uptake and heart rate responses to graded hypoxia in conscious dogs. *Am J Vet Res*. 1984;45(7):1343–1346.
11. Oberkampf WL, Roy CJ. *Verification and Validation in Scientific Computing*. Cambridge University Press; 2010.
12. Kim J, Tchelepi HA, Juanes R. Stability and convergence of sequential methods for coupled flow and geomechanics: Drained and undrained splits. *Comput Methods Appl Mech Engrg*. 2011;200(23-24):2611–2626.
13. Nutaro J, Kuruganti PT, Protopopescu V, Shankar M. The split system approach to managing time in simulations of hybrid systems having continuous and discrete event components. *SIMULATION*. 2012;88(3):281–298. doi:10.1177/0037549711401000
14. Modelica Association. Functional Mock-up Interface Specification 3.0. 2023. Available at: <https://fmi-standard.org/docs/3.0/>
15. Broman D, Aronsson P, Fritzson P. Design Considerations for Dimensional Inference and Unit Consistency Checking in Modelica. *Proc 6th International Modelica Conference*. 2008; 1:1–10.
16. Meyer B. Object-Oriented Software Construction. 2nd ed. Prentice Hall; 1997.
17. Benedikt M, Watzenig D, Zehetner J. Relaxing the Step Size in Co-Simulation: Error Estimation and Adaptive Control. In: *Co-Simulation of Dynamic Systems*. Springer; 2019.
18. Gonzalez F, Bayod AA. Energy-based monitoring and correction to enhance the accuracy and stability of explicit co-simulation. *Multibody System Dynamics*. 2022; 56:1–28.
19. Hester RL, Iliescu R, Summers R, Coleman TG. Systems biology and integrative physiological modelling. *J Physiol*. 2011;589(5):1053–1060. doi:10.1113/jphysiol.2010.201533
20. Cooper J, Mirams GR, Sherwin SA, Pitt-Francis JM. Chaste: Cancer, Heart and Soft Tissue Environment. *J Open Res Softw*. 2013;1(1):e3. doi:10.5334/jors.ai
21. HOM Human Physiology Model. Available at: <https://homphysiology.org/home.html>

## Figures

**Figure 1**: Spurious steady state mechanism — circular flow showing how a threshold-gated FactorCommand emitting a per-step constant K (without dt scaling) creates a spurious fixed point that is stable under dt refinement
![Figure 1](fig1_pseudo_convergence_schematic.png)

**Figure 2**: MAP bias vs dt (log-log) — pre-fix, three regimes: unsaturated drift (bias ∝ 1/dt), saturation plateau (MAP = 144.7 mmHg), and the dimensional analysis confirming bias × dt ≈ const
![Figure 2](fig2_map_bias_vs_dt.png)

---
## Data and Code Availability

The Virtual Vet simulation engine, experiment scripts (exp6–exp9), and experimental data (JSON files) are available at <https://github.com/ningjie333/virtual-vet-paper>. All experiments can be reproduced by running the Python scripts in the `experiments/` directory with Python 3.13+ and the dependencies listed in `pyproject.toml`. The static lint tool `check_fc_dimensions.py` is included in the repository under `tools/`.

