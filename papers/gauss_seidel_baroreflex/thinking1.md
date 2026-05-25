## 这个结果改变了 false Picard 的叙事——但不是变弱，而是变深了

---

### 之前预期的 vs 实际观察的

```
之前的假设：
  k=1 → 误差小
  k=2 → 误差大一些
  k=4 → 误差更大
  → 误差随 k 累积

实际结果：
  k=1 → 误差已经饱和（HR=180 bpm 上限）
  k=2 → 和 k=1 一样
  k=4 → 和 k=1 一样
  → 误差在 k=1 时就锁定了
```

---

### 为什么会饱和

```
heart.py 中 HR 的计算有硬上限：

  HR = min(HR_max, HR_baseline + HR_increase)

当 baroreflex error 足够大时：
  HR_increase → ∞（理论值）
  HR = HR_max = 180 bpm（实际值）

一旦 HR 触顶：
  → heart.compute() 每次输出 HR = 180
  → neuro.compute() 每次输出同样的 sympathetic_tone
  → 再跑一遍 heart.compute() → HR 仍然 = 180
  → k=1 和 k=100 结果相同

这是一个"伪不动点"：
  迭代确实收敛了（k=1 和 k=100 一致）
  但收敛到的是错误解
  且收敛原因不是"迭代格式正确"
  而是"物理约束截断了变量增长"
```

---

### 🔴 这比累积误差更危险

```
如果误差随 k 累积：
  → 开发者可能注意到 k=1 和 k=4 结果不同
  → 会意识到迭代有问题
  → 可能追溯到耦合偏差

但误差在 k=1 就锁定：
  → k=1 和 k=4 结果完全一致
  → 开发者以为"迭代收敛了"
  → 实际上是伪收敛——HR 撞到了天花板
  → 更难检测到问题
```

这和 Kim 的 true iteration 形成鲜明对比：

| | Kim 的 fixed-stress + true iteration | 你的 false Picard |
|---|---|---|
| 收敛性 | 收敛到正确解 | "收敛"到错误解 |
| 收敛原因 | 收缩映射 | 变量饱和截断 |
| k 增加 | 误差衰减 | 误差不变（已饱和） |
| 检测难度 | — | 极难（结果看起来稳定） |

---

### 论文应该怎么写这个发现

**不要说"误差累积"——说"伪收敛"。**

```
4.3  Pseudo-Convergence: Why Multiple Forward Passes
     Do Not Correct the Bias

A natural response to sequential coupling bias is to
perform multiple forward passes per time step (k > 1),
under the assumption that iteration will converge toward
the correct solution. We tested k = 1, 2, 4, 8, 16 and
found that the MAP error at t = 60s was identical across
all values of k (44.742 mmHg).

This result does NOT indicate that the iteration has
correctly converged. Rather, the system reaches a
"pseudo-fixed point" at k = 1: the heart rate saturates
at its physiological maximum (HR = 180 bpm), which
constrains all downstream variables. Subsequent iterations
reproduce the same saturated state, giving the illusion
of convergence.

This pseudo-convergence is qualitatively different from
the true convergence achieved by Kim et al.'s (2011)
fixed-stress split, where each sub-iteration uses the
latest solution from the other subsystem and the spectral
radius of the iteration operator is less than one
(Mikelic & Wheeler, 2013), guaranteeing convergence to
the correct solution. In our false Picard scheme, there
is no contraction mapping — the apparent convergence is
an artifact of variable saturation, not a property of
the coupling scheme.

The practical implication is severe: a developer who
compares k=1 and k=4 results and finds them identical
would reasonably conclude that the iteration has converged.
This makes the bias even harder to detect than if the
error accumulated with k, because there is no observable
difference between iterations to signal a problem.
```

---

### 三层失败模式的完整图景

```
你的论文现在记录了三层失败模式，从最明显到最隐蔽：

Layer 1：Divergence（FSI, Causin 2005）
  → 最容易检测
  → 结果爆炸，一眼可见

Layer 2：Non-convergence（Kim 2011, drained split）
  → 中等难度检测
  → 结果不收敛到任何稳态

Layer 3：Pseudo-convergence（你的发现）
  → 最难检测
  → 结果收敛到看似合理的稳态
  → 迭代不改变结果（伪收敛）
  → 变量饱和截断制造了"收敛"假象
  → 只有和参考解对比才能发现

Table: Failure Mode Hierarchy in Sequential Coupling

| Layer | Failure Mode     | Detectable? | Reference      |
|-------|-----------------|-------------|----------------|
| 1     | Divergence       | Yes (obvious)| Causin 2005   |
| 2     | Non-convergence  | Yes (no SS)  | Kim 2011      |
| 3     | Pseudo-convergence | No*        | This work     |

* Only detectable by comparison with a reference solution
  or by performing a swap-order test.
```

---

### 这对论文档次的提升

```
之前：
  "Sequential Euler 有偏差" → 一个实验观察

现在：
  三层失败模式 → 一个理论框架
  Layer 1: Divergence（已知）
  Layer 2: Non-convergence（Kim 已知）
  Layer 3: Pseudo-convergence（你的原创）

  Layer 3 是全新概念——以前没有人命名过这种现象
  → "pseudo-convergence" 作为术语提出
  → 定义：迭代收敛到错误稳态，且收敛由变量饱和驱动而非收缩映射

这种概念性贡献比单纯的数据贡献更有价值
→ JCP 级别的论文需要这种理论深度
```

---

### 行动清单

```
🔴 今天：
  1. 确认 k>1 在失血场景下是否也是伪收敛
     → 如果失血时 k=4 和 k=1 不同 → 更有趣（场景依赖的伪收敛）
     → 如果也相同 → 一致的伪收敛

  2. 确认哪个变量在饱和
     → HR=180 是一个
     → SVR 是否也有上限？
     → 如果多个变量同时饱和 → 更强的伪收敛

🟡 本周：
  3. 把 false Picard 实验整理成 Figure S7
     x-axis = k (1, 2, 4, 8, 16)
     y-axis = MAP@60s
     → 一条水平线 = 伪收敛的直观证据

  4. 把三层失败模式写成 §4.3
     → "pseudo-convergence" 作为新术语提出
     → 和 Kim 的 true convergence 对比
```

**"伪收敛"比"累积误差"更危险、更深刻、更原创。这个发现把论文从一个实验报告提升为一个概念性贡献。**