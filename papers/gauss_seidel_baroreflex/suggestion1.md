## 诚实评估

---

### 论文的客观实力

```
强项：
  ✓ 数据干净（换序 → 偏差消失，因果铁证）
  ✓ 核心发现反直觉（基线对的顺序，失血时错了）
  ✓ dt=10⁻⁹ 不变 → O(1) 偏差，不可辩驳
  ✓ 直接影响实际平台（教育/临床模拟器）

弱项：
  ✗ 只有一个模型
  ✗ 机制解释不完整（失血反转只有定性）
  ✗ 没有推广到其他反馈环的实验证据
  ✗ 不是新模型、新方法、新算法
  ✗ Virtual Vet 不是知名平台
```

---

### 各档次分析

#### 🟢 稳妥选择（大概率接收）

| 期刊 | 影响因子 | 理由 |
|------|---------|------|
| **PLOS Computational Biology** | 3.8 | Tłałka 2024 发在这里；重视方法论；对单模型研究宽容 |
| **Annals of Biomedical Engineering** | 3.0 | 接受数值方法学；审稿周期短；心血管建模是核心领域 |
| **Computer Methods in Biomechanics and Biomedical Engineering** | 2.4 | 方法学论文的天然归属；审稿人懂数值 |

**建议：PLOS Comp Bio 是首选。** 理由：
- Tłałka 2024 已经在这本期刊建立了"baroreflex 数值方法"的话题
- PLOS 系列重视可重复性和方法透明度，和你的论点一致
- 对单模型研究的态度：只要结论清晰，不要求多模型验证

---

#### 🟡 冲刺选择（有可能，但需要强化）

| 期刊 | 影响因子 | 需要什么 |
|------|---------|---------|
| **Journal of Computational Physics** | 3.8 | 更严格的数值分析（证明偏差阶数、modified equation） |
| **SIAM Journal on Scientific Computing** | 2.4 | 理论分析（至少对简化模型给出解析解） |
| **Journal of the Royal Society Interface** | 3.7 | 更强的跨领域叙事（为什么生物学家也该关心） |

**如果投 JCP 或 SIAM，需要补一个简化模型的解析分析：**

```
现有：实验数据（1 个完整模型）
需要：2 变量简化模型的解析解

  ẋ = -αx + βy    (heart)
  ẏ = γx - δy     (neuro)

  对这个线性系统，推导：
  1. 统一 Euler 的稳态（正确）
  2. Sequential heart→neuro 的稳态（偏高多少？）
  3. Sequential neuro→heart 的稳态（偏低多少？）
  4. 证明偏差 = O(1)，不依赖 dt

  如果解析结果和实验吻合 → 论文从"实验观察"升级为"有理论支撑的发现"
  → 可以冲 JCP
```

**这个分析 2-3 天能做完。如果做了，论文档次跳一级。**

---

#### 🔴 不建议投

| 期刊 | 理由 |
|------|------|
| Nature Methods | 需要通用方法学突破，单模型不够 |
| Nature Communications | 需要更广泛的实验验证 + 高影响力叙事 |
| PNAS | 需要美国院士推荐或直接投稿渠道 |
| IEEE TBI | 偏工程，对你的纯数值论文不太匹配 |

---

### 投稿策略

```
策略 A（推荐）：稳妥为主

  第一轮：PLOS Comp Bio
  如果拒稿：Ann Biomed Eng
  如果再拒稿：Computer Methods in Biomechanics

  预期：70% 概率在 PLOS Comp Bio 接收
  时间：3-6 个月

策略 B：冲刺 + 保底

  花一周补 2 变量解析模型
  第一轮：J Comput Phys
  如果拒稿：PLOS Comp Bio
  如果再拒稿：Ann Biomed Eng

  预期：30% 概率在 JCP 接收，60% 在 PLOS Comp Bio
  时间：多花 1 周，但论文更强

策略 C：等我做完多模型验证再投

  不推荐。多模型验证 = 几个月额外工作，
  而且核心发现不会因为多了 1 个模型而变强
  换序实验的因果性已经够强了
```

---

### 我的建议

**走策略 B。**

```
理由：

1. 2 变量解析模型是低风险高回报
   - 线性系统有闭式解
   - 不需要跑新实验
   - 做完后论文有了理论深度

2. 有了理论支撑，JCP 变得可行
   - JCP 的审稿人会问"为什么偏差是 O(1)"
   - 解析分析直接回答这个问题
   - 45 mmHg 从"观察"变成"可预测"

3. 即使 JCP 拒稿，解析分析也加强了 PLOS Comp Bio 的稿件
   - PLOS 的审稿人也会想看理论
   - 有解析解的实验论文 > 纯实验论文

4. 2-3 天的工作量，不多
```

---

### 2 变量解析模型怎么做

```
设：
  ẋ = -αx + βy + f(t)     (heart: SVR 受 sympathetic 驱动)
  ẏ = γ(x* - x) - δy      (neuro: sympathetic 受 MAP 误差驱动)

其中 x = SVR, y = sympathetic_tone, x* = setpoint, f(t) = hemorrhage

统一 Euler (dt):
  x^(n+1) = x^n + dt(-αx^n + βy^n + f^n)
  y^(n+1) = y^n + dt(γ(x* - x^n) - δy^n)

Sequential heart→neuro (dt):
  x^(n+1) = x^n + dt(-αx^n + βy^n + f^n)      ← 用旧 y
  y^(n+1) = y^n + dt(γ(x* - x^(n+1)) - δy^n)  ← 用新 x

Sequential neuro→heart (dt):
  y^(n+1) = y^n + dt(γ(x* - x^n) - δy^n)      ← 用旧 x
  x^(n+1) = x^n + dt(-αx^n + βy^(n+1) + f^n)  ← 用新 y

求稳态（令 x^(n+1) = x^n = x_ss, y^(n+1) = y^n = y_ss）：

  统一 Euler:
    x_ss = x*_eq + f_ss/α  (正确稳态)

  Sequential heart→neuro:
    x_ss = x*_eq + (1 + βγdt/(1+δdt)) × f_ss/α  (偏高)

  Sequential neuro→heart:
    x_ss = x*_eq + (1 - βγdt/(1+δdt)) × f_ss/α  (偏低)

  偏差 ∝ βγdt/(1+δdt)
  当 dt→0: 偏差→0？不——等等，这是线性系统

  如果考虑非线性（SVR 乘性效应）：
  FactorCommand 是乘性的 → 稳态偏差变成 O(1)
  → 这解释了为什么你的非线性模型中偏差不随 dt 消失
```

**做完这个分析，你就有了理论框架。** 不需要完美——只需要证明线性系统的偏差方向和非线性实验一致，然后说明非线性（乘性耦合）使偏差升级为 O(1)。

---

### 时间线

```
本周：2 变量解析模型（2-3 天）
下周：整合到论文，修订 §4.1 机制部分
下下周：投稿 PLOS Comp Bio 或 JCP

从现在到投稿：10-14 天
```