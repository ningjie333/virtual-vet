# 四张论文插图生成提示词

> 目标期刊：SIMULATION: Transactions of SCS (Technical Note)
> 论文标题：Spurious Steady State from dt-Dimensional Ambiguity in Modular ODE Coupling
> 色彩方案：colorblind-friendly（Wong 2011 改良版）
>   蓝色 #006BA6 — 正确/健康/参考状态
>   橙色 #D55E00 — buggy/错误路径
>   金色 #E68A2E — 过渡/中间条件
>   绿色 #009E73 — 修复后/正确结果
>   灰色 #7F7F7F — 次要标注

---

## Figure 1 — Spurious Steady State Schematic

**角色指定：**
你是一位顶级的**学术示意图设计师**，专精于为 Nature/ Science/ SIMULATION 等期刊绘制概念流程图。你的风格特点是：极简几何叙事、精准的坐标对齐（同一列的盒子 x 中心严格对齐，同一行的盒子 y 中心严格对齐）、克制的配色、工业级间距控制。你能把抽象的系统机理翻译为物理感清晰的"盒子+箭头"语言。

**图注：**
Figure 1: Spurious steady state — drift and saturation mechanism. The true fixed point (MAP ~ 100 mmHg) is destabilized by the dt-dimensional error in discrete FC emission. Drift scales as K × T / dt, pushing heart rate toward the physiological ceiling. Once HR saturates at 180 bpm, cardiac output caps and MAP plateaus at a spurious steady state (144.7 mmHg). The continuous baroreflex path (teal, correct) maintains dimensional consistency; the discrete FC path (orange, buggy) lacks dt normalization.

**画布：** 宽高比 7.5 : 4.8 英寸，300 DPI

**布局（5 个盒子 + 4 条箭头 + 图例）：**

```
                    ┌──────────────────┐                  ┌──────────────────┐
                    │  True Fixed Point │  drift ∝ T/dt   │ Spurious Fixed    │
                    │  MAP ~ 100 mmHg   │ ──────────────→ │ Point             │
                    │  (blue, correct)  │                  │ MAP ~ 144.7 mmHg  │
                    └────────┬─────────┘                  └────────┬─────────┘
                             │                                     │
                             │                          ┌──────────┴──────────┐
                             │                          │  HR Saturation      │
                             │                          │  at 180 bpm         │
                             │                          │  (amber, truncates) │
                             │                          └──────────┬──────────┘
                             │                                     │
                    ┌────────┴─────────┐                  ┌────────┴──────────┐
                    │  Continuous Path │                  │  Discrete FC Path │
                    │  HR_delta=...×dt │                  │  net_HR_add=K     │
                    │  (teal, correct) │                  │  (orange, buggy)  │
                    └──────────────────┘                  └───────────────────┘
```

**坐标精确布局：**
- 第 1 行（y = 4.9）：True FP（x=2.3） ← → Spurious FP（x=7.7）
- 第 2 行（y = 3.2）：HR Saturation（x=7.7）
- 第 3 行（y = 1.8）：Continuous Path（x=2.3），Discrete FC Path（x=7.7）
- Panel 标签 A（y=5.8）、B（y=4.2）、C（y=2.6）、D（y=1.0）在左边界

**盒子参数：**
- True FP: 蓝底 #E3F2FD, 蓝边 #006BA6, lw=2, 圆角 pad=0.08, 尺寸 2.6×0.9
- Spurious FP: 橙底 #FFF3E0, 橙边 #D55E00, lw=2, 尺寸 2.8×0.9
- HR Saturation: 黄底 #FFF8E1, 金边 #E68A2E, lw=2, 尺寸 3.4×0.9
- Continuous Path: 绿底 #E8F5E9, 绿边 #009E73, lw=2, 尺寸 3.0×0.8
- Discrete FC Path: 橙底 #FFF3E0, 橙边 #D55E00, lw=2, 尺寸 3.0×0.8
- 标题：粗体 10pt，副标题：8pt 灰色 #555

**箭头：**
- 箭头 1：True FP → Spurious FP（水平，橙色粗箭头 lw=2.0），上标 "drift ∝ K×T/dt"（9pt 粗体橙色）
- 箭头 2：Saturation → Spurious FP（垂直向上，橙色 lw=1.8），右侧标 "truncates drift"（8pt 金色）
- 箭头 3：Continuous Path → True FP（垂直向上，虚线，绿色 lw=1.5）
- 箭头 4：Discrete FC Path → Saturation（垂直向上，虚线，橙色 lw=1.5）

**额外元素：**
- 右上角放小图例（Legend: ── correct path, ─ ─ error propagation, ● buggy, ● correct）
- 左下角模块 A/B 区域的浅灰色说明文字（"Module A: continuous relaxation" / "Module B: threshold-gated FC"）
- 确保白色背景，无网格

**风格参考：** Nature 期刊的 "Mechanism" 示意图风格 — 盒子圆角自然、箭头端点清晰、文字全部水平阅读、间距均匀。

---

## Figure 2 — MAP Bias vs dt

**角色指定：**
你是一位**计算科学可视化专家**，擅长为 SIMULATION 期刊绘制收敛研究和误差分析的二维图。你精通双轴、对数坐标、分面板等复杂图表结构，能通过颜色和标注清晰区分不同物理 regime。你的强项是把一张图讲出故事：让人一眼看到"数据在哪变化、为什么变、变化意味着什么"。

**图注：**
Figure 2: Pre-fix MAP bias vs time step at DC=10（moderate hypoxia）.（a）MAP as a function of dt on log-linear scale. MAP increases systematically from 111.0 mmHg at dt = 0.1 s to 144.7 mmHg at dt = 0.02 s, then plateaus.（b）Log-log view showing |bias| ∝ 1/dt in the unsaturated regime（bias × dt = 1.14 ± 0.04, dashed orange line）and saturation plateau. The nominal MAP of 100 mmHg is shown as a green dotted reference.

**画布：** 双面板（a + b），总宽约 9 英寸，高约 4 英寸

**面板（a）— MAP vs dt（log-x, linear y）：**
- x 轴：dt（s），log 刻度，范围 0.001 ~ 0.1，标注 0.001, 0.01, 0.1
- y 轴：MAP（mmHg），线性刻度，范围 95 ~ 150
- 数据点（6 个，用蓝色 #006BA6 圆圈 + 连线）：
  | dt | MAP |
  |---|---|
  | 0.1 | 111.0 |
  | 0.05 | 121.1 |
  | 0.02 | 144.7 |
  | 0.01 | 144.7 |
  | 0.005 | 144.7 |
  | 0.001 | 144.7 |
- 参考线：绿色虚线 #009E73 在 MAP = 100（nominal）
- 参考线：红色点线 #D55E00 在 MAP = 144.7（saturation plateau）
- 标注：Unsaturated（bias ∝ 1/dt）框在斜坡区域；Saturated（MAP plateau）框在平坦区域
- 浅灰色水平网格线

**面板（b）— Dimensional Analysis（log-log）：**
- x 轴：dt（s），log 刻度，同 (a)
- y 轴：|bias| 或 bias×dt，log 刻度，范围 0.1 ~ 50
- 蓝色曲线：#006BA6，实线 lw=2.5，|bias| vs dt（上升后 plateau）
- 橙色虚线：#E68A2E，lw=2，bias × dt 乘积（在未饱和区 ≈ 1.14 常数）
- 标注框："bias × dt ≈ const = 1.14 ± 0.04 (unsaturated)" 放置在橙色线附近
- 灰色网格线

**两面板共用：**
- 图注（a）和（b）标签在各自面板左上角
- 图例：● |bias| = |MAP − 100|, − − bias × dt (constant)
- 坐标轴标签：MAP (mmHg) / |bias| or bias × dt / Time step dt (s)
- 字号：轴标签 11pt，刻度 8pt，图注 8pt，Times New Roman / serif
- 所有数据用圆形 marker（size ≈ 6px），线宽 2.5

**数据精度：** MAP 值保留 1 位小数，bias × dt 保留 2 位小数

---

## Figure 4 — Isolation Experiment Bar Chart

**角色指定：**
你是一位**生理学模拟实验数据可视化专家**，擅长把实验设计（隔离/对照/析因）用柱状图清晰地表达出来。你对颜色编码有深刻理解：读者应该在一秒钟内看出"哪个条件造成了差异"。你特别擅长在柱状图上叠加数值标注和统计量，让图表不依赖正文也能独立读。

**图注：**
Figure 4: MAP range across dt sweep for the four-condition isolation experiment. A_contrib = X_range − Y_range quantifies the effect of FC dt-scaling alone. Under moderate hypoxia（DC=10）, FC dt-scaling reduces MAP range from 31.99 mmHg to 0.41 mmHg（A_contrib = 31.58 mmHg）. Under severe hypoxia（DC=5）, A_contrib = 18.64 mmHg. The fourth condition W（gain=10, not shown）confirms B_contrib and C_contrib are both < 0.2 mmHg.

**画布：** 宽 7.5 英寸，高 4.5 英寸

**坐标布局：**
- 4 组柱：DC=25（normal），DC=15（mild），DC=10（moderate），DC=5（severe）
- 组间距 ~1.6 英寸，每组中心位置均匀分布
- y 轴：MAP range (mmHg)，0 ~ 35，线性刻度
- 每组 3 根柱（X / Y / Z 条件）
  - X（buggy）= 橙色 #D55E00
  - Y（A-only）= 金色 #E68A2E
  - Z（A+B）= 绿色 #009E73
- 柱宽 ~0.35 英寸，同组内柱间距 ~0.05 英寸

**数据（精确值，必须按此绘制）：**

| Group | X_range | Y_range | Z_range |
|-------|---------|---------|---------|
| DC=25 | 0.10 | 0.10 | 0.35 |
| DC=15 | 2.52 | 2.52 | 2.80 |
| DC=10 | 31.99 | 0.41 | 0.51 |
| DC=5  | 20.84 | 2.20 | 2.21 |

**注：** X 在 DC=10 和 DC=5 时非常高（柱子很高），其他情况下很小。这是图表的核心信息 — X_range 在中等/重度缺氧时数量级大于 Y/Z。

**标注要求：**
- 在 DC=10 和 DC=5 的 X 柱上方标注 "A = 31.6" 和 "A = 18.6"（字体粗体，红色或深色框背景）
- 在 DC=25 和 DC=15 的 X 柱上方不加 A_contrib 标注（因为没有实际意义）
- x 轴标签：DC=25 (normal), DC=15 (mild), DC=10 (moderate), DC=5 (severe)
- 图例（右上角或图表右侧）：□ X (buggy: FC bpm/step), □ Y (A-only: FC×dt), □ Z (A+B: FC×dt+cont.)

**额外信息：**
- 底部或右上角加注："4th condition W (gain=10) confirms B_contrib & C_contrib < 0.2 mmHg"
- 水平浅灰色网格线
- y 轴从 0 开始，到 35 结束，5 的倍数 tick
- 字体：Times New Roman / serif，轴标签 11pt，刻度 8pt，数值标注 9pt

**视觉效果：** 柱用 85% 不透明度，干净白色背景，柱无边框或仅 0.5px 边框。

---

## Figure 5 — Toy Model vs Virtual Vet Comparison

**角色指定：**
你是一位**跨尺度验证与确认（V&V）可视化专家**，擅长把理论模型和实际系统的对比用双面板清晰地呈现出来。你的图表设计遵循"并排对照"原则：两边的轴刻度、坐标系、色码必须完全一致，让读者一目了然地看到"不同的系统，同样的故障模式"。

**图注：**
Figure 5: Spurious steady state — domain-independent reproducibility.（a）Minimal 2-variable toy model（dx/dt = −k·(x−x₀) + FC_event, k=0.25, K=0.5, ceiling=180）produces the same bias pattern as（b）the Virtual Vet 11-organ simulation.（a）Buggy（orange）state x rises from 120.0（dt=0.1）to 180.0（dt≤0.02）; fixed（blue）x = 102.0 independent of dt.（b）Buggy MAP rises from 111.0（dt=0.1）to 144.7（dt≤0.02）; fixed MAP = 102.3. In both panels, the unsaturated regime shows bias ∝ 1/dt, and the saturation plateau truncates further increase. The correct steady state is shown as a green dashed reference.

**画布：** 双面板（a）+（b）并排，总宽 8.5 英寸，高 4 英寸

**面板（a）— Toy Model（左侧）：**
- x 轴：dt（s），log 刻度，0.001 ~ 0.1
- y 轴：State x (a.u.)，线性刻度，90 ~ 190
- 数据点：
  | dt | Toy buggy | Toy fixed |
  |---|---|---|
  | 0.100 | 120.0 | 102.0 |
  | 0.050 | 140.0 | 102.0 |
  | 0.020 | 180.0 | 102.0 |
  | 0.010 | 180.0 | 102.0 |
- 曲线：buggy 橙色 #D55E00 实线 lw=2.5，fixed 蓝色 #006BA6 虚线 lw=2.5
- 参考线：绿色虚线 #009E73 在 x = 102（correct steady state）
- 标注："Unsaturated (bias ∝ 1/dt)" 标注在上升段，"Saturated (ceiling = 180)" 标注在平台段
- 子标题：(a) Toy Model — Minimal 2-Variable ODE System

**面板（b）— Virtual Vet（右侧）：**
- x 轴：dt（s），log 刻度，0.001 ~ 0.1（与 (a) 完全相同）
- y 轴：MAP (mmHg)，线性刻度，90 ~ 190（与 (a) 相同范围！）
- 数据点：
  | dt | VT pre-fix | VT post-fix |
  |---|---|---|
  | 0.100 | 111.0 | 102.3 |
  | 0.050 | 121.1 | 102.3 |
  | 0.020 | 144.7 | 102.3 |
  | 0.010 | 144.7 | 102.3 |
- 曲线：orange buggy 实线 lw=2.5，blue fixed 虚线 lw=2.5
- 参考线：绿色虚线 #009E73 在 MAP = 102.3（correct steady state）
- 标注："Unsaturated (bias ∝ 1/dt)" 和 "Saturated (HR ceiling = 180)"
- 子标题：(b) Virtual Vet — 11-Organ Canine Cardiovascular Simulation

**两面板共用：**
- y 轴范围统一为 90 ~ 190，确保并排时视觉可比
- 浅灰色水平网格线
- 底部居中共享图例：── Buggy (unit/step) / ─ ─ Fixed (unit/s) / - - Correct SS
- 图例和标注用 8-9pt，轴标签 11pt
- 字体：Times New Roman / serif
- 面板 (a) 标注系统方程 "dx/dt = −k·(x−x₀) + FC_event" 在标题下方

**设计哲学：** 这张图的核心论点是"同样的模式在两个完全不同的系统中出现"。所以两块面板的视觉格式必须**严格对称**——同样的 y 轴范围、同样的 log x 轴、同样的标注位置、同样的色码。读者应该一眼看出"左边的曲线形状 = 右边的曲线形状"。

---

## 综合说明

**输出格式：** 所有图均输出为 300 DPI PNG，白色背景，"tight" bbox。
**字体：** Times New Roman（serif），所有文本水平阅读，无旋转。
**布局一致性：** 多面板图（Fig 2、Fig 5）的两部分应视觉对齐 — 相同高度，标题和图例位置一致。
**数据精确性：** 柱高度和曲线位置必须严格按上文表格数据绘制，不可近似。
