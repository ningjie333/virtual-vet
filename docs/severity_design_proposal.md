# 疾病严重度设计提案

**状态**：修订版（2026-06-14 多 agent 讨论后修订）
**日期**：2026-06-13（初稿）→ 2026-06-14（修订）
**作者**：架构审查 + 生理/游戏/架构三角度讨论

---

## 核心原则（修订）

> **临床分期是状态，疾病动力学是参数。两者正交，不可互相替代。**

原提案的核心假设"severity 是状态，不是参数"**部分正确**：

- ✅ **临床分期标签**（轻度/中度/重度）应该从 ODE 状态变量计算得出
- ❌ **疾病动力学参数**（rate/K）不能用 warmup 替代 — 15/15 疾病都证明了这一点

### 为什么 severity_presets 必须保留

severity_presets 改变的是 ODE 的**根本动力学**，不是初始条件：

| 疾病 | rate 比 (severe/mild) | K 比 (severe/mild) | warmup 可行？ |
|------|:---:|:---:|:---:|
| pneumonia | 5.6× | 2.4× | ❌ |
| DCM | 4.0× | 2.4× | ❌ |
| GDV | 5.0× (ischemia) | 2.4× | ❌ |
| DKA | 4.0× (3 个 rate) | N/A | ❌ |
| ... (15/15 疾病) | 2-5× | 1.3-3× | ❌ |

**数学论证**：logistic 方程 `dS/dt = rate × S × (1 - S/K)` 中：
- `rate` 差 4 倍 = severe 的进展速度是 mild 的 4 倍（warmup 无法复制）
- `K` 差 2.4 倍 = mild 的最大损伤只有 40%，severe 可达 95%（warmup 无法改变上限）

**实测数据**（pneumonia moderate，不同 warmup）：

| warmup | exudate | bacteria | fever | MAP |
|--------|---------|----------|-------|-----|
| 1m | 0.27 | 0.19 | 0.004 | 100.5 |
| 5m | 0.47 | 0.03 | 0.008 | 100.5 |
| 15m | 0.68 | 0.0003 | 0.007 | 100.5 |
| 30m | 0.70 | 0.0000 | 0.004 | 101.3 |

**问题**：moderate 的 immune_clearance=0.01 太强，bacteria 被清零（疾病自愈）。warmup 再长也无法产生 severe 效果。

---

## 修订后的设计方向

### 方向一（修订）：保留 severity_presets + 加 compute_clinical_severity

**原方向一**（warmup-only）**废弃** — 15/15 疾病都证明不可行。

**修订方向**：severity_presets 保留作为**疾病动力学参数**，新增 `compute_clinical_severity()` 从 ODE 状态计算**临床分期标签**。

#### Phase 1：compute_clinical_severity（零破坏，纯增量）

在 `ode_diseases.json` 中为每个疾病新增可选字段：

```json
{
  "pneumonia": {
    "severity_presets": { ... },  // 保留不动
    "clinical_severity": {
      "primary_var": "alveolar_exudate",
      "thresholds": [0.3, 0.7],
      "labels": ["mild", "moderate", "severe"]
    }
  }
}
```

新函数 `compute_clinical_severity(state_vars, disease_name) -> str`：
- 读取 `clinical_severity` 配置
- 根据 `primary_var` 的当前值和 `thresholds` 返回 `labels` 中的标签
- 用于报告引擎生成"轻度呼吸急促" vs "严重低氧血症"的语言

**不改**：ConfigDrivenDiseaseModule 内部、cases.json 结构、case_generator、gui_app API。

#### Phase 2：warmup 控制叙事层

warmup 的游戏价值不在生理模拟，而在**叙事层**：

| warmup | 叙事 | 玩家感知 |
|--------|------|---------|
| 0.5min | "主人说刚才突然就不行了" | 急症 |
| 2min | "3 天前开始咳嗽" | 亚急性 |
| 20min | "近 2 个月运动量下降" | 慢性 |

当前 `game_history` 是静态文本，不因 warmup 不同而变化。建议让 warmup 生成动态的"就诊时机描述"。

#### Phase 3：severity_presets 语义重定义

把 severity_presets 从"三个不同的病"重新定义为"同一疾病的不同生物学变异"：

| 原含义 | 新含义 |
|--------|--------|
| mild = 轻度肺炎 | mild = 免疫力正常的年轻动物（免疫清除快，病情自限） |
| moderate = 中度肺炎 | moderate = 基线（默认） |
| severe = 重度肺炎 | severe = 免疫抑制/老年/合并症（免疫清除慢，病情失控） |

这样 warmup + severity 共同决定就诊时的状态：
- severe 肺炎 warmup=2min ≈ moderate 肺炎 warmup=15min（临床表现相似）
- 但 severe 的后续进展更快（rate 更高），玩家需要更快行动

---

### 方向二：物种差异作为生理响应差异（不变）

**思路**：同一种病，在不同物种身上的临床表现不同，源于物种特异的生理参数。

**Q3 已落地**（2026-06-14）：

| 生理量 | 犬 | 猫 | 马 | 状态 |
|--------|:--:|:--:|:--:|------|
| 静息心率 | ✅ CANINE=85 | ✅ FELINE=150 | ✅ EQUINE=35 | ✅ |
| 应激心率 | ✅ CANINE=180 | ✅ FELINE=250 | ✅ EQUINE=70 | ✅ |
| 静息 RR | ✅ CANINE=18 | ✅ FELINE=25 | ✅ EQUINE=12 | ✅ |
| 应激 RR | ✅ CANINE=40 | ✅ FELINE=50 | ✅ EQUINE=60 | ✅ |
| PaCO₂ | ✅ CANINE=40.0 | ✅ FELINE=35.0 | ✅ EQUINE=42.0 | ✅ |
| Hb | ✅ 14.0 | ✅ 12.0 | ✅ 13.0 | ✅ |
| 血容量 ml/kg | ✅ 86 | ✅ 55 | ✅ 76 | ✅ |
| 发热阈值 °C | ✅ 39.2 | ✅ 39.5 | ✅ 38.5 | ✅ |

Lookup helpers：`species_hr()` / `species_rr()` / `species_paco2()` / `fever_threshold_c()` / `total_blood_volume_ml()` 已实现。

**疾病 ODE 本身不需要按物种变化** — species 差异在引擎层已覆盖。

---

### 方向三：合并症（多疾病叠加）— ✅ 已落地

**诊断半边**（2026-06-14 全部完成）：

| 组件 | commit | 状态 |
|------|--------|------|
| Q1 engine: `self.diseases` list | `379557f` | ✅ |
| Q2 spec: chained-rebase | `379557f` | ✅ |
| game-layer wiring | `db9958e` | ✅ |
| 2 comorbidity cases | `7d9a42b` | ✅ |
| multi-disease diagnosis | `4ce5a0f` | ✅ |

**治疗半边**（2026-06-14 全部完成）：

| 问题 | 决策 | commit |
|------|------|--------|
| Q4.1 治疗输入 | C. 自动推断 | `1461de0` |
| Q4.2 Win/loss | B. 主诊断必须对 | `1461de0` |
| Q4.3 Protocol 存法 | B. 运行时合并 | `1461de0` |

---

## 修订后的实施步骤

### 第一步（已完成）：Q1-Q4 基础设施

- ✅ Q1: `self.diseases` list + multi-disease support
- ✅ Q2: chained-rebase merge semantics
- ✅ Q3: species-aware parameters + lookup helpers
- ✅ Q4: multi-disease treatment (auto-infer + primary-must-win + runtime merge)

### 第二步（下一步）：compute_clinical_severity

1. 在 `ode_diseases.json` 中为每个疾病新增 `clinical_severity` 字段
2. 实现 `compute_clinical_severity(state_vars, disease_name) -> str`
3. 集成到报告引擎，生成 severity-appropriate 语言
4. 测试：同一疾病不同 warmup 产生不同的临床分期标签

### 第三步（未来）：warmup 叙事层

1. 让 warmup 生成动态的"就诊时机描述"
2. 集成到 game_history / case description

### 第四步（未来）：severity_presets 语义重定义

1. 更新 `ode_diseases.json` 注释，明确 presets 是"生物学变异"而非"不同疾病"
2. 更新 `create_disease()` 文档
3. 考虑重命名 `severity_presets` → `strain_profiles`（可选，YAGNI？）

---

## 不再使用的设计（修订）

以下设计建议**废弃**：

- ❌ ~~移除 `severity_presets` 中的 mild/moderate/severe 参数变体~~（15/15 疾病证明不可行）
- ❌ ~~warmup_minutes 作为唯一分期机制~~（warmup 无法复制 rate/K 差异）
- ❌ ~~cases.json 的 `severity` 字段用 warmup_minutes 代替~~（两者正交，不可替代）

保留的设计：

- ✅ `severity_presets` 作为疾病动力学参数（rate/K）
- ✅ `warmup_minutes` 作为就诊时机（叙事层 + 临床分期输入）
- ✅ `difficulty` 作为游戏体验参数（AP 预算 + 线索设计）
- ✅ `compute_clinical_severity()` 从 ODE 状态计算临床分期标签

---

## 附录：多 agent 讨论记录（2026-06-14）

### 生理建模角度

15/15 疾病的 severity_presets 都修改了 ODE 的 rate 和/或 K 参数，而不是初始条件。warmup staging 只能设置初始状态，无法改变系统的动力学方程。

**结论**：severity_presets 是不可删除的架构组件。

### 游戏设计角度

- warmup 让玩家感受不到"拖了很久"（时间感知断裂 + 无叙事线索）
- severity_presets 应保留，语义改为"生物学变异"而非"不同疾病"
- difficulty 和 severity 应解耦（difficulty=AP预算+线索设计，severity=就诊时临床状态）
- 合并症应作为主要难度杠杆（比拉长 warmup 更有游戏设计价值）

### 架构角度

- Option A（删除 presets）：不可行，15/15 疾病都证明了
- **Option B（保留 presets + 加 compute_clinical_severity）**：推荐，零破坏，纯增量
- Option C（重命名 presets → strain_profiles）：中等工作量，仅命名 clarity

**推荐**：Option B，分阶段实施。

---

## 相关 commits

| commit | 内容 | 日期 |
|--------|------|------|
| `379557f` | Q1 engine: `self.diseases` list + chained-rebase spec | 2026-06-14 |
| `db9958e` | game-layer wiring: PresentationRequest/GameState/gui_app | 2026-06-14 |
| `7d9a42b` | 2 comorbidity cases (DCM+肺炎, CKD+肺炎) + 端到端测试 | 2026-06-14 |
| `4ce5a0f` | multi-disease diagnosis (/api/hint top-2 + /api/diagnosis target_diseases) | 2026-06-14 |
| `939d54d` | Q3 species-aware parameters + lookup helpers | 2026-06-14 |
| `1461de0` | Q4 multi-disease treatment (auto-infer + primary-must-win + runtime merge) | 2026-06-14 |
