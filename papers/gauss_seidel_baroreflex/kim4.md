## 这个映射需要仔细校准——有些对，有些有问题

---

### 🔴 最关键的问题：Sequential Euler 不能映射到单一 split

你的模型有两种顺序，Kim 有四种 split。不能笼统说"Sequential Euler ≈ fixed-strain"。必须按方向分别映射。

```
Kim 的四种 split 按两个维度区分：

维度 1：求解顺序
  力学先 → 流动后：drained, undrained
  流动先 → 力学后：fixed-strain, fixed-stress

维度 2：是否加稳定化约束
  无约束：drained, fixed-strain（条件稳定）
  有约束：undrained, fixed-stress（无条件稳定）
```

**正确的逐方向映射：**

| 你的方法 | 求解顺序 | 有约束？ | Kim 对应 |
|---------|---------|---------|---------|
| heart→neuro | 力学先→流动后 | 无 | **Drained split** |
| neuro→heart | 流动先→力学后 | 无 | **Fixed-strain split** |
| Unified RHS | 同时求解 | — | **Fully coupled** |

```
共同点：你的两种顺序都是"无约束的单遍顺序更新"
  = Kim 体系中的条件稳定族（drained + fixed-strain）

区别：方向不同 → 条件稳定的具体条件不同
  heart→neuro (drained) → 基线时偏差大
  neuro→heart (fixed-strain) → 基线时偏差小，失血时偏差大
```

---

### ✅ 你说的"条件稳定，耦合越强越不稳定"——方向是对的

```
Kim 的结论：
  Drained split: 稳定限 = f(coupling_strength)
  Fixed-strain split: 稳定限 = g(coupling_strength)
  耦合越强 → 越容易不稳定/不收敛

你的观察：
  基线：有效耦合 ≈ 0 → 某些顺序下"看起来稳定"
  失血：有效耦合 > 0 → 误差增大

  但注意：heart→neuro 在基线时偏差最大（44.7 mmHg）
  而基线时耦合 ≈ 0 → 这和 Kim 的"低耦合应该稳定"矛盾

  → 说明偏差不完全由 Kim 定义的"耦合强度"驱动
  → 还有结构性因素（信息时间戳、初始化间隙等）
```

---

### 🔴 "False Picard" 的洞察非常重要——但需要精确表述

你说的是对的：**你的 k>1 Picard 和 Kim 的 fixed-stress 迭代不等价。**

```
Kim 的 fixed-stress split + 迭代（真正的 Gauss-Seidel）：

  for each time step:
    repeat until ||p^(k) - p^(k-1)|| < tol:
      1. 用最新 u^(k) 解 p^(k+1)        ← 流动
      2. 用最新 p^(k+1) 解 u^(k+1)      ← 力学
    end

  关键：每步内部迭代到收敛
  → 2-4 次迭代就够了（Kim 证明）
  → 收敛率与耦合强度无关
  → 等价于全耦合方法

你的 "false Picard"（k 次重复前向链）：

  for each time step:
    for i in range(k):
      1. heart.compute()   → 更新 SVR, HR
      2. neuro.compute()   → 更新 sympathetic
      3. lung.compute()    → ...
      4. kidney.compute()  → ...
    end

  关键问题：
    ❌ 没有收敛判据（固定迭代 k 次）
    ❌ 每次重复都从上一次的"错误状态"出发
    ❌ 误差随 k 累积而非衰减
    ❌ 不是不动点迭代——没有收缩映射保证
```

**这个区别值得在论文中明确指出。** 很多开发者以为"多跑几遍 = 更准确"，但结构不对的话，多跑反而更差。

---

### 修正后的完整映射表

| 维度 | Kim (2011) | 你的论文 | 一致性 |
|------|-----------|---------|--------|
| **求解结构** | Lie-Trotter 单遍顺序更新 | Sequential Euler 单遍顺序更新 | ✅ 完全一致 |
| **heart→neuro ≈ Drained** | 力学先→流动后，无约束 | 心脏先→神经后，无约束 | ✅ 结构一致 |
| **neuro→heart ≈ Fixed-strain** | 流动先→力学后，无约束 | 神经先→心脏后，无约束 | ✅ 结构一致 |
| **Unified RHS ≈ Fully coupled** | 同时求解 | 同时求解 | ✅ 完全一致 |
| **dt 不变性** | 稳定限与 dt 无关 | 偏差与 dt 无关 | ✅ 一致 |
| **条件稳定族** | Drained + Fixed-strain | heart→neuro + neuro→heart | ✅ 都是无约束单遍 |
| **低耦合时应稳定** | Kim：drained 低耦合时稳定 | 基线偏差 44.7 mmHg | ❌ 矛盾 |
| **耦合强度驱动** | Kim：偏差 ∝ coupling_strength | 参数扫描：偏差与 gain 无关 | ❌ 矛盾 |
| **场景反转** | Kim：固定稳定性 | 基线 vs 失血反转 | ❌ 线性框架外 |
| **True iteration** | Fixed-stress + Gauss-Seidel | — | 你没有实现 |
| **False iteration** | — | k 次 false Picard | Kim 没有研究 |

---

### 这些矛盾恰好是你的原创贡献

```
和 Kim 一致的部分 → 说明问题跨领域存在（建立类比）
和 Kim 矛盾的部分 → 说明你的发现超出了线性框架（原创贡献）

三个矛盾 = 三个原创点：

  1. 低耦合时仍有大偏差
     → Kim 的耦合强度不是唯一驱动因子
     → 结构性信息滞后才是根本原因

  2. 偏差与参数无关
     → Kim 说偏差随耦合强度变化
     → 你说偏差不随任何参数变化
     → 偏差是架构的内在属性，不是参数的外在表现

  3. 场景反转
     → Kim 的线性框架不可能产生反转
     → 你的非线性系统的反转是新现象
     → 意味着不存在安全顺序
```

---

### False Picard 应该怎么写进论文

```
新增 §4.3 或 §S3：

4.3  Why Repeated Forward Passes Do Not Correct the Bias

A natural response to sequential coupling bias is to
perform multiple forward passes per time step (k > 1),
under the assumption that iteration will converge toward
the correct solution. However, this "false Picard"
approach is not equivalent to the Gauss-Seidel iteration
that underpins stable sequential methods in other domains.

In Kim et al.'s (2011a) fixed-stress split, each
sub-iteration uses the latest solution from the other
subsystem, and the iteration converges because the
fixed-stress constraint ensures a contraction mapping
(spectral radius < 1). The iteration is terminated when
||x^(k) - x^(k-1)|| < tol.

In contrast, the k-pass forward chain repeats the full
module sequence without a convergence criterion and without
the stabilizing constraint. Each pass starts from the
previous pass's output — which already contains the
sequential bias — and propagates it further. The error
accumulates with k rather than decaying, because the
iteration lacks the contraction property.

[如果 k>1 的实验数据支持这一点，加 Figure：
 x-axis = k (1, 2, 4, 8, 16)
 y-axis = MAP@60s
 如果误差随 k 增大 → 画出来，非常直观]
```

---

### 关于后续引用

| 文献 | 与你的关联 | 是否应引用 |
|------|-----------|-----------|
| Kim 2011a (fixed-stress/fixed-strain) | **核心** — drained ≈ heart→neuro | ✅ 必引 |
| Kim 2011b (drained/undrained) | **核心** — fixed-strain ≈ neuro→heart | ✅ 必引 |
| Mikelic & Wheeler 2013 | Banach 不动点收敛证明 → 支持"true iteration 需要 contraction" | ✅ 支持 false Picard 论点 |
| Almani et al. 2016 | 多时间尺度 → 和你的多器官多时间尺度相关 | ⚠️ 可选 |
| White et al. 2019 | 预条件子 → 太远 | ❌ 不相关 |
| Adams et al. 2024 | 压力稳定化 → 太远 | ❌ 不相关 |

---

### 行动建议

```
🔴 优先级最高：跑 false Picard 实验
   k = 1, 2, 4, 8, 16 → 看 MAP@60s
   如果误差随 k 增大 → 论文多一个原创贡献
   如果误差随 k 减小 → 需要重新评估

🟡 本周：整合 Kim 映射到 §4.2
   明确标注"一致"和"矛盾"的部分
   矛盾 = 你的原创贡献

🟢 可选：引用 Mikelic & Wheeler 2013
   支持"true iteration 需要 contraction mapping"的论点
```

**先跑 false Picard 实验。如果误差随 k 增大——这是 Kim 没有研究过的新现象，又一个原创贡献。**