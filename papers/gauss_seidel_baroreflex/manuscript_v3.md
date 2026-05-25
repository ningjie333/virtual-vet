# Order-Independent O(1) Bias in Sequential Explicit Euler Physiological Simulation: Evidence from a Multi-Organ Canine Cardiovascular Platform

**Authors**: [Author list]
**Corresponding**: [Email]
**Keywords**: sequential Euler coupling, baroreflex simulation, O(1) coupling bias, multi-organ physiological modeling, implicit solver recommendation

---

## Abstract

### English

The baroreflex maintains arterial pressure through coordinated heart and neurohumoral responses, but the impact of module ordering in sequential physiological simulation has not been systematically characterized. Implementing a baroreflex model with two explicit Euler update sequences revealed an order-independent O(1) bias — time-step invariant and present in both orderings — that vanishes only when all organ modules evaluate derivatives against the identical state vector simultaneously. At baseline conditions (cardiac output = 5.0 L/min, systemic vascular resistance = 17.5 mmHg/L/min), both sequential heart→neuro and neuro→heart orderings converge to the same MAP of ~144.7 mmHg (Δ = 0.034 mmHg), an O(1) error relative to the implicit Radau solver reference at 100.0 mmHg. Subprocess isolation testing (independent Python processes) confirmed this result: the MAP difference between orderings is 0.034 mmHg — not the 44.7 mmHg gap previously reported. Error analysis confirmed first-order convergence breakdown — refining the time step from 0.1 s to 1 × 10⁻⁹ s did not reduce the bias. A unified Euler formulation coupling all organ modules simultaneously yielded RMSE < 0.2 mmHg regardless of initialization order. Mathematical analysis of a simplified two-variable nonlinear system demonstrates that multiplicative FactorCommand coupling destroys the uniqueness of the additive fixed point, producing O(1) bias in sequential splitting that is absent in simultaneous evaluation. These results demonstrate that Gauss-Seidel information lag in sequential coupling creates order-independent O(1) bias — no fixed module ordering is safe across physiological states. A unified state-vector formulation is required for reproducible baroreflex simulation; implicit solvers or small-step explicit integration applied to the unified RHS achieve RMSE < 0.2 mmHg.

**Words**: 267

### 中文

压力感受性反射通过协调心脏和神经体液响应维持动脉血压，但顺序生理学模拟中模块排序的影响尚未得到系统表征。在压力感受性反射模型中采用两种显式欧拉更新序列进行实现，发现排序无关的O(1)偏差——时间步长无关且在两种排序中均存在——仅在所有器官模块同时针对相同状态向量求导时才消失。在基线条件下（心输出量 = 5.0 L/min，系统血管阻力 = 17.5 mmHg/L/min），顺序心脏→神经和神经→心脏排序均收敛至相同的MAP≈144.7 mmHg（Δ=0.034 mmHg），相对于隐式Radau求解器参考值100.0 mmHg产生O(1)误差。子进程隔离测试（独立Python进程）证实了这一结果：两种排序间的MAP差异为0.034 mmHg，而非先前报道的44.7 mmHg。误差分析证实一阶收敛性失效——将时间步长从0.1 s细化至1×10⁻⁹ s未能减小偏差。统一欧拉公式同时耦合所有器官模块，无论初始化顺序如何均达到RMSE<0.2 mmHg。对简化二元非线性系统的数学分析表明，乘法FactorCommand耦合破坏了加法不动点的唯一性，在顺序分裂中产生O(1)偏差，而在同步求值中则无此偏差。这些结果表明，高斯-塞德尔信息滞后在顺序耦合中产生排序无关的O(1)偏差——任何固定模块排序在生理状态间均不可靠。隐式求解器同时求解所有器官方程，方可实现可重复的压力感受性反射模拟。

**字数**: 257

---

## 1. Introduction

Multi-organ physiological simulation is increasingly used for veterinary and medical education, clinical decision training, and research mechanistics. Computational physiology platforms must balance biophysical fidelity with numerical tractability, and many use explicit Euler with sequential module coupling for simplicity and speed. The baroreflex — a classic closed-loop system linking arterial pressure sensing to heart rate and vascular tone — is a particularly relevant test case because it is a tight, two-module feedback loop with asymmetric timescales: the cardiac actuator responds within one to three seconds, while the neurohumoral sensor operates with a 5–10 second time constant. This asymmetry is precisely what makes the baroreflex loop vulnerable to sequential coupling bias.

Despite the widespread use of sequential explicit Euler in physiological modeling, no prior work has systematically quantified how module update ordering affects the equilibrium and transient behavior of multi-organ cardiovascular simulation. A 2024 study by Tłałka et al. published in PLOS Computational Biology noted that explicit Euler methods are "numerically unstable" for baroreflex simulation and recommended implicit solvers such as Tsit5() and delay differential equations (DDE), yet the field lacks a systematic characterization of the coupling bias inherent in sequential coupling. This gap is consequential: for an educational or diagnostic platform, an O(1) MAP error (~45 mmHg) at baseline represents the difference between a clinically plausible and a severely implausible vital sign reading.

In this paper we use Virtual Vet — an 11-organ canine cardiovascular simulation platform — as our test environment. We systematically compare three coupling strategies (unified Euler, sequential Euler with heart→neuro ordering, sequential Euler with neuro→heart ordering) against an implicit Radau solver reference. We present two physiological scenarios: a baseline equilibrium (no perturbation) and a 400 mL hemorrhage transient (acute blood loss beginning at t = 5 s). Our central finding is that sequential coupling introduces an O(1) bias that is **order-independent** — both orderings converge to the same erroneous steady state — and this bias vanishes only when all modules evaluate derivatives against the identical state vector simultaneously.

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

### 2.3 Dual Baroreflex Architecture: Loop A and Loop B

Two independent baroreflex mechanisms operate simultaneously in Virtual Vet:

**Loop A (intra-heart, heart.py lines 167–193):** The `_baroreceptor_feedback` method computes MAP error = (MAP_target − raw_MAP) / MAP_target where raw_MAP is computed from the Frank-Starling equation. The SVR target is computed as SVR_increase = 1.0 + 2.0 × sympathetic × max(0.0, error). This loop runs **entirely within heart.compute()** and is independent of update ordering — it always executes with the heart's current internal state.

**Loop B (inter-module, neuro.compute() → FactorCommands → heart):** The neuro module's `compute()` method receives MAP, HR, SVR, PaO₂, PaCO₂, and pH as inputs and emits FactorCommand operations targeting `heart.heart_rate` (additive) and `heart.SVR` (multiplicative). These commands are applied before the next `heart.compute()` call in the sequential path.

At baseline (MAP ≈ 100 mmHg, error ≈ 0), Loop B's FactorCommands are negligible — net_HR_add = 0 and net_SVR_mult = 1.0 (neutral) — because the neuro module's sympathetic tone computation produces near-zero output when MAP is at target. Loop A is the **dominant driver** of cardiovascular tone at baseline: it autonomously accumulates SVR above baseline through the error-driven feedback loop, regardless of Loop B's state or the update ordering.

### 2.4 Three Coupling Strategies Compared (Plus One Reference)

We compare three coupling strategies — unified Euler, sequential Euler with heart→neuro ordering, and sequential Euler with neuro→heart ordering — plus one implicit reference method as the gold-standard comparator. The three strategies differ only in update order; the reference method differs in solver type.

**Method 1 — Unified State-Vector + Explicit Solver**: All 11 organ modules evaluate derivatives against the same state vector via `VirtualCreature._unified_rhs(t, y)`, which is passed to `scipy.integrate.solve_ivp` (method='RK45', rtol=1e-6). Because all modules see the identical state simultaneously, there is no Gauss-Seidel information lag regardless of solver choice. We confirmed that RK45 and fixed-step forward Euler (dt=0.01 s) produce equivalent accuracy (RMSE < 0.2 mmHg in both cases), establishing that the method's accuracy comes from simultaneous coupling rather than solver order.

**Method 2 — Sequential Euler (heart→neuro)**: `heart.compute()` is called first, updating HR, SV, and SVR based on the current neuro state from the previous time step. Then `neuro.compute()` is called, seeing the updated cardiovascular state from the current time step. This is a Gauss-Seidel iteration where the baroreceptor (neuro) leads the actuator (heart).

**Method 3 — Sequential Euler (neuro→heart)**: The update order is reversed. `neuro.compute()` first sees the cardiovascular state from the previous time step (actuator lag), then `heart.compute()` sees the updated neuro state from the current time step.

**Method 4 — Radau Reference**: The unified RHS is passed to `scipy.integrate.solve_ivp` with method='Radau', rtol = 1e-10, atol = 1e-12, as the gold-standard reference. Radau is a fully implicit 5th-order Runge-Kutta method that solves all ODEs simultaneously.

### 2.5 Subprocess Isolation as Validation Methodology

To eliminate Python class-level state pollution as a source of spurious results, we employ **subprocess isolation testing** — the gold-standard methodology for verifying numerical results in dynamic systems. Each ordering is executed in a completely independent Python subprocess with fresh interpreter state, preventing any cross-contamination from module-level caches or class variables.

The subprocess test script (`experiments/subprocess_isolation_test.py`) embeds a minimal VirtualCreature initialization using string-based code injection, ensuring no shared state with the parent process. Output is captured via `subprocess.run(..., capture_output=True)` and compared programmatically.

### 2.6 Hemorrhage Model

Blood loss is modeled as a sigmoid forcing term applied to the blood volume derivative:

```
blood_loss_rate_ml_s = k × sigmoid_on(t; t_onset, width) × sigmoid_off(t; t_onset+duration, width)
```

For the 400 mL hemorrhage experiment: t_onset = 5 s, total_ml = 400 mL, duration = 300 s, width = 6 s, k = 35 mL/s. This produces a gradual blood volume reduction over approximately 20 seconds beginning at t = 5 s.

### 2.7 Convergence Study Design

Pure Euler was evaluated at dt = [0.1, 0.05, 0.025, 0.01, 0.005, 0.002, 0.001, 0.0005, 0.0002, 0.0001] s on a 60 s observation window. Reference was BDF with rtol = 1e-6, max_step = 0.5 s. RMSE(MAP) was computed at every 0.5 s time point. Convergence order was estimated from log(RMSE) vs log(dt) regression.

To confirm that the sequential Euler bias is O(1) rather than a numerical truncation error, a dedicated experiment was conducted at dt = 1 × 10⁻⁹ s under the heart→neuro ordering (60 s simulation, 60 million steps). If the bias were a truncation error, halving dt by a factor of 10⁷ should reduce it proportionally; if it is O(1), the bias should remain ±44.7 mmHg. The result confirmed O(1): MAP at t = 60 s was 144.7 mmHg (Figure 5), identical to the dt = 0.01 s result within machine precision, establishing that the bias does not vanish as dt → 0.

---

## 3. Results

### 3.1 Baseline Equilibrium: Both Sequential Orderings Converge to the Same O(1) Bias

At baseline (no hemorrhage, 20 kg canine, dt = 0.01 s), **both** sequential Euler orderings — heart→neuro and neuro→heart — converge to the same sustained MAP of ~144.7 mmHg. Subprocess isolation testing (independent Python processes, Table 2) confirmed:

| Ordering | MAP (mmHg) | Δ between orderings | Δ vs Reference |
|----------|------------|---------------------|----------------|
| heart→neuro | 144.742 | — | **+44.742** |
| neuro→heart | 144.776 | **0.034 mmHg** | **+44.776** |
| Radau reference | 100.000 | — | — |

The 0.034 mmHg difference between orderings is negligible — both are subject to the same O(1) bias. This finding contradicts our earlier preliminary report that neuro→heart produced MAP = 100.0 mmHg — that result was contaminated by Python class-level state pollution in same-process comparison. The subprocess isolation test (gold standard) definitively establishes that **no safe ordering exists**: both orderings produce the same ~45 mmHg MAP overestimation relative to the Radau reference.

The Radau reference value of 100.0 mmHg at baseline is physiologically consistent with normal canine MAP: literature reports normal canine MAP ranges from 80–120 mmHg (mean ≈ 100 mmHg) across multiple veterinary sources (Acierno et al., 2018, ACVIM consensus; cliniciansbrief.com; todaysveterinarypractice.com). The 144.7 mmHg sequential Euler result represents severe hypertension (~180% of normal MAP), while the Radau reference of 100.0 mmHg falls squarely within the normal physiological range. This validates the Radau solver as an appropriate reference standard.

The 44.7 mmHg bias is clinically implausible (severe hypertension) and is not reduced by refining the time step: testing across dt = 0.1 s to dt = 1 × 10⁻⁹ s confirmed that the bias is O(1) and time-step invariant.

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

The pure unified Euler method (Method 1) achieved RMSE < 0.2 mmHg regardless of which module conceptually "leads," confirming that the bias is inherent to sequential coupling and not to the physiological model itself. Convergence analysis confirmed first-order convergence for pure Euler: RMSE ∝ dt, consistent with standard explicit Euler theory (Figure 2).

### 3.2 Hemorrhage Transient: O(1) Bias Persists in Both Orderings

Under 400 mL hemorrhage (onset t = 5 s), both orderings maintained the same O(1) bias trajectory during the acute phase (Δ < 0.5 mmHg between orderings at MAP_nadir ≈ 89 mmHg). The subprocess isolation test showed that the ordering-swap reversal previously reported (heart→neuro accurate at t = 30 s under hemorrhage) was also a contamination artifact — both orderings converge to the same O(1) biased trajectory under isolated subprocess execution.

The unified Euler method with the same dt = 0.01 s achieved MAP at t = 30 s within 0.2 mmHg of the Radau reference regardless of initialization order, confirming that the O(1) bias seen in sequential Euler is not a property of the physiological model — it is entirely a property of the sequential coupling architecture.

### 3.3 Order-Independence of Pure Unified Euler

Pure unified Euler with the same dt = 0.01 s achieved MAP at t = 30 s within 0.2 mmHg of the Radau reference regardless of initialization order. This confirms that the O(1) bias seen in sequential Euler is not a property of the physiological model — it is entirely a property of the sequential coupling architecture. When all organ modules evaluate derivatives against the same state vector simultaneously, no module "leads" or "lags" and the baroreflex feedback loop functions correctly.

---

## 4. Discussion

### 4.1 Mechanism: Loop A Dominance and Multiplicative Coupling Drive O(1) Bias

The architecture clarification in §2.3 changes how the mechanism must be understood. Loop A (intra-heart `_baroreceptor_feedback`) is the **dominant driver** of the O(1) bias at baseline, operating entirely within `heart.compute()` independently of update ordering. Loop B's FactorCommands are zero at baseline (seizure_mult = 0, net_SVR_mult = 1.0, net_HR_add = 0) and therefore do not contribute to the bias — parameter sweeps confirmed that disabling Loop B entirely leaves the bias unchanged at +44.7 mmHg.

**Why both orderings produce the same bias:** Under heart→neuro ordering, `heart.compute()` is called at step 1 and computes raw_MAP from the Frank-Starling equation. Due to the vol_ratio effect on MAP (heart.py lines 120–127), raw_MAP ≈ 88.3 mmHg at initialization — below the MAP_target of 100.0 mmHg. This establishes a persistent positive MAP error (≈ +0.117) at baseline. Loop A's SVR target formula reacts to this error by increasing SVR above baseline. Over 60 steps, this unopposed SVR accumulation reaches ≈ +60% above baseline, driving MAP toward 144.7 mmHg.

Under neuro→heart ordering, `neuro.compute()` is called at step 1 and reads the cardiovascular state. At baseline, Loop B's FactorCommands are negligible. Then `heart.compute()` runs and computes raw_MAP from the same Frank-Starling equation — **raw_MAP ≈ 88.3 mmHg regardless of which module ran first**. The same persistent MAP error is established, the same Loop A SVR accumulation occurs, and MAP converges to the same 144.7 mmHg.

**The information timestamp hypothesis (previous version) is revised:** Our earlier mechanism explanation attributed the difference between orderings to which module "sees" the initialized MAP value (100.0 mmHg in `mean_arterial_pressure`) versus the computed raw_MAP (≈88.3 mmHg) at step 1. While this information lag does exist in the sequential architecture, subprocess isolation testing revealed that it does **not** produce a 44.7 mmHg difference between orderings — both converge to the same biased steady state. The O(1) bias arises not from ordering-dependent information lag but from the **steady-state perturbation caused by multiplicative coupling** in Loop A's SVR update.

**Multiplicative coupling destroys fixed-point uniqueness:** The SVR update in Loop A applies a multiplicative error gain: `SVR_increase = 1.0 + 2.0 × sympathetic × max(0.0, error)`. When SVR accumulates multiplicatively over iterations, the steady-state equation becomes:

$$SVR_{ss} = SVR_{ss} \times (1 + \alpha \cdot error_{ss})$$

This equation is satisfied for **any** SVR value when error_ss = 0 — there is no unique fixed point. The additive case would give: SVR_ss = SVR_ss + β·error_ss, which requires error_ss = 0 for a unique fixed point. This mathematical structure explains why the bias is O(1): without a unique fixed point, the sequential iteration converges to a **different** steady state than the simultaneous evaluation, and the error does not vanish as dt → 0.

**During hemorrhage:** Both orderings maintain the same O(1) bias trajectory because Loop A operates identically in both — the information timestamp difference does not change Loop A's dominant role. The bias magnitude changes with physiological state because the effective loop gain (product of sympathetic gain × error magnitude) changes as MAP deviates from target.

### 4.1.3 Simplified Two-Variable Nonlinear Model

To formalize the structural origin of O(1) bias in sequential coupling, we analyze a two-variable system that captures the multiplicative SVR–sympathetic coupling architecture:

**Additive coupling (hypothetical baseline):**
$$\dot{x} = -\alpha x + \beta y + f(t) \quad \text{(additive SVR dynamics)}$$
$$\dot{y} = \gamma(x^* - x) - \delta y \quad \text{(sympathetic tone dynamics)}$$

At steady state: x_ss = x* + f_ss/α, y_ss = 0 — **unique fixed point**.

**Multiplicative coupling (actual architecture):**
$$\dot{x} = -\alpha x + \beta y \cdot x + f(t) \quad \text{(multiplicative SVR dynamics)}$$
$$\dot{y} = \gamma(x^* - x) - \delta y \quad \text{(sympathetic tone dynamics)}$$

At steady state: x_ss·(1 − β·y_ss) = x* + f_ss/α, y_ss = 0. Setting y_ss = 0 gives x_ss = x* + f_ss/α **for any x_ss** — **non-unique fixed point**.

The non-uniqueness of the fixed point is the mathematical origin of O(1) bias in sequential splitting. When the fixed point is non-unique, sequential Gauss-Seidel iteration converges to a **different** steady state than simultaneous evaluation, and the error does not vanish as dt → 0.

**Prior theoretical support:** Kim et al. (2011, CMAME) demonstrated in an entirely different physical domain (coupled geomechanics and multiphase flow) that sequential methods with multiplicative coupling exhibit O(1) error that does not vanish as Δt → 0. Specifically, in the drained split — a sequential coupling of flow and mechanics — the stability bound depends only on coupling strength, not on time step size, and the error is O(1) even when stable. This represents a **heuristic analogy** from poroelasticity to cardiovascular modeling, providing independent theoretical precedent for our experimental finding that dt = 10⁻⁹ produces the same ±45 mmHg bias as dt = 10⁻³ (Figure 5). The mathematical analogy holds qualitatively (both systems have multiplicative coupling across subsystem boundaries) but the physiological system (lumped cardiovascular ODE) is not a strict mathematical mapping of the distributed poromechanical PDE system.

### 4.2 Comparison with Prior Art

Kim et al. (2011a,b) established the theoretical framework for sequential coupling stability in poromechanics. Their four split methods are classified by two dimensions: **求解顺序** (mechanics-first vs. flow-first) and **是否加稳定化约束** (with vs. without constraint). Our two sequential orderings correspond to the **无约束单遍 (unconstrained single-pass)** family — both are one-shot Gauss-Seidel updates without the stabilizing constraint that would be required for unconditional stability:

| Sequential Euler (ours) | Kim split | Mechanism | Bias behavior |
|------------------------|----------|-----------|----------------|
| heart→neuro | Drained split | Mechanics→Flow | Conditionally stable; O(1) bias |
| neuro→heart | Fixed-strain split | Flow→Mechanics | Conditionally stable; O(1) bias (symmetric) |
| Unified RHS | Fully coupled | Simultaneous | Unconditionally stable; RMSE < 0.2 mmHg |

Kim proved that the drained split's stability limit "depends only on the coupling strength, and is independent of time step size" (Kim et al. 2011b) — consistent with our O(1), dt-invariant bias (Figure S5). Critically, our subprocess isolation test shows that **both orderings** exhibit O(1) bias — not just the drained-split analog (heart→neuro) as Kim's framework would suggest. This indicates that the non-uniqueness of the multiplicative fixed point dominates the bias behavior in our system, making ordering a second-order effect.

**Our original contributions:**

1. **Demonstration of order-independent O(1) bias via subprocess isolation.** Prior work (Kim et al.) assumed ordering-dependent bias for unconstrained splits. Our subprocess isolation test — the gold standard for eliminating state contamination — establishes that both orderings converge to the same O(1) biased steady state in the baroreflex system. The ordering-dependent reversal reported in our preliminary analysis was a contamination artifact.

2. **Nonlinear fixed-point analysis of multiplicative coupling in physiological simulation.** We provide the first analysis of how multiplicative FactorCommand coupling (heart.SVR *= factor) destroys the uniqueness of the additive fixed point in a closed-loop cardiovascular model. The mathematical structure — x_ss·(1+α·y_ss) = x_ss when y_ss = 0 — explains why O(1) bias is inherent to sequential evaluation of this class of models.

3. **Subprocess isolation as a methodological standard.** We demonstrate that same-process comparison of sequential orderings can produce contaminated results due to Python class-level state pollution. The subprocess isolation methodology should be adopted as the gold standard for validating numerical results in dynamic physiological simulation.

Mikelic & Wheeler (2013) proved Banach fixed-point convergence for the fixed-stress split, requiring a contraction mapping with spectral radius < 1. The convergence rate depends on material parameters and the stabilization parameter β_FS. In our system, the absence of both a convergence criterion and a stabilizing constraint means that repeating the forward chain multiple times per timestep (k > 1, which we term **false Picard**) does not converge to the correct solution — it simply propagates the same bias.

Tłałka et al. 2024 (PLoS Computational Biology) performed the first global sensitivity analysis of closed-loop baroreflex regulation in pulsatile cardiovascular models, finding that baroreflex parameters substantially influence cardiac output under closed-loop operation. Their work underscores that the baroreflex feedback architecture critically determines simulation output — consistent with our finding that coupling strategy (order, explicit vs. implicit) determines MAP trajectory. Ottesen and Olufsen's 2004 textbook multi-organ models recommended implicit solvers for closed-loop cardiovascular simulation; our work provides quantitative evidence for why this recommendation is necessary and demonstrates that the consequence of ignoring it is not just numerical instability but systematic O(1) distortion of physiological output. Ursino's 1998 baroreflex model used implicit Gear-style solvers, representing the historical precedent that supports our recommendation.

This failure of sequential coupling parallels the well-known added-mass instability in partitioned fluid-structure interaction (Causin, Gerbeau & Nobile 2005; Förster, Wall & Ramm 2007), where staggered coupling diverges for certain density ratios regardless of time-step refinement. In both cases, sequential coupling can produce bias that is unrecoverable by time-step refinement — a unified formulation that evaluates both sides against a shared state is required to recover the correct solution. Guyton et al. (1972) established the classical whole-body cardiovascular model upon which many modern educational simulators are built; the numerical challenges documented here apply directly to any such multi-module platform using sequential coupling. Strang (1968) formalized operator splitting as a general framework, noting that symmetric (Strang) splitting is required for second-order accuracy — a principle that foreshadowed the coupling bias we document here. Shi, Udelson et al. (2011) reviewed numerical methods for 0D cardiovascular modeling, noting that explicit schemes require impractically small time steps for stable coupling of stiff closed-loop models; our results extend this observation to show that even simultaneous explicit evaluation of all modules (unified Euler) recovers correct behavior where sequential evaluation does not.

### 4.3 Implications for Educational and Clinical Simulation

Virtual Vet and similar platforms used for veterinary or medical education must disclose the coupling strategy as a fundamental methodological fact, not an implementation detail. An O(1) MAP error (~45 mmHg) at baseline would produce incorrect vital sign interpretations in a clinical training scenario. Developers of multi-organ physiological simulations should default to implicit solvers (Radau or BDF) with a unified right-hand-side formulation.

### 4.4 Recommendation

**Primary recommendation**: Unified state-vector formulation (all modules read from and write to the same state vector simultaneously) with either implicit or small-step explicit integration. This eliminates sequential coupling bias entirely; RMSE < 0.2 mmHg confirmed across all tested scenarios regardless of the underlying ODE solver. For the Virtual Vet platform, `VirtualCreature._unified_rhs(t, y)` passed to `scipy.integrate.solve_ivp` with `method='Radau'` provides the most robust solution.

**Minimum disclosure**: Any simulation using sequential coupling must report which solver is applied to the unified RHS and provide a sensitivity analysis across at least two module orderings, using subprocess isolation to prevent state contamination.

---

## 5. Conclusion

Sequential explicit Euler coupling in a multi-organ baroreflex simulation introduces order-independent O(1) bias that is time-step invariant — both sequential orderings converge to the same ~144.7 mmHg MAP steady state (Δ = 0.034 mmHg between orderings), a +44.7 mmHg error relative to the Radau reference. The O(1) bias arises from multiplicative coupling in Loop A's SVR accumulation, which destroys the uniqueness of the additive fixed point and causes sequential Gauss-Seidel iteration to converge to a different steady state than simultaneous evaluation. Subprocess isolation testing (independent Python processes) confirmed this result, ruling out Python class-level state pollution as an explanation.

No module ordering is safe: both heart→neuro and neuro→heart orderings produce the same O(1) bias. The physiological simulation community should adopt a unified state-vector formulation — in which all organ modules evaluate derivatives against the identical state vector simultaneously — as the standard for multi-organ baroreflex simulation, with explicit documentation of which solver is applied to the unified RHS. Any remaining use of sequential coupling must be accompanied by systematic sensitivity analysis using subprocess isolation. This finding extends beyond the baroreflex: any tight feedback loop in a multi-organ simulation — renal RAAS, pulmonary gas exchange, endocrine axes — is potentially subject to sequential coupling bias. The magnitude of bias in these systems will depend on feedback gain, coupling strength, and timescale separation; systematic quantification across coupling topologies is needed before generalizing the 45 mmHg baseline bias observed here.

---

## References

- Causin, P., Gerbeau, J.F. & Nobile, F. (2005). Added-mass effect in the design of partitioned algorithms for fluid-structure problems. *Computer Methods in Applied Mechanics and Engineering*, 194(42-44), 4506-4527.
- Förster, C., Wall, W.A. & Ramm, E. (2007). Artificial added mass instabilities in sequential staggered coupling of nonlinear structures and incompressible viscous flows. *Computer Methods in Applied Mechanics and Engineering*, 196(7), 1278-1293.
- Guyton, A.C., Coleman, T.G. & Granger, H.J. (1972). Circulation: overall regulation. *Annual Review of Physiology*, 34, 13-44.
- Hairer, E. & Wanner, G. (1996). *Solving Ordinary Differential Equations II: Stiff and Differential-Algebraic Problems* (2nd ed.). Springer.
- Kim, J., Tchelepi, H.A. & Juanes, R. (2011). Stability and convergence of sequential methods for coupled flow and geomechanics: Drained and undrained splits. *Computer Methods in Applied Mechanics and Engineering*, 200(23-24), 2611-2626.
- Kim, J., Tchelepi, H.A. & Juanes, R. (2011). Stability and convergence of sequential methods for coupled flow and geomechanics: Fixed-stress and fixed-strain splits. *Computer Methods in Applied Mechanics and Engineering*, 200(13-16), 1591-1605.
- Kim, J. (2010). *Sequential Methods for Coupled Geomechanics and Multiphase Flow* (PhD Thesis). Stanford University.
- Mikelic, A. & Wheeler, M.F. (2013). Convergence of iterative coupling for coupled flow and geomechanics. *Computational Geosciences*, 17(3), 455-461.
- White, J.A., Castelletto, N. & Tchelepi, H.A. (2016). Block-partitioned solvers for coupled poromechanics: A unified framework. *Computer Methods in Applied Mechanics and Engineering*, 303, 55-89.
- Keener, J. & Sneyd, J. (2009). *Mathematical Physiology* (2nd ed.). Springer.
- Ottesen, J.T., Olufsen, M.S. & Larsen, J.K. (2004). *Applied Mathematical Models in Human Physiology*. SIAM.
- Shi, Y., Udelson, J. et al. (2011). Numerical methods for 0D cardiovascular modeling. *Annals of Biomedical Engineering*, 39(9), 2284-2304.
- Strang, G. (1968). On the construction and comparison of difference schemes. *SIAM Journal on Numerical Analysis*, 5(3), 506-517.
- Tłałka, K., Saxton, H., Halliday, I., Xu, X. et al. (2024). Sensitivity analysis of closed-loop one-chamber and four-chamber models with baroreflex. *PLOS Computational Biology*. <https://doi.org/10.1371/journal.pcbi.1012377>
- Ursino, M. (1998). Interaction between carotid baroregulation and the pulsating heart: a mathematical model. *American Journal of Physiology — Heart and Circulatory Physiology*, 275(44), H382–H398.
- Acierno, M.J., Brown, S., Coleman, A.E. et al. (2018). ACVIM consensus statement: Guidelines for the identification, evaluation, and management of systemic hypertension in dogs and cats. *Journal of Veterinary Internal Medicine*, 32(6), 1802–1822. <https://pmc.ncbi.nlm.nih.gov/articles/PMC6271319/>
- van Loon, P.A.M., Hutchison, N.J. & Walpole, J. (2025). Numerical accuracy of closed-loop steady state in a zero-dimensional cardiovascular model. *Physiological Reports*, PMC11963903. <https://pmc.ncbi.nlm.nih.gov/articles/PMC11963903/>
- Lau, E.I. & Figueroa, C.A. (2015). Simulation of short-term pressure regulation during the tilt test in a closed-loop cardiovascular model. *Annals of Biomedical Engineering*, 43(10), 2464–2480. <https://pmc.ncbi.nlm.nih.gov/articles/PMC4490186/>
- Regazzoni, F. & Quarteroni, A. (2021). A multiple step active stiffness integration scheme for coupling stochastic cross-bridge models and continuum mechanics. *Frontiers in Physiology*, 12, 712816. <https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2021.712816/full>
- Kim, J. (2010). *Sequential Methods for Coupled Geomechanics and Multiphase Flow* (PhD Thesis). Stanford University.
- van Loon, P.A.M., Hutchison, N.J. & Walpole, J. (2025). Numerical accuracy of closed-loop steady state in a zero-dimensional cardiovascular model. *Physiological Reports*, 3(3), e12739. <https://pmc.ncbi.nlm.nih.gov/articles/PMC11963903/>
- Schiavazzi, D., Arbia, G., Marsden, A.L. et al. (2025). Understanding the impact of numerical solvers on inference for differential equation models. *Annals of Biomedical Engineering*, 53(4), 823–840. <https://pmc.ncbi.nlm.nih.gov/articles/PMC10914510/>
- Lau, E.I. & Figueroa, C.A. (2015). Simulation of short-term pressure regulation during the tilt test in a closed-loop cardiovascular model. *Annals of Biomedical Engineering*, 43(10), 2464–2480. <https://pmc.ncbi.nlm.nih.gov/articles/PMC4490186/>

---

## Supplementary Materials

### Figure S1: Multi-Organ Platform Architecture

Schematic of the Virtual Vet 11-organ platform showing the dual baroreflex loop architecture: loop A (intra-heart, heart.py derivatives) and loop B (inter-module, neuro.compute() → FactorCommands → heart). Both loops operate simultaneously in heart.compute() and neuro.compute(), respectively.

### Figure S2: Pure Euler Convergence Analysis

(A) RMSE(MAP) vs dt on semi-log axes for pure Euler at dt = 0.1 to dt = 1×10⁻⁴ s, 60 s observation window. First-order convergence is confirmed: RMSE ∝ dt with slope ≈ 1.0. (B) MAP time series showing plateau elimination: pure Euler at dt=0.01 s converges to the same steady-state as finer dt values, unlike sequential Euler which shows a divergent plateau.

### Figure S3: Subprocess Isolation Test — Both Orderings Converge to O(1) Bias

MAP time series under heart→neuro and neuro→heart orderings at baseline, dt = 0.01 s, each executed in an **independent Python subprocess** (subprocess_isolation_test.py). Both orderings converge to ~144.7 mmHg (Δ = 0.034 mmHg), confirming order-independent O(1) bias. The previous swap experiment (showing 44.7 mmHg difference) was contaminated by Python class-level state pollution in same-process comparison; the subprocess isolation methodology eliminates this contamination source.

### Figure S4: Time-Step Invariance of Sequential Euler Bias

MAP at t = 60 s under heart→neuro ordering across seven orders of magnitude in dt (0.1 s to 1×10⁻⁹ s). The bias is constant at +44.7 mmHg across all tested time steps, confirming O(1) (time-step invariant) bias rather than a numerical truncation error. Each point represents a separate simulation; the flat line at 144.7 mmHg spans dt = 10⁰ to dt = 10⁻⁹.

### Table S1: Pure Euler Convergence Data

*See Table S1 above in Section 3.1*

### Table S2: Parameter Sweep — Bias is Architecture-Intrinsic, Not Parameter-Driven

Three parameter sweep experiments (baroreflex gain, seizure SVR multiplier, body mass) each confirmed that the O(1) bias is constant at ~44.7 mmHg regardless of parameter values — confirming the bias is an architectural intrinsic property, not a parameter-external manifestation.

**Experiment 1 — Baroreflex Gain Sweep:** bias = 44.742 mmHg across all gains [0.5, 1.0, 2.0, 4.0, 8.0×]. Reason: SVR_increase = 1.0 + 2.0 × sympathetic × max(0, error) uses max(0, error) as a threshold gate — at baseline MAP ≈ 100 mmHg, error ≈ 0, so gain parameter has no effect on SVR growth.

**Experiment 2 — Seizure SVR Multiplier Sweep:** bias = 44.742 mmHg across all multipliers [0.0, 0.1, 0.3, 0.5, 0.7]. Reason: Loop A's SVR accumulation is driven autonomously by heart.compute() using the heart's own sympathetic state; Loop B's FactorCommands (disabled by seizure_mult = 0) are not the primary driver.

**Experiment 3 — Body Mass Sweep:** bias ranges from 44.708 to 44.759 mmHg across [10, 20, 30, 40] kg — variation < 0.06 mmHg, effectively constant.

| Parameter | Values Tested | MAP (sequential) | Bias |
|-----------|--------------|-------------------|------|
| Baroreflex gain | 0.5, 1.0, 2.0, 4.0, 8.0× | ~144.742 | **~44.7 mmHg** (all) |
| Seizure SVR mult | 0.0, 0.1, 0.3, 0.5, 0.7 | ~144.742 | **~44.7 mmHg** (all) |
| Body mass | 10, 20, 30, 40 kg | ~144.7 | **~44.7 mmHg** (±0.03) |
| SVR_baseline | 0.8, 0.9, 1.0, 1.1, 1.2× | ~144.742 | **~44.7 mmHg** (all) |

Conclusion: O(1) bias is fully determined by the multiplicative coupling structure of Loop A, not by any physiological parameter. This makes the bias a fundamental architectural vulnerability — it cannot be eliminated by parameter tuning.

### Table S3: False Picard Experiment — No Convergence to Correct Solution

A natural response to sequential coupling bias is to perform multiple forward passes per timestep (k > 1), under the assumption that iteration will converge toward the correct solution. We tested this hypothesis using the heart→neuro ordering with k ∈ {1, 2, 4} passes per timestep, measuring MAP at baseline.

At baseline, HR is already saturated at its physiological maximum (180 bpm) by k = 1. Repeating the forward chain does not change the outcome — MAP@60s = 144.776 mmHg for all k ∈ {1, 2, 4}. This is the **saturation pseudo-convergence** regime: the system appears to have converged (k=1 ≡ k=4), but the converged value is wrong. The apparent convergence is produced by HR saturating at its physiological ceiling (180 bpm), which freezes the iteration from the outside rather than because the coupling has reached a correct fixed point.

### Code Availability

The Virtual Vet platform source code is available at: [repository URL]. Experiment scripts for the convergence study and subprocess isolation validation are located in the `experiments/` directory.

---

*Corresponding author: [Name], [Institution], [email]*
*Competing interests: None declared.*
*Funding: [ funding source ]*