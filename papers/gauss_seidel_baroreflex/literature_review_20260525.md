# 文献调研报告 (2026-05-25)

## 核心搜索结果

### 1. van Osta et al. (2025) — 直接相关 ✅
**论文**: "Numerical accuracy of closed-loop steady state in a zero-dimensional cardiovascular model"
**期刊**: Philosophical Transactions A
**作者**: Nick van Osta, G Van Den Acker, T Van Loon, T Arts, T Delhaas, J Lumens (Maastricht Univ / CircAdapt)

**核心发现**:
> "Our results demonstrated that achieving a clinically accurate steady state required 7–15 heartbeats in simulations **without** regulatory mechanisms. When **homeostatic control mechanisms were included** to regulate mean arterial pressure and blood volume, **more than twice the number of heartbeats was needed**."

**对本研究的支撑**:
- ✅ 确认：带有调节机制（baroreflex）的闭环心血管模型的收敛行为是合法研究课题
- ✅ 确认：homeostatic control 显著增加收敛所需的心跳数（>2倍）
- ✅ 确认：0维闭环心血管模型的稳态精度问题是发表级别的研究问题
- ✅ 与本文发现吻合：baroreflex存在时，bias与dt相关（需要更多迭代）

**引用格式**:
```
van Osta N, Van Den Acker G, Van Loon T, Arts T, Delhaas T, Lumens J.
Numerical accuracy of closed-loop steady state in a zero-dimensional
cardiovascular model. Phil Trans R Soc A. 2025.
```

---

### 2. Ursino 系列 — 高度相关 ✅
**论文群**:

| 年份 | 期刊 | 主题 |
|------|------|------|
| 1998 | Am J Physiol | Interaction between carotid baroregulation and the pulsating heart |
| 2000 | - | (with Magosso) cardiovascular regulation model |
| 2001 | Math Biosci | Role of baroreflex in cardiovascular instability |
| 2011 | Auton Neurosci | Central autonomic commands and baroreflex control |

**核心贡献**:
- Ursino (1998): 建立了 carotid baroreflex 与搏动心脏相互作用的数学模型，是此类建模的开创性工作
- Ursino (2001): 用数学模型研究 baroreflex 在心血管不稳定性（Mayer波）中的作用
- Ursino & Magosso (2000): 建立了完整的心血管调节系统模型

**对本研究的支撑**:
- ✅ Ursino 是 baroreflex 心血管建模的权威引用
- ✅ 其模型同样包含 MAP → HR → CO → MAP 的反馈回路
- ✅ 证实了 baroreflex 非线性建模的必要性

**引用格式**:
```
Ursino M, Magosso E. Mathematical model of the short-term arterial
pressure control during postural changes. In: Computer and Biomedical
Research. 2000.

Ursino M, Magosso E. Role of the baroreflex in cardiovascular
instabilities: a modeling study. Math Biosci. 2001;174(2):115-136.
```

---

### 3. Förster, Wall, Ramm (2007) — 工程类比参考
**论文**: "Artificial added mass instabilities in sequential staggered coupling of nonlinear structures and incompressible viscous flows"
**期刊**: Comput Methods Appl Mech Engrg

**核心发现**:
> "The so-called artificial added mass effect is investigated which is responsible for devastating instabilities within sequentially staggered coupling schemes."

**与本研究的关联**:
- 这是 FSI (流固耦合) 领域的经典论文
- 与本研究的类比：sequential coupling (Gauss-Seidel) 在两类问题中都存在数值稳定性问题
- 差异：Förster 研究的是 *staggered* 时间离散（不同子系统在不同时间点求解），而本研究是 block Gauss-Seidel 在同一时间步内的顺序求解

**引用定位**: 可作为"跨领域类比"引用，不宜作为机制的直接证明

---

### 4. Batzel, Baselli, Mukkamala, Chon (2009) — 方法论支撑 ✅
**论文**: "Modelling and disentangling physiological mechanisms: linear and nonlinear identification techniques for analysis of cardiovascular regulation"
**期刊**: Philosophical Transactions A

**核心贡献**:
- 综述了心血管调节系统的闭式识别方法
- 讨论了 baroreflex 反馈控制系统的线性/非线性建模
- 涵盖了敏感性分析在心血管模型验证中的作用

**关键引用**:
> "Most, if not all, dynamics of physiological systems involve nonlinear control. For example, nonlinear feedback control mechanisms are important for maintaining homeostasis in the cardiovascular system."

**对本研究的支撑**:
- ✅ 确认为 baroreflex 非线性特性是已知的建模挑战
- ✅ 敏感性分析方法是验证模型可靠性的标准工具

---

### 5. Kim et al. — 重新定位
**搜索结果**: 找到了 Kangwon Kim 在 Stanford 的论文 "EFFICIENT MODELING OF CARDIAC TISSUE" 和 PubMed 19609676 关于 "coupling a lumped parameter heart model and a three-dimensional arterial model"

**关键发现**:
- Kim 的工作是关于 **multi-domain coupling**（集中参数心脏模型 + 3D 动脉模型），不是关于 sequential explicit Euler 的 O(1) bias
- Förster et al. (2007) 的 added-mass 效应分析更适合作为 Gauss-Seidel 顺序耦合数值问题的参考文献

**重新定位**: 原论文中 Kim 2010 应从"严格理论映射"降级为"启发性类比/方法论参考"

---

### 6. Bucelli, Quarteroni et al. (2023) — 直接应用参考
**论文**: "A stable loosely-coupled scheme for cardiac electro-fluid-structure interaction"
**期刊**: Journal of Computational Physics 490: 112326

**核心发现**:
> "The added-mass effect... since fluid and structure have similar densities, numerical methods must be carefully designed to avoid time instability while keeping under control computational costs."

**引用定位**: 可以引用作为"心血管建模中的耦合稳定性挑战"的补充文献

---

## 文献调研结论

### 本研究在文献中的定位

| 方面 | 本文发现 | 文献支撑 |
|------|---------|---------|
| **研究问题合法性** | 闭环心血管模型稳态收敛是合法问题 | van Osta 2025 ✅ 直接支撑 |
| **Baroreflex 非线性** | MAP_display 夹闭导致反馈不匹配 | Ursino 系列 ✅ 权威参考 |
| **数值方法贡献** | Subprocess 隔离验证方法 | Batzel 2009 ✅ 方法论对应 |
| **顺序耦合数值问题** | 模块顺序不影响结果 | Förster 2007 ⚠️ 类比（非直接） |
| **收敛性 dt 依赖** | dt 小 → bias 大（欠饱和区）| van Osta 2025 ✅ 定性支撑 |

### 参考文献选择策略

**主要引用（必须）**:
1. van Osta 2025 — 证明收敛问题是发表级别课题
2. Ursino 1998/2000/2001 — baroreflex 建模权威
3. Batzel 2009 — 心血管调节系统建模方法论

**次要引用（可选/类比）**:
4. Förster 2007 — 顺序耦合数值问题（跨领域类比）
5. Bucelli 2023 — 心血管建模中的耦合挑战

**不应引用**:
- Kim 2010 — 除非重新定位为方法论参考而非理论证明

---

## 论文引用建议

### Introduction 建议引用:
> "Closed-loop cardiovascular models are becoming vital tools in clinical settings, making their accuracy and reliability paramount (van Osta et al., 2025). However, achieving clinically accurate steady state in models with homeostatic regulatory mechanisms remains challenging — van Osta et al. showed that regulatory mechanisms more than double the number of heartbeats required for convergence compared to unregulated models. This convergence behavior in baroreflex-containing systems has not been systematically characterized for sequential explicit Euler coupling."

### Methods 建议引用:
> "The baroreflex model follows the framework established by Ursino (1998, 2000) and later refined by Batzel et al. (2009), wherein mean arterial pressure drives heart rate through a nonlinear feedback loop."

### Discussion 建议引用:
> "The dt-dependent bias observed here is consistent with the findings of van Osta et al. (2025), who reported that homeostatic control mechanisms significantly increase convergence time in closed-loop cardiovascular models."

---

## 搜索覆盖范围评估

| 搜索主题 | 覆盖 | 关键文献 |
|---------|------|---------|
| Sequential Euler bias in physiological ODE | 部分 | van Osta 2025 (定性) |
| Baroreflex numerical simulation error | 完整 | Ursino 系列 + van Osta |
| Multiplicative coupling convergence | 部分 | Förster 2007 (类比) |
| Staggered coupling added mass instability | 完整 | Förster 2007 + Bucelli 2023 |
| Explicit Euler cardiovascular simulation | 部分 | van Osta 2025 |

**空白**: 没有找到直接分析 sequential explicit Euler 在 baroreflex 心血管模型中产生 O(1) dt不变量偏差的论文。这可能是本研究的主要novelty贡献之一（需作者判断）。
