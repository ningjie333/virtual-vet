## FactorCommand 无关。偏差完全来自顺序耦合本身。

---

### 2×2 完整结果

| | 有 FactorCommand | 无 FactorCommand |
|---|---|---|
| **Sequential** | 144.776 | 144.776 |
| **Unified** | ~100.0 | ~100.0 |

```
FactorCommand 的贡献 = 0.000 mmHg

偏差 100% 来自顺序耦合的 Gauss-Seidel 结构。
```

---

### 这意味着什么

```
之前所有关于"FactorCommand 累积"、"chemoreceptor 驱动"、
"Loop B 的 FactorCommand 是偏差来源"的讨论——全部错误。

偏差的根因是最朴素的结构：

  Sequential：模块 A 更新状态 → 模块 B 读了 A 更新后的状态 → 产生一步信息超前
  Unified：所有模块读同一个 state_n → 无信息超前

这正好是 Kim 研究的东西。Kim 没有 FactorCommand，Kim 也有 O(1) 偏差。
你的系统没有 FactorCommand 也有 O(1) 偏差。
→ 同一个数学结构，不同的物理外衣。
```

---

### 但这引出一个更深的谜：什么在驱动 HR→180？

```
FactorCommand 被禁用了，HR 仍然到 180。
驱动力只能是 Loop A——heart 内部的 baroreflex。

T2 说 step 1 的 error = -0.10（MAP 高于 target）→ 副交感抑制
如果 error 一直是负的 → HR 应该下降 → 不应该到 180

两种可能：

1. error 在后续步骤中翻转了符号
   → 需要看 step 2-60 的 trace

2. sympathetic 变量有自己的动力学正反馈
   → 即使 error=0，sympathetic 也可能漂移
   → 这才是偏差的真正微观机制
```

---

### 我的判断：论文现在比之前更强

```
之前：偏差可能来自 FactorCommand（实现层面）
      → 审稿人可以说"换个实现就好了"

现在：偏差来自 Gauss-Seidel 结构（数学层面）
      → 审稿人无法说"换个实现就好了"
      → 这是和 Kim 同一层面的结论

之前：和 Kim 的映射有矛盾（参数不敏感、低耦合时不稳定）
      → 令人不安

现在：FactorCommand 被排除后，这些矛盾可能消失
      → 因为之前的"矛盾"可能是 FactorCommand 的干扰
      → 需要重新验证参数扫描（无 FactorCommand 条件下）
```

---

### 但有一个新风险需要警惕

```
如果偏差完全来自 Gauss-Seidel 结构，为什么参数扫描全部 44.742？

Kim 的理论：Gauss-Seidel 偏差 ∝ 耦合强度
如果偏差 ∝ 耦合强度，改变 gain 应该改变偏差
但你的数据：改变 gain 不改变偏差

可能的解释：

1. 所有参数变化都没有改变"有效耦合强度"
   → 因为 HR 已经饱和 → 系统在饱和区运行
   → 饱和区内的耦合强度是常数
   → 参数变化被饱和吸收

2. 偏差不是 ∝ 耦合强度，而是由饱和约束的固定点决定
   → MAP = CO × SVR / 60, CO = HR_max × SV
   → HR_max = 180 → MAP 由 HR_max 和 SV 完全决定
   → SVR_baseline 变化不影响 MAP（因为 HR 已经饱和）
   → gain 变化不影响 MAP（同上）

如果是这样：
  偏差 44.742 = HR_max × SV / 60 × something - 100
  → 这是一个由硬约束决定的常数
  → 不是 Gauss-Seidel 误差的渐进行为
  → 和 Kim 的"偏差 ∝ coupling"不同
```

---

### 两个需要回答的问题

```
问题 1：无 FactorCommand 条件下的参数扫描

  禁用 FactorCommand 后：
    gain = 0.5 → MAP = ?
    gain = 8.0 → MAP = ?
  
  如果仍然全部 44.742 → 饱和约束主导，不是 Kim 型误差
  如果随 gain 变化 → Gauss-Seidel 误差主导，和 Kim 对齐

  这个实验决定论文和 Kim 的关系。

问题 2：无 FactorCommand 条件下的 dt 扫描

  禁用 FactorCommand 后：
    dt = 0.1  → MAP = ?
    dt = 0.001 → MAP = ?
    dt = 10⁻⁶ → MAP = ?
  
  如果偏差随 dt 变化 → 不是 O(1) → 和之前的结论矛盾
  如果偏差不随 dt 变化 → O(1) 确认 → 但需要解释为什么
```

---

### 论文定位的两种走向

```
走向 A（如果参数扫描在无 FactorCommand 下随 gain 变化）：

  "Sequential Gauss-Seidel coupling in nonlinear physiological
   systems produces O(1) bias, consistent with Kim et al.'s
   drained split analysis. The bias depends on effective
   coupling strength and is independent of time step size.
   FactorCommand post-modification does not contribute to
   the bias — it is purely a structural property of the
   coupling scheme."

  → 和 Kim 对齐，投 CMAME
  → 原创贡献：跨领域验证 + 伪收敛 + FactorCommand 排除实验

走向 B（如果参数扫描在无 FactorCommand 下仍然恒定）：

  "Sequential Gauss-Seidel coupling in nonlinear systems with
   variable saturation produces an order-independent, parameter-
   insensitive O(1) bias. The bias is determined by the
   saturation constraint's modified fixed point, not by coupling
   strength. This differs from Kim et al.'s linear framework
   where bias scales with coupling strength."

  → 超越 Kim，投 CMAME
  → 原创贡献：饱和约束产生新的偏差动力学 + 伪收敛 + 参数不敏感

  → 但需要更强有力的理论解释
```

**我倾向走向 B 更可能——因为之前的参数扫描已经显示恒定 44.742，而 FactorCommand 被排除并不改变这个结果。** 但这只是猜测，需要实验确认。

**先跑无 FactorCommand 下的 gain 扫描。10 分钟。结果决定论文走向。**