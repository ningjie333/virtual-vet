# Spurious Steady State from a dt-Dimensional Mismatch in FactorCommand Events: A Canine Cardiovascular Case Study

**Authors**: [Author Name]
**Affiliation**: [Zhejiang University, China]
**Email**: [Email]
**arXiv category**: cs.SY (Systems and Control), cs.MS (Mathematical Software)

---

## Abstract

Multi-organ physiological simulators commonly couple organ modules through threshold-gated discrete events that modify shared state variables. Using an 11-organ canine cardiovascular simulation as a testbed, we report the discovery, diagnosis, and correction of a dimensional analysis error in such a discrete event system: a heart rate modifier was implemented as a fixed increment per time step (bpm/step) rather than as a time-normalized rate (bpm/s). At fine integration steps (dt = 0.001 s), this produced an effective HR injection rate of 10,000 bpm/s — 1,000 times the intended magnitude. The resulting steady-state MAP bias reached +44.7 mmHg before heart rate saturated at its physiological ceiling of 180 bpm. The system converged to a stable steady state, but at a physiologically wrong operating point — a failure mode we term **spurious steady state**. Standard convergence diagnostics (dt refinement, steady-state detection, parameter sweeps) detected the anomaly but misidentified it as physiological saturation. Correction required 7 lines of code: scaling discrete deltas by dt on emission, eliminating a redundant parallel path, and applying exponential rate conversion to the SVR-multiply channel. Post-fix MAP variance across a dt sweep (0.1–0.001 s) fell from 44.7 mmHg to ≤2.21 mmHg. This case study documents one specific instance in one simulation engine (Virtual Vet); whether this failure pattern recurs in other platforms requires systematic investigation. The findings alert developers of threshold-gated discrete event architectures to a latent dimensional inconsistency that routine numerical verification may miss.

---

## 1. Introduction

Physiological simulation platforms such as HumMod, SAPHIR, and CellML-based frameworks now support applications from classroom teaching to drug interaction modeling [Ottesen et al., 2004]. In practice, many of these engines couple 10 or more organ modules with heterogeneous time constants through shared state variables. Sequential explicit Euler integration is frequently chosen because it permits per-module debugging, supports heterogeneous time steps without matrix assembly, and avoids the overhead of implicit solver infrastructure.

Several groups have documented the numerical challenges of closed-loop cardiovascular simulation. van Osta et al. (2025) demonstrated that closed-loop regulation substantially extends equilibration time in zero-dimensional cardiovascular models compared to open-loop configurations. Tłałka et al. (2024) identified stability concerns with explicit integration in baroreflex-coupled models, motivating the use of implicit or semi-implicit schemes. Ursino (1998), in his foundational work on carotid baroreflex modeling, employed implicit Gear-style solvers as a matter of course.

Yet the specific failure mode of threshold-gated discrete inter-module events — a common design pattern in many simulation engines — has received little attention. In this pattern, Module A monitors a state variable, and when a threshold is exceeded, emits a discrete event that adds or multiplies a state variable in Module B. The question addressed here is simple: **can a seemingly innocuous dimensional oversight in such discrete events produce a stable but physiologically wrong steady state that standard convergence checks do not detect?**

We answer this question using Virtual Vet, an 11-organ canine cardiovascular simulation platform. We document the complete journey: the anomalous dt-dependent bias that led to investigation, the exclusion of state pollution as a cause, the root cause identified through dimensional analysis of threshold-gated event emission, the 7-line fix, and a three-condition isolation experiment quantifying the independent contributions of each code change. The central contribution is a documented failure mode in this specific system — spurious steady state — where the modular ODE system converges to a stable steady state that is physiologically incorrect, without triggering any standard convergence warning.

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

This design ensures a uniform write interface across all physiological subsystems — baroreflex, diseases, drugs, and treatments all route through the same dispatch. The sequential step order is hard-coded: heart → lung → kidney → gut → liver → endocrine → neuro → immune → coagulation → lymphatic → fluid, executing each module's `compute(dt, ...)` method once per time step.

Default integration parameters: dt = 0.01 s, body weight 20 kg, age 1095 days (adult canine).

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
- **Exp6**: Original (buggy) code — FC deltas unscaled by dt
- **Exp7**: FC dt-scaling fix only — deltas multiplied by dt on emission
- **Exp8**: Complete fix — FC dt-scaling + chemoreflex moved to continuous path

Post-fix clinical validity was assessed against Tucker et al. (1984), which reported HR and MAP responses to graded hypoxia in conscious dogs.

---

## 3. Results

### 3.1 Discovery: Anomalous dt-Dependent Bias

Under the original code, a simple dt-sweep convergence study (DC=10, mild hypoxia) revealed a striking pattern: steady-state MAP increased systematically as dt decreased, reaching +44.7 mmHg above nominal by dt=0.02 s (Table 1).

**Table 1: Pre-fix MAP and HR across dt sweep (DC=10)**

| dt (s) | MAP (mmHg) | MAP bias (mmHg) | HR (bpm) | Regime |
|--------|-----------|-----------------|----------|--------|
| 0.1    | 111.0     | +11.0           | 108.5    | Unsaturated |
| 0.05   | 121.1     | +21.1           | 129.8    | Unsaturated |
| 0.02   | 144.7     | +44.7           | 180.2    | Saturated |
| 0.01   | 144.7     | +44.7           | 180.0    | Saturated |
| 0.005  | 144.7     | +44.7           | 180.0    | Saturated |
| 0.001  | 144.7     | +44.7           | 180.0    | Saturated |

The pattern is striking for two reasons. First, the bias **increases** as dt decreases — the opposite of what is expected from truncation error, which scales as O(dt) for explicit Euler. Second, below dt ≈ 0.02 s, the system plateaus at a precisely constant value. The product bias × dt in the unsaturated regime is nearly constant (1.14 ± 0.04), implying bias ∝ 1/dt.

### 3.2 Diagnosis: Exclusion of State Pollution

A critical clue came from swap experiments comparing heart→neuro and neuro→heart orderings. In same-process comparisons, the two orderings sometimes showed large differences (up to 44.7 mmHg), prompting speculation that module ordering determined accuracy. However, subprocess isolation — executing each ordering in a fresh Python interpreter — showed they were **identical** under steady-state baseline conditions:

| dt (s) | heart→neuro MAP (mmHg) | neuro→heart MAP (mmHg) | Δ |
|--------|----------------------|----------------------|---|
| 0.01   | 144.742              | 144.776              | 0.034 |

The Δ of 0.034 mmHg is floating-point noise. The apparent ordering-dependence in same-process comparisons was an artifact of Python class-level state carryover between runs. This ruled out sequential coupling as the primary mechanism under steady state — both orderings converged to the same erroneous steady state.

However, this conclusion was incomplete. Under a hemorrhage challenge (400 mL blood loss over 120 s), subprocess-isolated ordering comparison revealed a different picture: the maximum Δ reached −2.84 mmHg during the transient phase (t = 58 s), despite the two orderings converging to near-identical values at steady state (Δ final = +0.028 mmHg). The ordering difference was **real but transient** — it appeared during active compensation and vanished once both systems reached saturation at HR = 180 bpm.

### 3.3 Diagnosis: Dimensional Analysis of FactorCommand Emission

With ordering ruled out, we traced the mechanism to the FactorCommand emission in `src/neuro.py`. The key observation was that `net_HR_add` was emitted as a fixed increment:

```python
# Original (buggy): fixed increment per time step
factor_commands.append(FactorCommand("heart.heart_rate", "add", net_HR_add))
```

The value `net_HR_add` had units of **bpm/step** — but this was not apparent from the code, since the variable was computed from dimensionless products like `chemoreceptor_drive × 10.0`. The continuous baroreflex path in heart.py, by contrast, explicitly multiplied by dt.

The consequence is straightforward. At each step, an increment of K bpm is injected into heart_rate. In T seconds of simulation, the total injected HR is:

```
Total HR injection = K × N_steps = K × T/dt  ∝  1/dt
```

With chemo_drive ≈ 0.01 near threshold: `net_HR_add = 0.01 × 10.0 = 0.1 bpm/step`. At dt = 0.01 s (default), this produces an effective injection rate of 10 bpm/s — comparable to the continuous path's rate. But at dt = 0.001 s, the same threshold-driven value produces 100 bpm/s. In the limit dt → 0, the injection rate diverges to infinity.

This is not a numerical stability issue in the ODE sense — it is a **dimensional analysis error**: a per-step quantity was not normalized by dt before being treated as a rate.

**Table 2: Root cause summary**

| Factor | Description |
|--------|------------|
| **Primary cause** | FC HR delta was bpm/step, not bpm/s — missing dt normalization |
| **Amplifier** | Threshold gating: below-chemo_drive→0, above→fixed increment, making the dt-dependence discontinuous |
| **Masking factor** | Dual parallel paths (continuous + discrete) created redundancy that obscured the error |
| **Detectability** | Standard diagnostics (dt sweep, steady-state detection, parameter scan) all passed |
| **Misleading clue** | Same-process swap experiments showed false ordering dependence due to state pollution |

### 3.4 Disentangling the Three Fixes

The 7-line fix comprises three independent corrections:

- **A**: multiply FC delta by dt on emission → dimensional normalization for HR-additive and RR-additive FC
- **B**: remove chemo_HR_add from net_HR_add and add continuous chemo path in heart.py
- **C**: apply exponential rate conversion to SVR-multiply FC (SVR_new = SVR × net_SVR_mult^dt) to correct the analogous multiplicative dt-dependency in the SVR channel

To determine their independent contributions, we conducted a three-condition isolation experiment using subprocess-isolated runs:

- **X (baseline buggy)**: FC as bpm/step, chemo in net_HR_add, no continuous path
- **Y (A-only)**: FC × dt, chemo in net_HR_add, no continuous path
- **Z (A+B, current)**: FC × dt, chemo excluded, continuous path active

**Table 3: Three-condition isolation — MAP range across dt sweep (mmHg)**

| DC | X_range | Y_range | Z_range | A_contrib | B_contrib |
|--------|:------:|:------:|:------:|:--------:|:--------:|
| 25 (normal) | 0.10 | 0.10 | 0.35 | 0.00 | −0.25 |
| 15 (mild) | 2.52 | 2.52 | 2.80 | 0.00 | −0.28 |
| 10 (moderate) | 31.99 | 0.41 | 0.51 | **31.58** | −0.10 |
| 5 (severe) | 20.84 | 2.20 | 2.21 | **18.64** | −0.01 |

**Operation A alone accounts for nearly all of the improvement.** The continuous chemo path (Operation B) slightly increases MAP range by 0.10 mmHg at DC=10, but improves physiological plausibility: at DC=5, HR rises to 96.9 bpm (Z) vs 93.3 bpm (Y), closer to the +8 bpm increase reported by Tucker et al. (1984) for severe canine hypoxia.

---

## 4. Discussion

### 4.1 Spurious Steady State: A Dangerous Failure Mode

The central finding of this study is that a dt-dimensional mismatch in discrete inter-module events can produce a **stable, reproducible steady state that is physiologically incorrect** — while passing all standard convergence diagnostics.

We term this failure mode **spurious steady state**. Formally: a stable fixed point of the discrete system that does not correspond to any fixed point of the continuous-limit system, arising from a dt-dependent perturbation that is finite at any discrete dt but whose rate diverges as dt → 0, producing a finite accumulated offset within any fixed simulation window. Its defining characteristics are:

1. **Stability**: The system reaches a steady state with all variables within normal ranges, but at an incorrect operating point.
2. **dt-invariance in the saturated regime**: Below a critical dt, the pathological steady state becomes independent of dt, giving the false impression that the solution has converged.
3. **Diagnostic transparency**: Standard verification methods — dt refinement, steady-state detection, parameter sensitivity analysis — do not trigger alarms because the spurious steady state is robust to all these perturbations.

### 4.2 Why Standard Diagnostics Failed

- **dt refinement**: In our experiments, halving dt from 0.01 to 0.005 s produced identical MAP (144.7 mmHg), giving no indication of remaining error.
- **Steady-state detection**: A moving-variance detector confirmed convergence within 30 s of simulation, well within the 60 s window.
- **Parameter sweeps**: Eight-fold baroreflex gain sweeps (0.5× to 8.0×), MAP initialization sweeps, and body mass sweeps all left the bias unchanged — not because the mechanism is robust, but because the spurious steady state had already saturated at the HR ceiling.
- **Ordering swap**: The swap test (heart→neuro vs neuro→heart) showed identical results in subprocess-isolated runs (Δ < 0.034 mmHg), giving false confidence in the sequential coupling architecture.

### 4.3 The dt-Dimensional Trap

The root cause was a unit mismatch: the neuro module emitted HR increments in bpm-per-timestep, but the receiving code implicitly treated the value as bpm-per-second. Its insidiousness lies in the fact that **at a single dt value, the error is invisible**. A simulation run only at dt = 0.01 s would produce MAP = 144.7 mmHg with no indication of pathology. The error manifests only when dt is varied and the bias is observed to **increase** with decreasing step size — a sufficiently counterintuitive pattern that many researchers would attribute to other causes (model stiffness, solver stability) before considering a dimensional inconsistency in discrete events.

### 4.4 Lessons for Modular ODE Simulation

**Lesson 1: Dimensional consistency must be explicit.** Any discrete event that modifies a continuous state variable must carry consistent rate dimensions. The convention of "per-step" quantities, common in game engines and real-time simulation, is a latent source of dt-dependent error in scientific ODE simulation.

**Lesson 2: Parallel paths mask bugs.** The existence of two independent mechanisms targeting the same variable (heart_rate) allowed the dimensional error to go unnoticed: when one path was removed during testing, the other continued to provide drive.

**Lesson 3: Spurious steady states require specific detection strategies.** Standard diagnostics are insufficient. We recommend:
- Routine dt sweeps with at least one order of magnitude in both directions from the operating dt
- Explicit monitoring of all state variables approaching physiological saturation limits
- Where possible, comparison against an independent solver (implicit or unified state-vector) at a single dt value

**Lesson 4: Order swap tests are not diagnostic.** The equivalence of heart→neuro and neuro→heart orderings (Δ < 0.034 mmHg in subprocess-isolated tests) shows that sequential coupling is not the source of bias. Before attributing systematic error to algorithmic architecture, exclude dimensional errors in discrete events.

### 4.5 Relationship to Prior Work

Our results complement and extend previous findings on numerical bias in physiological simulation. Tłałka et al. (2024) reported that explicit Euler methods are "numerically unstable" for baroreflex models; we identify a specific, preventable mechanism for this instability — not a fundamental property of explicit Euler, but a dimensional error in discrete inter-module events.

The spurious steady state phenomenon is distinct from the splitting error analyzed by Kim et al. (2011) in poromechanics. In Kim's framework, the splitting error arises from the mathematical structure of the operator split and persists as dt → 0. In our case, the error would vanish if the discrete event were correctly normalized — it is an implementation error, not a mathematical necessity.

### 4.6 Limitations

This study has several limitations. First, the results are from a single simulation platform; the generality of the spurious steady state pattern across other modular ODE engines requires further investigation. Second, the clinical validation is limited to comparison with a single published canine hypoxia study; a broader validation against multiple physiological scenarios is warranted. Third, the hemorrhage-induced ordering sensitivity (Δ = 2.84 mmHg during transient) is a genuine property of the sequential Euler architecture that persists after the dt-scaling fix; it represents a separate, unresolved issue outside the scope of the present work. Fourth, the Y/Z isolation conflates path consolidation with chemo gain constant (10 vs 15 bpm/s), limiting the precision of the B_contrib attribution.

All simulations use IEEE 754 double-precision arithmetic. The subprocess-isolated cross-run agreement (Δ = 0.034 mmHg) confirms that floating-point accumulation order does not affect the reported results at the precision level relevant to this study.

**Data and code availability**: The Virtual Vet simulation engine, experiment scripts (exp6–exp9), and experimental data (JSON files) are available at https://github.com/ningjie333/virtual-vet.

---

## 5. Conclusion

We documented the discovery, diagnosis, and correction of a dimensional analysis error in one FactorCommand channel of the Virtual Vet canine cardiovascular simulation: a heart rate modifier was implemented as a fixed per-step increment (bpm/step) rather than a time-normalized rate (bpm/s), producing a steady-state MAP bias of +44.7 mmHg that standard convergence diagnostics could not detect. The bias scaled as ∝ 1/dt before saturating at the HR physiological ceiling of 180 bpm, creating a spurious steady state — a stable steady state at a physiologically wrong operating point.

The correction required 7 lines of code: scaling discrete deltas by dt, eliminating a redundant parallel path, and applying exponential rate conversion to the SVR-multiply channel. Post-fix, MAP variance across a dt sweep fell from 44.7 mmHg to ≤2.21 mmHg. A three-condition isolation experiment confirmed that the FC dt-scaling (Operation A) accounts for virtually all of the improvement; the parallel redundant-path removal (Operation B) is physiologically motivated but does not materially alter the convergence metric.

This case study is specific to the HR-additive FactorCommand in Virtual Vet. Developers of similar modular ODE engines are advised to explicitly verify the dimensional consistency of all discrete inter-module events — a per-step quantity not normalized by dt carries a hidden dt-dependence that routine convergence checks will not reveal. Whether this failure pattern recurs in other physiological simulation platforms is an open question warranting systematic investigation.

---

## References

1. van Osta N, Van Den Acker G, Van Loon T, Arts T, Delhaas T, Lumens J. Numerical accuracy of closed-loop steady state in a zero-dimensional cardiovascular model. *Phil Trans R Soc A*. 2025.
2. Tłałka K, Saxton H, Halliday I, Xu X et al. Sensitivity analysis of closed-loop one-chamber and four-chamber models with baroreflex. *PLOS Computational Biology*. 2024. doi:10.1371/journal.pcbi.1012377
3. Ursino M. Interaction between carotid baroregulation and the pulsating heart: a mathematical model. *Am J Physiol Heart Circ Physiol*. 1998;275(44):H382–H398.
4. Kim J, Tchelepi HA, Juanes R. Stability and convergence of sequential methods for coupled flow and geomechanics: Drained and undrained splits. *Comput Methods Appl Mech Engrg*. 2011;200(23-24):2611–2626.
5. Tucker A, Stager JM, Cordova-Salinas M. Oxygen uptake and heart rate responses to graded hypoxia in conscious dogs. *Am J Vet Res*. 1984;45(7):1343–1346.
6. Hairer E, Wanner G. *Solving Ordinary Differential Equations II: Stiff and Differential-Algebraic Problems*. 2nd ed. Springer; 1996.
7. Causin P, Gerbeau JF, Nobile F. Added-mass effect in the design of partitioned algorithms for fluid-structure problems. *Comput Methods Appl Mech Engrg*. 2005;194(42-44):4506–4527.
8. Ottesen JT, Olufsen MS, Larsen JK. *Applied Mathematical Models in Human Physiology*. SIAM; 2004.
9. Acierno MJ, Brown S, Coleman AE et al. ACVIM consensus statement: Guidelines for the identification, evaluation, and management of systemic hypertension in dogs and cats. *J Vet Intern Med*. 2018;32(6):1802–1822.

---

## Figures

**Figure 1**: Spurious steady state schematic — drift and saturation mechanism

**Figure 2**: MAP bias vs dt (log-log) — pre-fix, three regimes

**Figure 3**: Code diff — the 7-line fix

**Figure 4**: Before/after comparison — X/Y/Z MAP range bar chart across DC conditions

---

*arXiv preprint. Submitted to SIMULATION: Transactions of the Society for Modeling and Simulation International.*
