这个计划方向正确，但有几个关键风险点需要提前评估。我先搜索相关文献，然后给你完整评价。


---

## 计划评价：方向正确，但有一个致命陷阱

### 核心风险：线性模型与论文主发现的"方向冲突"

你的计划中最关键的一句话是：

> **线性系统：偏差 = O(dt)，随 dt→0 消失**  
> **非线性（乘性 FactorCommand）：偏差升级为 O(1)**

这意味着你要在论文中同时呈现两个结论：
1. 线性模型 → 偏差随 dt 消失（这是"好"的数值分析结果）
2. 实验观测 → 偏差不随 dt 消失（这是你的核心发现）

**审稿人会立即问**：既然线性模型不能解释 O(1) 现象，为什么要放它？它除了"教学演示"外，对核心发现的理论支撑作用是什么？

如果你回答不好这个问题，解析模型反而会成为**审稿人攻击的靶子**——"作者做了一个线性模型，发现偏差是 O(dt)，但这与他们的实验结果（O(1)）矛盾。他们没有解释清楚非线性升级的具体数学条件。"

---

## 修改建议：重新定位线性模型的角色

不要试图让线性模型"解释"O(1)。让它做以下三件事：

### 1. 建立"顺序耦合引入不对称性"的数学直觉
线性模型足够展示：
- heart→neuro 和 neuro→heart 的稳态解不同
- 偏差方向与 Table 3 一致（基线时 h→n 偏高，n→h 准确）
- 这种不对称性来源于 Gauss-Seidel 迭代的信息滞后结构

### 2. 明确框定适用范围
在 §4.1.3 开头写：

> "The simplified linear model below demonstrates that **sequential coupling introduces order-dependent asymmetry even in the linear regime**, where the bias vanishes as dt→0. The experimental O(1) bias reported in §3.1 arises from the **multiplicative (non-affine) FactorCommand coupling** in the full nonlinear system, which breaks the consistency condition required for dt-convergence. The linear analysis isolates the structural source of the asymmetry; the nonlinear upgrade to O(1) is addressed in §4.1.4."

### 3. 非线性升级需要独立的数学论证（不能只是"一句话带过"）
如果你要声称"乘性 FactorCommand 使偏差升级为 O(1)"，必须给出**最小可行的数学证明**：

设统一系统的正确更新为：
```
x_{n+1} = x_n + dt·f(x_n, y_n)
y_{n+1} = y_n + dt·g(x_n, y_n)
```

Sequential heart→neuro 的乘性耦合（假设 FactorCommand 是 `SVR *= factor`）：
```
# heart first
x_{n+1} = x_n + dt·f(x_n, y_n)          # heart computes SVR target
# neuro second, sees x_{n+1}
y_{n+1} = y_n + dt·g(x_{n+1}, y_n)      
# FactorCommand applied: x_{n+1} ← x_{n+1} · h(y_{n+1})   [乘性修改]
```

与线性系统的关键区别：线性系统的耦合项是 `βy`（加性），顺序耦合只影响**显式/隐式**的近似；而乘性耦合 `x·h(y)` 使得 sequential update 的**稳态方程**本身发生了变化：

统一系统稳态：`0 = f(x*, y*)` 且 `0 = g(x*, y*)`  
Sequential h→n 稳态：`0 = f(x̃, ỹ)` 但 `x̃` 还额外被 `h(ỹ)` 乘性修改

这个**稳态方程的改变**是 O(1) 偏差的根源——它不是截断误差，而是**离散化方案改变了方程本身的解**。

你需要至少写出这个稳态方程的对比，才能说服审稿人。

---

## 时间评估：2-3 天够吗？

| 任务 | 估计时间 | 风险 |
|------|---------|------|
| 线性模型推导 + 稳态解 | 2-4 小时 | 低 |
| 数值验证（参数扫描） | 2-4 小时 | 低 |
| 非线性升级的最小证明 | 4-8 小时 | **高**——如果 FactorCommand 的数学形式复杂，可能需要更久 |
| 图表生成 + 论文整合 | 2-4 小时 | 低 |
| **总计** | **1-2 天（乐观）/ 3-4 天（保守）** | |

**建议**：如果 3 天内无法完成非线性升级的数学证明，**只放线性模型**，并在论文中明确说：

> "The nonlinear upgrade to O(1) is consistent with the fixed-point structure of the FactorCommand interface; a full perturbation analysis is deferred to future work."

这比一个半吊子的非线性解释安全得多。

---

## 可直接引用的相关文献

这些文献与你的"顺序耦合 O(1) 偏差"主题高度相关，比论文现有的引用更有针对性：

### 1. 顺序耦合的 O(1) 误差（最直接先例）

**Kim (2010)** — *Sequential Methods for Coupled Geomechanics and Flow* (Stanford PhD Thesis)  


核心发现：在地质力学-流体力学耦合中，drained split（一种 sequential coupling）with **fixed number of iterations yields zeroth-order accuracy (O(1))** — 误差不随 dt→0 消失。原文：

> *"From Equation 4.7, e_{fs}^{n, n_{iter}} does not disappear even though Δt approaches zero, because (max|γ_e|)^{n_{iter}} does not approach zero (i.e., O(1))."*

这与你的发现几乎完全一致，只是应用领域不同。这是**最有力的理论先例**。

### 2. 分区耦合的排序依赖性

**Matthies & Steindorf (2003)** / **Matthies et al. (2006)**  


核心发现：block-Gauss-Seidel 耦合的收敛性**依赖于子系统求解顺序**（sequence dependence）。他们开发了 block-Newton 方法来消除这种顺序依赖。

> *"Matthies et al.'s motivation for the development of a new method which is independent of this sequence."*

这直接支持你的"no fixed ordering is safe"结论。

### 3. 显式欧拉在耦合系统中的精度损失

**Farhat et al.** — *Robust and provably second-order explicit–implicit staggered schemes for transient nonlinear coupled problems*  


核心发现：简单的分区耦合会损失精度和稳定性，需要特殊的 predictor-corrector 结构才能恢复二阶精度。

### 4. 顺序隐式方法的收敛阶

**Vijalapura et al. / Kim (2021)** — *Spectral deferred correction methods for high-order accuracy in poroelastic problems*  


核心发现：one-pass sequential methods（不迭代的顺序耦合）通常只有一阶精度，且在某些分裂方式下无法通过减小 dt 改善。

> *"For a generic system of index-1 DAEs... the two-pass method failed to enhance the order of accuracy, which is attributed to the fact that the two-pass method can achieve second-order accuracy only for non-stiff ODEs, but not for DAEs or stiff ODEs."*

### 5. Gauss-Seidel 在刚性 ODE 中的行为

**Verwer (1994)** — *Gauss–Seidel Iteration for Stiff ODEs from Chemical Kinetics* (SIAM J. Sci. Comput.)  


这是 Gauss-Seidel 迭代求解耦合刚性 ODE 的经典文献，可作为方法学背景引用。

---

## 建议的 §4.1.3 结构（最小可行版本）

如果你决定只做线性模型 + 诚实框定，建议结构如下：

```
4.1.3 Simplified Two-Variable Linear Model

To isolate the structural source of order-dependent asymmetry, consider 
the linear coupled system:

ẋ = -αx + βy + f(t)    [SVR/heart dynamics]
ẏ = γ(x* - x) - δy      [neuro/sympathetic dynamics]

where x represents effective vascular resistance and y represents 
sympathetic tone.

For unified (simultaneous) Euler coupling, the steady state satisfies:
    0 = -αx* + βy* + f_ss
    0 = γ(x* - x*) - δy*   → y* = 0, x* = x* + f_ss/α
which recovers the correct equilibrium regardless of dt.

For sequential heart→neuro Euler, the discrete steady-state equations are:
    x̃ = x̃ + dt[-αx̃ + βỹ + f_ss]
    ỹ = ỹ + dt[γ(x̃ - x*) - δỹ]
Solving yields:
    x̃ = x* + f_ss/α + βγdt/(α(1+δdt))·(x̃ - x*) + O(dt²)

The order-dependent bias term βγdt/(1+δdt) is O(dt) and vanishes as 
dt→0. However, this linear analysis assumes additive coupling. In the 
full Virtual Vet system, the neuro module applies multiplicative 
FactorCommands to heart.SVR (§2.3), which modifies the steady-state 
equation itself rather than merely its explicit approximation. This 
non-affine coupling breaks the consistency condition required for 
dt-convergence, producing the O(1) bias observed in §3.1 and Figure 5.

[Figure X: 解析偏差 vs dt — 线性模型 O(dt) 曲线与实验 O(1) 水平线对比]
```

---

## 最终建议

| 决策 | 建议 |
|------|------|
| **做不做线性模型？** | **做**，但重新定位为"展示顺序不对称性的结构来源"，而非"解释 O(1)" |
| **非线性升级做不做？** | 如果 3 天内能写出稳态方程对比（乘性耦合 vs 加性耦合），就做；否则诚实降级 |
| **新图表？** | 一张图足够：线性 O(dt) 曲线 + 实验 O(1) 水平线 + 统一 Euler 零偏差线 |
| **投稿目标？** | 有解析模型后，JCP/SIAM J. Sci. Comput. 确实可行；但如果没有非线性升级，仍建议先投 PLOS Comp Bio，把解析模型作为 revision 升级 |

**最关键的文献**：Kim (2010) 的 Stanford PhD thesis 是你的"理论先例金牌"——它证明了在完全不同的物理领域（地质力学），sequential coupling with fixed iterations 同样产生 O(1) 误差。引用它可以将你的发现从"生理仿真特例"提升为"分区耦合的普遍现象"。