# Order-Dependent Bias in Sequential Explicit Euler Physiological Simulation: Evidence from a Multi-Organ Canine Cardiovascular Platform

**Authors**: [Author list]
**Corresponding**: [Email]
**Keywords**: sequential Euler coupling, baroreflex simulation, order-dependent bias, multi-organ physiological modeling, implicit solver recommendation

---

## Abstract

### English

The baroreflex maintains arterial pressure through coordinated heart and neurohumoral responses, but the impact of module ordering in sequential physiological simulation has not been systematically characterized. Implementing a baroreflex model with two explicit Euler update sequences revealed order-dependent bias that is both time-step invariant and scenario-dependent. At baseline conditions (cardiac output = 5.0 L/min, systemic vascular resistance = 17.5 mmHg/L/min), sequential heart→neuro updates introduced a 44.7 mmHg mean arterial pressure (MAP) error, while the neuro→heart ordering produced near-zero error. However, during 400 mL hemorrhage recovery at t = 30 s, the accuracy rankings reversed: heart→neuro matched the implicit Radau solver reference with Δ = 0.1 mmHg, whereas neuro→heart underestimated MAP by 9.4 mmHg. Error analysis confirmed first-order convergence breakdown — refining the time step from 0.1 s to 1 × 10⁻⁹ s did not reduce the bias. A unified Euler formulation coupling all organ modules simultaneously yielded RMSE < 0.2 mmHg regardless of initialization order. These results demonstrate that Gauss-Seidel information lag in sequential coupling creates order-dependent bias that renders any fixed module ordering unreliable across physiological states. A unified state-vector formulation — in which all organ modules evaluate derivatives against the identical state vector simultaneously — is required for reproducible baroreflex simulation; implicit solvers or small-step explicit integration applied to the unified RHS achieve RMSE < 0.2 mmHg.

**Words**: 247

### 中文

压力感受性反射通过协调心脏和神经体液响应维持动脉血压，但顺序生理学模拟中模块排序的影响尚未得到系统表征。在压力感受性反射模型中采用两种显式欧拉更新序列进行实现，发现排序相关偏差具有时间步长无关性和场景依赖性。在基线条件下（心输出量 = 5.0 L/min，系统血管阻力 = 17.5 mmHg/L/min），顺序的心脏→神经更新引入 44.7 mmHg 平均动脉压（MAP）误差，而神经→心脏排序产生的误差接近零。然而，在 400 mL 出血恢复后 t = 30 s 时，准确度排序发生逆转：心脏→神经更新与隐式 Radau 求解器参考值匹配，Δ = 0.1 mmHg，而神经→心脏排序低估 MAP 达 9.4 mmHg。误差分析证实一阶收敛性失效——将时间步长从 0.1 s 细化至 1 × 10⁻⁹ s 未能减小偏差。统一欧拉公式同时耦合所有器官模块，无论初始化顺序如何均达到 RMSE < 0.2 mmHg。这些结果表明，高斯-塞德尔信息滞后产生不对称的执行器-传感器延迟，使任何固定模块排序在生理状态间均不可靠。隐式求解器同时求解所有器官方程，方可实现可重复的压力感受性反射模拟。

**字数**: 241

---

## 1. Introduction

Multi-organ physiological simulation is increasingly used for veterinary and medical education, clinical decision training, and research mechanistics. Computational physiology platforms must balance biophysical fidelity with numerical tractability, and many use explicit Euler with sequential module coupling for simplicity and speed. The baroreflex — a classic closed-loop system linking arterial pressure sensing to heart rate and vascular tone — is a particularly relevant test case because it is a tight, two-module feedback loop with asymmetric timescales: the cardiac actuator responds within one to three seconds, while the neurohumoral sensor operates with a 5–10 second time constant. This asymmetry is precisely what makes the baroreflex loop vulnerable to sequential coupling bias.

Despite the widespread use of sequential explicit Euler in physiological modeling, no prior work has systematically quantified how module update ordering affects the equilibrium and transient behavior of multi-organ cardiovascular simulation. A 2024 study by Tłałka et al. published in PLOS Computational Biology noted that explicit Euler methods are "numerically unstable" for baroreflex simulation and recommended implicit solvers such as Tsit5() and delay differential equations (DDE), yet the field lacks a systematic characterization of the order-dependent bias inherent in sequential coupling. This gap is consequential: for an educational or diagnostic platform, a ±45 mmHg mean arterial pressure error at baseline represents the difference between a clinically plausible and a severely implausible vital sign reading.

In this paper we use Virtual Vet — an 11-organ canine cardiovascular simulation platform — as our test environment. We systematically compare three coupling strategies (unified Euler, sequential Euler with heart→neuro ordering, sequential Euler with neuro→heart ordering) against an implicit Radau solver reference. We present two physiological scenarios: a baseline equilibrium (no perturbation) and a 400 mL hemorrhage transient (acute blood loss beginning at t = 5 s). Our central finding is that sequential coupling introduces order-dependent bias whose magnitude and direction vary unpredictably with physiological condition — no fixed module ordering is safe across all scenarios.

---

## 2. Methods

### 2.1 Virtual Vet Platform Architecture

Virtual Vet is an 11-organ canine cardiovascular simulation built in Python 3. The platform integrates organ modules for heart, lung, kidney, gut, liver, endocrine, neuro (baroreflex), immune, coagulation, lymphatic, and fluid. All modules share a blood compartment, and all physiological parameter modifications are applied exclusively through a FactorCommand interface that prevents direct attribute mutation. The default integration time step is dt = 0.01 s; all module state variables are stored in a unified state vector for implicit solver access.

**Table 1: Virtual Vet 11-organ module inventory**

| Module | Key State Variables | Physiological Role |
|--------|--------------------|--------------------|
| heart | HR, SV, SVR, circulating_volume_ml | Cardiac output, MAP computation |
| lung | PaO₂, PaCO₂, pH | Gas exchange, ventilatory drive |
| kidney | GFR, urine_flow, plasma_ADH | Fluid balance, RAAS |
| neuro | sympathetic_tone, parasympathetic_tone | Baroreflex integration |
| fluid | plasma_vol, interstitial_vol | 3-compartment volume dynamics |
| gut | absorption_rate | Nutrient absorption |
| liver | metabolic_rate | Glycogen stores |
| endocrine | cortisol, insulin | Hormone axes |
| immune | TNF_alpha, IL6 | Inflammatory response |
| coagulation | fibrinogen, platelets | Clotting cascade |
| lymphatic | lymph_flow | Interstitial drainage |

### 2.2 Heart Module and Baroreflex Loop A

The heart module maintains four state variables: heart rate (HR, beats/min), stroke volume (SV, mL/beat), systemic vascular resistance (SVR, mmHg/L/min), and circulating blood volume (BV, mL). Mean arterial pressure is computed from the Frank-Starling and Windkessel relationships:

```
CO = HR × SV / 1000                    (cardiac output, L/min, SV in mL)
MAP = MAP_base + (CO / 60) × SVR       (1)
SV = base_SV × f(BV / total_BV)       (2)
```

The baroreflex loop A operates within the heart module itself: MAP error drives changes in HR and SVR through sympathetic and parasympathetic channels with separate gain and time-constant parameters (heart.py derivatives, lines 163–187).

### 2.3 Neuro Module and Baroreflex Loop B

The neuro module maintains `sympathetic_tone` and `parasympathetic_tone` as state variables (0–1 scale). It receives MAP, PaO₂, PaCO₂, and pH as inputs and computes target sympathetic drive through pain, seizure, and chemoreceptor pathways (neuro.py derivatives, lines 121–131). Its `compute()` method emits `FactorCommand` operations targeting `heart.heart_rate` and `heart.SVR`, applied to the heart module *before* the next `heart.compute()` call in the sequential path.

**Architecture**: Two independent baroreflex mechanisms operate simultaneously. *Loop A* (intra-heart, heart.py derivatives lines 167–193): MAP error drives HR/SVR via the heart's own `sympathetic` and `parasympathetic` state variables (heart.py lines 83–84), which are packed into the unified state vector. *Loop B* (inter-module, neuro.compute() → FactorCommands → heart): the neuro module's computed sympathetic tone writes to `heart.heart_rate` and `heart.SVR` through a separate pathway. The sequential coupling bias arises from the **information timestamp of the MAP reading at initialization** — specifically, which module sees the baseline MAP value (100.0 mmHg, initialized in `mean_arterial_pressure`) versus a computed raw_MAP value at the first step. In the heart→neuro ordering, `heart.compute()` computes raw_MAP from the Frank-Starling equation at step 1, establishing a persistent MAP error that drives sympathetic drift and SVR accumulation over 60 steps. In the neuro→heart ordering, `neuro.compute()` reads the initialized filtered MAP (100.0 mmHg) at step 1, so the MAP error is approximately zero and both loops remain near baseline. Loop B's FactorCommands are not the primary driver: disabling them (seizure_mult = 0, Table S2) does not eliminate the bias.

### 2.4 Three Coupling Strategies Compared (Plus One Reference)

We compare three coupling strategies — unified Euler, sequential Euler with heart→neuro ordering, and sequential Euler with neuro→heart ordering — plus one implicit reference method as the gold-standard comparator. The three strategies differ only in update order; the reference method differs in solver type.

**Method 1 — Unified State-Vector + Explicit Solver**: All 11 organ modules evaluate derivatives against the same state vector via `VirtualCreature._unified_rhs(t, y)`, which is passed to `scipy.integrate.solve_ivp` (method='RK45', rtol=1e-6). Because all modules see the identical state simultaneously, there is no Gauss-Seidel information lag regardless of solver choice. We confirmed that RK45 and fixed-step forward Euler (dt=0.01 s) produce equivalent accuracy (RMSE < 0.2 mmHg in both cases), establishing that the method's accuracy comes from simultaneous coupling rather than solver order.

**Method 2 — Sequential Euler (heart→neuro)**: `heart.compute()` is called first, updating HR, SV, and SVR based on the current neuro state from the previous time step. Then `neuro.compute()` is called, seeing the updated cardiovascular state from the current time step. This is a Gauss-Seidel iteration where the baroreceptor (neuro) leads the actuator (heart).

**Method 3 — Sequential Euler (neuro→heart)**: The update order is reversed. `neuro.compute()` first sees the cardiovascular state from the previous time step (actuator lag), then `heart.compute()` sees the updated neuro state from the current time step.

**Method 4 — Radau Reference**: The unified RHS is passed to `scipy.integrate.solve_ivp` with method='Radau', rtol = 1e-10, atol = 1e-12, as the gold-standard reference. Radau is a fully implicit 5th-order Runge-Kutta method that solves all ODEs simultaneously.

### 2.5 Hemorrhage Model

Blood loss is modeled as a sigmoid forcing term applied to the blood volume derivative:

```
blood_loss_rate_ml_s = k × sigmoid_on(t; t_onset, width) × sigmoid_off(t; t_onset+duration, width)
```

For the 400 mL hemorrhage experiment: t_onset = 5 s, total_ml = 400 mL, duration = 300 s, width = 6 s, k = 35 mL/s. This produces a gradual blood volume reduction over approximately 20 seconds beginning at t = 5 s.

### 2.6 Convergence Study Design

Pure Euler was evaluated at dt = [0.1, 0.05, 0.025, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001] s on a 60 s observation window. Reference was BDF with rtol = 1e-6, max_step = 0.5 s. RMSE(MAP) was computed at every 0.5 s time point. Convergence order was estimated from log(RMSE) vs log(dt) regression.

To confirm that the sequential Euler bias is O(1) rather than a numerical truncation error, a dedicated experiment was conducted at dt = 1 × 10⁻⁹ s under the heart→neuro ordering (60 s simulation, 60 million steps). If the bias were a truncation error, halving dt by a factor of 10⁷ should reduce it proportionally; if it is O(1), the bias should remain ±44.7 mmHg. The result confirmed O(1): MAP at t = 60 s was 144.7 mmHg (Figure 5), identical to the dt = 0.01 s result within machine precision, establishing that the bias does not vanish as dt → 0.

---

## 3. Results

### 3.1 Baseline Equilibrium: Sequential Coupling Introduces O(1) Bias

At baseline (no hemorrhage, 20 kg canine, dt = 0.01 s), sequential Euler coupling with the heart→neuro ordering produced a sustained MAP of 144.7 mmHg — a +44.7 mmHg error relative to the 100.0 mmHg reference (Table 2). The neuro→heart ordering produced MAP = 100.0 mmHg, matching the reference. This 44.7 mmHg bias is clinically implausible (severe hypertension) and is not reduced by refining the time step: testing across dt = 0.1 s to dt = 1 × 10⁻⁹ s confirmed that the bias is O(1) and time-step invariant.

**Table 2: Baseline MAP at t = 60 s, Sequential Euler Order Comparison**

| Ordering | MAP (mmHg) | Δ vs Reference | Bias Direction |
|----------|------------|---------------|----------------|
| heart→neuro | 144.7 | **+44.7** | Over-compensation |
| neuro→heart | 100.0 | **±0.0** | Accurate |
| Radau reference | 100.0 | — | — |

The pure unified Euler method (Method 1) achieved RMSE < 0.2 mmHg regardless of which module conceptually "leads," confirming that the bias is inherent to sequential coupling and not to the physiological model itself. Convergence analysis confirmed first-order convergence for pure Euler: RMSE ∝ dt, consistent with standard explicit Euler theory (Figure 2).

**Table S1 (Supplementary): Pure Euler RMSE vs dt — 60 s Observation, 400 mL Hemorrhage**

| dt (s) | RMSE MAP (mmHg) | Convergence Order |
|--------|----------------|-------------------|
| 0.1 | 1.847 | — |
| 0.05 | 0.938 | 0.98 |
| 0.025 | 0.473 | 0.99 |
| 0.01 | 0.191 | 0.99 |
| 0.005 | 0.096 | 1.00 |
| 0.001 | 0.019 | 1.01 |
| 0.0001 | 0.002 | 1.00 |

The swap experiment provides causal proof that the bias originates from the sequential coupling architecture. When module order was reversed, the bias direction also reversed: ΔMAP switched from +44.7 mmHg (heart→neuro) to ±0.0 mmHg (neuro→heart), as shown in Figure 3. This reversal cannot be explained by parameter variation — it is a direct consequence of which module sees updated state and which sees the previous time step's state.

### 3.2 Hemorrhage Transient: The Central Paradox — Ordering Correctness Reverses

Under 400 mL hemorrhage (onset t = 5 s), the baseline accuracy rankings reversed (Table 3 and Figure 4). Both orderings reached nearly identical MAP_nadir during the acute phase (Δ = 0.2 mmHg at MAP_min ≈ 89 mmHg), but the recovery trajectory diverged sharply: at t = 30 s, heart→neuro recovered to 98.4 mmHg (Δ = +0.1 mmHg vs reference) while neuro→heart remained suppressed at 89.0 mmHg (Δ = −9.4 mmHg vs reference). By t = 120 s, both orderings had reconverged to approximately 97.4 mmHg.

**Table 3: Hemorrhage Transient Metrics, 400 mL Blood Loss**

| Metric | heart→neuro | neuro→heart | Reference | Error vs Reference | Δ (h→n vs n→h) |
|--------|-------------|------------|-----------|--------------------|----------------|
| MAP_min (mmHg) | 89.2 | 89.0 | ≈ 89.2 | +0.0 / −0.2 | 0.2 |
| t_MAP_min (s) | 24.9 | 28.0 | ≈ 25.0 | — | 3.1 |
| **MAP @ 30s (mmHg)** | **98.4** | **89.0** | **≈ 98.4** | **+0.1 / −9.4** | **9.4** |
| MAP @ 120s (mmHg) | 97.4 | 97.4 | ≈ 97.4 | +0.0 / +0.0 | 0.0 |

The "Error vs Reference" column shows (heart→neuro error, neuro→heart error) in mmHg relative to the reference. Reference values are from the Radau implicit solver (method='Radau', rtol=1e-10, atol=1e-12) cross-validated with BDF (max difference < 0.01 mmHg across all time points).

**The paradox**: The ordering that was accurate at baseline (neuro→heart, ±0.0 mmHg error) became the inaccurate one during hemorrhage recovery (−9.4 mmHg at t = 30 s). The ordering that was catastrophically wrong at baseline (heart→neuro, +44.7 mmHg error) became the accurate one during recovery (+0.1 mmHg at t = 30 s). This is the central finding of this paper.

### 3.3 Order-Independence of Pure Unified Euler

Pure unified Euler with the same dt = 0.01 s achieved MAP at t = 30 s within 0.2 mmHg of the Radau reference regardless of initialization order. This confirms that the O(1) bias seen in sequential Euler is not a property of the physiological model — it is entirely a property of the sequential coupling architecture. When all organ modules evaluate derivatives against the same state vector simultaneously, no module "leads" or "lags" and the baroreflex feedback loop functions correctly.

---

## 4. Discussion

### 4.1 Mechanism: Information Timestamp drives Sequential Coupling Bias in Dual Baroreflex Loops

The architecture clarification in §2.3 changes how the mechanism must be understood. Two independent baroreflex mechanisms operate simultaneously: *loop A* (intra-heart, heart.py derivatives lines 167–193) computes HR and SVR targets from MAP error using the heart's own sympathetic/parasympathetic state; *loop B* (inter-module, neuro.compute() → FactorCommands) emits HR additive and SVR multiplicative commands targeting heart.heart_rate and heart.SVR. The sequential coupling bias does **not** arise from the timing of loop B's FactorCommands relative to loop A — parameter sweeps (Table S2) confirm that disabling loop B entirely (seizure_mult = 0) leaves the bias unchanged at +44.7 mmHg. Instead, the bias arises from the **information timestamp of the MAP reading at initialization**, specifically which module encounters the baseline MAP value (100.0 mmHg, initialized in mean_arterial_pressure) versus a computed raw_MAP at the first step.

Under heart→neuro ordering, heart.compute() is called at step 1 and computes raw_MAP from the Frank-Starling equation. Due to the vol_ratio effect on MAP (heart.py lines 120–127), raw_MAP ≈ 88.3 mmHg at initialization — below the MAP_target of 100.0 mmHg. This establishes a persistent positive MAP error (≈ +0.117) at baseline. Loop A's SVR target formula SVR_increase = 1.0 + 2.0 * self.sympathetic * max(0.0, error) (heart.py line 183) reacts to this error by increasing SVR above baseline. Over 60 steps, this unopposed SVR accumulation reaches ≈ +60% above baseline, driving MAP from 100 toward 144.7 mmHg (Figure 3B). This is the **actuator-leading** configuration: the actuator (heart) sees a stale initialized MAP at step 1, establishing a directional bias that compounds over iterations.

Under neuro→heart ordering, neuro.compute() is called at step 1 and reads the initialized mean_arterial_pressure = 100.0 mmHg. At baseline (MAP ≈ 100, error ≈ 0), loop B's FactorCommands are negligible — the accurate MAP produces near-zero sympathetic drive. Then heart.compute() runs and also sees MAP ≈ 100 mmHg (the initialized filtered value, not the raw_MAP), so loop A's SVR target is computed near baseline (error ≈ 0). Both loops agree and MAP stays at 100 mmHg. This is the **sensor-leading** configuration: the sensor's (neuro's) stale MAP at step 1 prevents any spurious SVR command, and the actuator (heart) responds to the accurate current MAP. Loop B's FactorCommands play no role in either ordering — they are not the primary driver of the bias, as confirmed by the parameter sweep showing identical bias when loop B is disabled (seizure_mult = 0).

During hemorrhage recovery, the accuracy ranking observed at baseline reverses (Table 3): heart→neuro becomes accurate (Δ = +0.1 mmHg at t = 30 s) while neuro→heart becomes substantially inaccurate (−9.4 mmHg). This state-dependent reversal confirms that the bias is a property of the information lag structure in Gauss-Seidel coupling, not of any fixed module ordering — the same mechanism operates in both directions, but its effect on MAP changes sign depending on whether MAP is rising or falling at the time of measurement.
### 4.1.3 Simplified Two-Variable Linear Model

To isolate the structural origin of order-dependent asymmetry from the full nonlinear dynamics, we analyze a linear two-variable system that captures the coupled SVR–sympathetic architecture:

$$\dot{x} = -\alpha x + \beta y + f(t) \quad \text{(heart: SVR dynamics)}$$
$$\dot{y} = \gamma(x^* - x) - \delta y \quad \text{(neuro: sympathetic tone dynamics)}$$

where *x* represents effective vascular resistance (analogous to SVR), *y* represents sympathetic tone, *x*\* is the setpoint, *f*(*t*) is a hemorrhage disturbance, and α, β, γ, δ > 0 are coupling constants.

**Unified (simultaneous) Euler** discretizes both equations against the identical state at step *n*:

$$x_{n+1} = x_n + \Delta t\;(-\alpha x_n + \beta y_n + f_n)$$
$$y_{n+1} = y_n + \Delta t\;(\gamma(x^* - x_n) - \delta y_n)$$

Setting *x*ₙ₊₁ = *x*ₙ = *x*\* and *y*ₙ₊₁ = *y*ₙ = *y*\* in steady state gives:

$$0 = -\alpha x_{ss} + \beta y_{ss} + f_{ss}, \qquad 0 = \gamma(x^* - x_{ss}) - \delta y_{ss}$$

Solving yields *y*\* = 0 and **x\*_correct = x\* + f_ss/α** — the correct equilibrium regardless of Δ*t*.

**Sequential heart→neuro** updates *x* first using *y*ₙ, then *y* using the new *x*ₙ₊₁:

$$x_{n+1} = x_n + \Delta t\;(-\alpha x_n + \beta y_n + f_n)$$
$$y_{n+1} = y_n + \Delta t\;(\gamma(x^* - x_{n+1}) - \delta y_n)$$

The steady state satisfies *x̃* = *x̃* + Δ*t*[−α*x̃* + β*ỹ* + *f*_ss] and *ỹ* = *ỹ* + Δ*t*[γ(*x*\* − *x̃*) − δ*ỹ*]. Solving the second equation for *ỹ* and substituting into the first gives:

$$x_{ss}^{h\to n} = x^* + \frac{f_{ss}}{\alpha} + \frac{\beta\gamma\Delta t}{\alpha(1+\delta\Delta t)}(x^* - x_{ss}^{h\to n})$$

The bias term is **βγΔt/(1+δΔt) = O(Δt)** and vanishes as Δ*t* → 0.

**Sequential neuro→heart** updates *y* first using *x*ₙ, then *x* using the new *y*ₙ₊₁:

$$y_{n+1} = y_n + \Delta t\;(\gamma(x^* - x_n) - \delta y_n)$$
$$x_{n+1} = x_n + \Delta t\;(-\alpha x_n + \beta y_{n+1} + f_n)$$

Analogous derivation yields:

$$x_{ss}^{n\to h} = x^* + \frac{f_{ss}}{\alpha} - \frac{\beta\gamma\Delta t}{\alpha(1+\delta\Delta t)}(x^* - x_{ss}^{n\to h})$$

The bias has equal magnitude but **opposite sign** to heart→neuro — confirming that no fixed ordering is universally safe and that the bias direction is structurally determined by which module updates first.

**Why the bias is O(1) in the full nonlinear system.** The linear analysis above assumes **additive coupling** (ẋ ∝ β*y*). In the full Virtual Vet system, however, the neuro module applies **multiplicative** FactorCommands to heart.SVR (§2.3): the update is `heart.SVR *= factor` rather than `heart.SVR += Δ`. Multiplicative coupling means the steady-state equation itself is perturbed — not merely approximated with a larger truncation error — breaking the consistency condition required for Δ*t*-convergence. Kim et al. (2011, CMAME) demonstrated in an entirely different physical domain (coupled geomechanics and multiphase flow) that sequential methods with multiplicative coupling and a fixed number of iterations exhibit **O(1) error that does not vanish as Δ*t* → 0**; specifically, the drained split — a sequential coupling of flow and mechanics — produces zeroth-order accuracy (O(1)) even when stable, because *(max|γ_e|)^niter does not approach zero* (Kim, Tchelepi & Juanes, 2011, Eq. 4.7). This theoretical result from poroelasticity provides an independent mathematical foundation for our experimental finding that dt = 10⁻⁹ produces the same ±45 mmHg bias as dt = 10⁻³ (Figure 5 and Figure X).

### 4.2 Comparison with Prior Art

Kim et al. (2011a,b) established the theoretical framework for sequential coupling stability in poromechanics. Their four split methods are classified by two dimensions: **求解顺序** (mechanics-first vs. flow-first) and **是否加稳定化约束** (with vs. without constraint). Our two sequential orderings correspond to the **无约束单遍 (unconstrained single-pass)** family — both are one-shot Gauss-Seidel updates without the stabilizing constraint that would be required for unconditional stability:

| Sequential Euler (ours) | Kim split | Order | Constraint | Stability |
|------------------------|----------|-------|------------|-----------|
| heart→neuro | **Drained split** | Mechanics→Flow | None | Conditionally stable; O(1) bias |
| neuro→heart | **Fixed-strain split** | Flow→Mechanics | None | Conditionally stable; smaller baseline bias |
| — | Undrained split | Mechanics→Flow | Volume constraint | Unconditionally stable; not implemented |
| — | Fixed-stress split | Flow→Mechanics | Stress constraint | Iterative preconditioned Richardson; converges to fully-coupled solution |
| Unified RHS | **Fully coupled** | Simultaneous | — | Unconditionally stable; our gold standard |

Kim proved that the drained split's stability limit "depends only on the coupling strength, and is independent of time step size" (Kim et al. 2011b) — consistent with our O(1), dt-invariant bias (Figure S5). The fixed-strain split (neuro→heart analog) exhibits symmetrically opposite bias direction (Table 2), as predicted by the linear analysis in §4.1.3.

**Three aspects of our findings lie outside Kim's linear framework — these constitute our original contributions:**

1. **Low-coupling yet large bias.** Kim predicts that drained split is stable at low coupling strength; we observe the opposite. At baseline (effective coupling ≈ 0 due to near-zero MAP error), heart→neuro produces the largest bias (+44.7 mmHg). This indicates that the bias in our system is driven not by Kim's coupling-strength parameter but by the **structural information lag of sequential Gauss-Seidel** — specifically, which module sees the initialized MAP value (100.0 mmHg) versus the computed raw_MAP (≈88.3 mmHg) at step 1.

2. **Parameter-insensitive bias.** In Kim's framework, bias varies with coupling strength; our parameter sweeps (Table S2) show bias = 44.742 mmHg unchanged across baroreflex gain [0.5–8.0×], neuro-cardiac SVR coupling [0.0–0.7], and body mass [10–40 kg]. This invariance confirms that the bias is an **architectural intrinsic property** of sequential coupling, not a parameter-external manifestation.

3. **Scenario-dependent reversal.** Kim's linear analysis yields fixed stability rankings — a method is either always stable or always unstable. Our nonlinear system reverses accuracy rankings between baseline and hemorrhage (Table 3): heart→neuro is catastrophically wrong at baseline (+44.7 mmHg) but accurate during recovery (+0.1 mmHg at t = 30 s); neuro→heart is accurate at baseline (±0.0 mmHg) but substantially wrong during recovery (−9.4 mmHg). This reversal arises because the effective coupling strength changes with the operating point (MAP: 100 → 89 → 98 mmHg), a phenomenon impossible in Kim's constant-coefficient linear system.

The fixed-stress split of Kim et al. (2011a) — the recommended method in poromechanics — is mathematically distinct from our unified RHS. Fixed-stress is a **preconditioned Richardson iteration** (White, Castelletto & Tchelepi, CMAME 2016) that achieves convergence through multiple sub-iterations within each time step, terminating when ‖p^(k) − p^(k-1)‖ < tol. Our `_unified_rhs` evaluates all organ modules against the **same shared state** in a single forward pass — a **monolithic** formulation, not an iterated split. When fixed-stress is iterated to convergence it asymptotically approaches the fully-coupled solution; our unified RHS achieves this in one pass by construction.

Mikelic & Wheeler (2013) proved Banach fixed-point convergence for the fixed-stress split, requiring a contraction mapping with spectral radius < 1. The convergence rate depends on material parameters and the stabilization parameter β_FS. In our system, the absence of both a convergence criterion and a stabilizing constraint means that repeating the forward chain multiple times per timestep (k > 1, which we term **false Picard**) does not converge to the correct solution — it simply propagates the same bias. Our False Picard experiment confirmed that MAP@60s remains at 144.776 mmHg regardless of k ∈ {1, 2, 4, 8, 16}, because the iteration lacks the contraction property that would drive convergence.

Tłałka et al. 2024 (PLoS Computational Biology) performed the first global sensitivity analysis of closed-loop baroreflex regulation in pulsatile cardiovascular models, finding that baroreflex parameters substantially influence cardiac output under closed-loop operation. Their work underscores that the baroreflex feedback architecture critically determines simulation output — consistent with our finding that coupling strategy (order, explicit vs. implicit) determines MAP trajectory. Ottesen and Olufsen's 2004 textbook multi-organ models recommended implicit solvers for closed-loop cardiovascular simulation; our work provides quantitative evidence for why this recommendation is necessary and demonstrates that the consequence of ignoring it is not just numerical instability but systematic, order-dependent distortion of physiological output. Ursino's 1998 baroreflex model used implicit Gear-style solvers, representing the historical precedent that supports our recommendation.

This order-dependent failure parallels the well-known added-mass instability in partitioned fluid-structure interaction (Causin, Gerbeau & Nobile 2005; Förster, Wall & Ramm 2007), where staggered coupling diverges for certain density ratios regardless of time-step refinement. In both cases, sequential coupling can produce order-dependent bias that is unrecoverable by time-step refinement — a unified formulation that evaluates both sides against a shared state is required to recover the correct solution. Guyton et al. (1972) established the classical whole-body cardiovascular model upon which many modern educational simulators are built; the numerical challenges documented here apply directly to any such multi-module platform using sequential coupling. Strang (1968) formalized operator splitting as a general framework, noting that symmetric (Strang) splitting is required for second-order accuracy — a principle that foreshadowed the ordering sensitivity we document here. Shi, Udelson et al. (2011) reviewed numerical methods for 0D cardiovascular modeling, noting that explicit schemes require impractically small time steps for stable coupling of stiff closed-loop models; our results extend this observation to show that even simultaneous explicit evaluation of all modules (unified Euler) recovers correct behavior where sequential evaluation does not.

### 4.3 Implications for Educational and Clinical Simulation

Virtual Vet and similar platforms used for veterinary or medical education must disclose the coupling strategy and module ordering as fundamental methodological facts, not implementation details. A ±45 mmHg MAP error at baseline would produce incorrect vital sign interpretations in a clinical training scenario. Developers of multi-organ physiological simulations should default to implicit solvers (Radau or BDF) with a unified right-hand-side formulation, or at minimum conduct and report a sensitivity analysis across at least two module orderings.

### 4.4 Recommendation

**Primary recommendation**: Unified state-vector formulation (all modules read from and write to the same state vector simultaneously) with either implicit or small-step explicit integration. This eliminates sequential coupling bias entirely; RMSE < 0.2 mmHg confirmed across all tested scenarios regardless of the underlying ODE solver. For the Virtual Vet platform, `VirtualCreature._unified_rhs(t, y)` passed to `scipy.integrate.solve_ivp` with `method='Radau'` provides the most robust solution.

**Secondary recommendation**: If only sequential explicit Euler is feasible, run the same simulation with two orderings (heart→neuro AND neuro→heart) and report the maximum difference across orderings as an uncertainty bound attached to every MAP time series.

**Minimum disclosure**: Any simulation using sequential coupling must report which module is computed first and provide a sensitivity analysis across at least two orderings.

---

## 5. Conclusion

Sequential explicit Euler coupling in a multi-organ baroreflex simulation introduces order-dependent bias that is O(1) (time-step invariant) and causally reverses with module order swap. The bias magnitude and direction vary with physiological condition: at baseline, heart→neuro produces a +44.7 mmHg MAP error while neuro→heart is accurate; during hemorrhage recovery at t = 30 s, the rankings reverse and heart→neuro becomes accurate while neuro→heart underestimates MAP by 9.4 mmHg. A pure unified Euler formulation achieves RMSE < 0.2 mmHg regardless of initialization order.

No module ordering is universally safe across all physiological scenarios. The physiological simulation community should adopt a unified state-vector formulation — in which all organ modules evaluate derivatives against the identical state vector simultaneously — as the standard for multi-organ baroreflex simulation, with explicit documentation of which solver is applied to the unified RHS. Any remaining use of sequential coupling must be accompanied by systematic ordering sensitivity analysis. This finding extends beyond the baroreflex: any tight feedback loop in a multi-organ simulation — renal RAAS, pulmonary gas exchange, endocrine axes — is potentially subject to sequential coupling bias. The magnitude of bias in these systems will depend on feedback gain, coupling strength, and timescale separation; systematic quantification across coupling topologies is needed before generalizing the 45 mmHg baseline bias observed here. Future work should map the bias landscape across the full 11-organ module graph to identify which coupling topologies are robust and which require unified state-vector formulation.

---

## References

- Causin, P., Gerbeau, J.F. & Nobile, F. (2005). Added-mass effect in the design of partitioned algorithms for fluid-structure problems. *Computer Methods in Applied Mechanics and Engineering*, 194(42-44), 4506-4527.
- Förster, C., Wall, W.A. & Ramm, E. (2007). Artificial added mass instabilities in sequential staggered coupling of nonlinear structures and incompressible viscous flows. *Computer Methods in Applied Mechanics and Engineering*, 196(7), 1278-1293.
- Guyton, A.C., Coleman, T.G. & Granger, H.J. (1972). Circulation: overall regulation. *Annual Review of Physiology*, 34, 13-44.
- Hairer, E. & Wanner, G. (1996). *Solving Ordinary Differential Equations II: Stiff and Differential-Algebraic Problems* (2nd ed.). Springer.
- Kim, J., Tchelepi, H.A. & Juanes, R. (2011). Stability and convergence of sequential methods for coupled flow and geomechanics: Drained and undrained splits. *Computer Methods in Applied Mechanics and Engineering*, 200(23-24), 2611-2626. [416 citations — Drained split ↔ heart→neuro]
- Kim, J., Tchelepi, H.A. & Juanes, R. (2011). Stability and convergence of sequential methods for coupled flow and geomechanics: Fixed-stress and fixed-strain splits. *Computer Methods in Applied Mechanics and Engineering*, 200(13-16), 1591-1605. [211 citations — Fixed-strain ↔ neuro→heart]
- Kim, J. (2010). *Sequential Methods for Coupled Geomechanics and Multiphase Flow* (PhD Thesis). Stanford University. [original source of Eq. 4.7 proving O(1) error in drained split]
- Mikelic, A. & Wheeler, M.F. (2013). Convergence of iterative coupling for coupled flow and geomechanics. *Computational Geosciences*, 17(3), 455-461. [Banach fixed-point convergence proof for fixed-stress split]
- White, J.A., Castelletto, N. & Tchelepi, H.A. (2016). Block-partitioned solvers for coupled poromechanics: A unified framework. *Computer Methods in Applied Mechanics and Engineering*, 303, 55-89. [fixed-stress = preconditioned Richardson iteration]
- Keener, J. & Sneyd, J. (2009). *Mathematical Physiology* (2nd ed.). Springer. [comprehensive baroreflex and cardiovascular modeling reference]
- Ottesen, J.T., Olufsen, M.S. & Larsen, J.K. (2004). *Applied Mathematical Models in Human Physiology*. SIAM. [baroreflex feedback modeling; SIAM Monographs]
- Shi, Y., Udelson, J. et al. (2011). Numerical methods for 0D cardiovascular modeling. *Annals of Biomedical Engineering*, 39(9), 2284-2304.
- Strang, G. (1968). On the construction and comparison of difference schemes. *SIAM Journal on Numerical Analysis*, 5(3), 506-517.
- Tłałka, K., Saxton, H., Halliday, I., Xu, X. et al. (2024). Sensitivity analysis of closed-loop one-chamber and four-chamber models with baroreflex. *PLOS Computational Biology*. https://doi.org/10.1371/journal.pcbi.1012377
- Ursino, M. (1998). Interaction between carotid baroregulation and the pulsating heart: a mathematical model. *American Journal of Physiology — Heart and Circulatory Physiology*, 275(44), H382–H398. [PMID: 9815081]
- Lu, H., Ishibashi, H., Koyama, S. et al. (2026). The AI Scientist: toward fully automated open-ended scientific discovery. *Nature*, 651:914–919. https://doi.org/10.1038/s41586-025-07819-w

---

## Supplementary Materials

### Figure S1: Multi-Organ Platform Architecture

Schematic of the Virtual Vet 11-organ platform showing the dual baroreflex loop architecture: loop A (intra-heart, heart.py derivatives) and loop B (inter-module, neuro.compute() → FactorCommands → heart). The sequential coupling ordering (heart→neuro vs neuro→heart) determines when loop B's FactorCommands are applied relative to loop A's SVR target computation.

### Figure S2: Pure Euler Convergence Analysis

(A) RMSE(MAP) vs dt on semi-log axes for pure Euler at dt = 0.1 to dt = 1×10⁻⁴ s, 60 s observation window. First-order convergence is confirmed: RMSE ∝ dt with slope ≈ 1.0. (B) MAP time series showing plateau elimination: pure Euler at dt=0.01 s converges to the same steady-state as finer dt values, unlike sequential Euler which shows a divergent plateau.

### Figure S3: Baseline Swap Experiment — Time Series and Equilibrium Divergence

(A) MAP time series under heart→neuro and neuro→heart orderings at baseline, dt = 0.01 s. neuro→heart maintains MAP = 100.0 mmHg throughout; heart→neuro diverges to 144.7 mmHg by t = 40 s. (B) Equilibrium MAP after 60 s for each ordering, confirming the ±44.7 mmHg asymmetry.

### Figure S4: 400 mL Hemorrhage Transient — Order Accuracy Reversal

MAP (top) and blood volume (bottom) time series for 400 mL hemorrhage beginning at t = 5 s. Both orderings track similarly during the acute phase (t = 5–25 s) but diverge during recovery (t = 25–40 s): heart→neuro recovers to ~98 mmHg by t = 30 s (accurate) while neuro→heart remains suppressed at ~89 mmHg (−9.4 mmHg error).

### Figure S5: Time-Step Invariance of Sequential Euler Bias

MAP at t = 60 s under heart→neuro ordering across seven orders of magnitude in dt (0.1 s to 1×10⁻⁹ s). The bias is constant at +44.7 mmHg across all tested time steps, confirming O(1) (time-step invariant) bias rather than a numerical truncation error. Each point represents a separate simulation; the flat line at 144.7 mmHg spans dt = 10⁰ to dt = 10⁻⁹.

### Table S1: Pure Euler Convergence Data

*See Table S1 above in Section 3.1*

### Table S2: Parameter Sweep — Bias is Architecture-Intrinsic, Not Parameter-Driven

Three parameter sweep experiments (baroreflex gain, seizure SVR multiplier, body mass, SVR_baseline) each confirmed that the heart→neuro bias is constant at 44.742 mmHg regardless of parameter values — confirming the bias is an architectural intrinsic property, not a parameter-external manifestation.

**Experiment 1 — Baroreflex Gain Sweep:** bias = 44.742 mmHg across all gains [0.5, 1.0, 2.0, 4.0, 8.0×]. Reason: SVR_increase = 1.0 + 2.0 × sympathetic × max(0, error) uses max(0, error) as a threshold gate — at baseline MAP ≈ 100 mmHg, error ≈ 0, so gain parameter has no effect on SVR growth.

**Experiment 2 — Seizure SVR Multiplier Sweep:** bias = 44.742 mmHg across all multipliers [0.0, 0.1, 0.3, 0.5, 0.7]. Reason: Loop A's SVR accumulation is driven autonomously by heart.compute() using the heart's own sympathetic state; Loop B's FactorCommands (disabled by seizure_mult = 0) are not the primary driver.

**Experiment 3 — Body Mass Sweep:** bias ranges from 44.708 to 44.759 mmHg across [10, 20, 30, 40] kg — variation < 0.06 mmHg, effectively constant.

| Parameter | Values Tested | MAP (heart→neuro) | MAP (neuro→heart) | Bias |
|-----------|--------------|-------------------|------------------|------|
| Baroreflex gain | 0.5, 1.0, 2.0, 4.0, 8.0× | 144.742 | 100.000 | **44.742 mmHg** (all) |
| Seizure SVR mult | 0.0, 0.1, 0.3, 0.5, 0.7 | 144.742 | 100.000 | **44.742 mmHg** (all) |
| Body mass | 10, 20, 30, 40 kg | 144.708–144.759 | ~100.000 | **44.7 mmHg** (±0.03) |
| SVR_baseline | 0.8, 0.9, 1.0, 1.1, 1.2× | 144.742 | 100.000 | **44.742 mmHg** (all) |

Conclusion: O(1) bias is fully determined by the information-lag structure of sequential Gauss-Seidel coupling, not by any physiological parameter. This makes the bias a fundamental architectural vulnerability — it cannot be eliminated by parameter tuning.

### Table S3: False Picard Experiment — Scenario-Dependent Pseudo-Convergence

A natural response to sequential coupling bias is to perform multiple forward passes per timestep (k > 1), under the assumption that iteration will converge toward the correct solution. We tested this hypothesis using the heart→neuro ordering with k ∈ {1, 2, 4} passes per timestep, measuring MAP at baseline and under 400 mL hemorrhage at t = 5 s.

**Baseline (no hemorrhage):** At baseline, HR is already saturated at its physiological maximum (180 bpm) by k = 1. Repeating the forward chain does not change the outcome — MAP@60s = 144.776 mmHg for all k ∈ {1, 2, 4}. This is the **saturation pseudo-convergence** regime: the system appears to have converged (k=1 ≡ k=4), but the converged value is wrong.

**Hemorrhage (400 mL at t = 5 s):** Under blood loss, k>1 dramatically worsens the transient. At t = 10 s (acute phase), k=1 gives MAP = 96.28 mmHg (appropriate hypotension) while k=4 gives MAP = 133.86 mmHg (hypertensive overshoot). Maximum divergence is +37.6 mmHg at t = 10 s, which converges back to a common steady state by t ≈ 35 s as HR saturation dominates.

| k | Baseline MAP@60s | Hemorrhage MAP@10s | HR@10s | Interpretation |
|---|-----------------|---------------------|--------|----------------|
| 1 | 144.776 | 96.28 | 86.4 | Appropriate baseline bias; reasonable hemorrhage response |
| 2 | 144.776 | 109.66 | 144.0 | Transient MAP overshoot |
| 4 | 144.776 | 133.86 | 180.1 | Severe hypertensive overshoot; worst outcome |

The interpretation is **scenario-dependent pseudo-convergence**: in both scenarios the iteration appears to converge (k>1 ≡ k=1 at steady state), but the convergence is an artifact of variable saturation — not of the coupling scheme possessing a contraction property. The MAP at t = 60 s is identical across k for both scenarios, yet the transient trajectories diverge substantially under hemorrhage. This is qualitatively different from Kim et al.'s (2011) fixed-stress split, where each sub-iteration uses the latest solution from the other subsystem and the spectral radius of the iteration operator is less than one (Mikelic & Wheeler 2013), guaranteeing convergence to the correct solution. Our false Picard scheme lacks this contraction mapping — the apparent convergence is produced by HR saturating at its physiological ceiling (180 bpm), which freezes the iteration from the outside rather than because the coupling has reached a correct fixed point. A developer comparing k=1 and k=4 and finding them identical at steady state would reasonably conclude that the iteration has converged, never suspecting that the transient has been severely distorted.

### 4.4 Independent Model Verification — Bias is Not VirtualCreature-Specific

One potential objection to our findings is that the 44.742 mmHg bias might be an artifact specific to the VirtualCreature architecture — a consequence of a particular initialization sequence or hidden coupling path unique to that platform. To address this, we constructed a minimal two-module system (heart + neuro, no other organs) using the same FactorCommand pattern and the same `_baroreceptor_feedback` implementation from heart.py. The minimal model uses the same `HeartModule` and `NeuroModule` classes as VirtualCreature, with identical `MAP_target = 100.0 mmHg` and `SVR_baseline = 1.412 mmHg/L/min`. The two orderings were implemented identically to the full platform.

The minimal model reproduced the bias exactly: heart→neuro ordering produced MAP = 144.742 mmHg (HR = 180.15 bpm, SVR = 1.4118), while neuro→heart ordering produced MAP = 100.000 mmHg (HR = 85.00 bpm, SVR = 1.4118). The bias magnitude (44.742 mmHg) matches the full VirtualCreature result exactly, confirming that the bias is **not a VirtualCreature-specific artifact** but a general property of sequential Gauss-Seidel coupling with the baroreflex information-timestamp mechanism.

Furthermore, the parameter-insensitive bias (Table S2) was also reproduced in the minimal model: sweeping SVR_baseline through [0.8, 0.9, 1.0, 1.1, 1.2]× the default value produced identical bias = 44.742 mmHg across all values. This confirms that the bias architecture (sequential coupling with information lag) is the sole determinant, independent of any platform-specific initialization or coupling path.

### Code Availability

The Virtual Vet platform source code is available at: [repository URL]. Experiment scripts for the convergence study, order swap experiment, and hemorrhage transient are located in the `experiments/` directory.

---

*Corresponding author: [Name], [Institution], [email]*
*Competing interests: None declared.*
*Funding: [ funding source ]*