# 疾病严重度设计提案

**状态**：草稿
**日期**：2026-06-13
**作者**：架构审查

---

## 核心原则

> **疾病严重度是状态，不是参数。**

轻度/中度/重度是疾病的**临床分期标签**，由 ODE 状态变量计算得出，而不是预设的三套不同 ODE 参数。

当前设计的 `severity_presets: { mild/moderate/severe }` 本质上是三个不同的病，而不是同一疾病的不同阶段。这导致：
- 病例的难度差异来自"预设参数"，而非"就诊时机"
- 疾病没有单一的进展路径，调试和分析困难
- 临床分期（早期/进展期/危重）和游戏难度混淆

---

## 当前设计的问题

### 问题 1：severity 是输入，不是输出

```json
// 当前 — 三套参数，三个"病"
"severity_presets": {
  "mild":    { "growth_rate": 0.001429 },
  "moderate": { "growth_rate": 0.0025 },
  "severe":  { "growth_rate": 0.008 }
}
```

这三条 logistic 曲线代表**不同的细菌增长模型**，不是"同一个肺炎的不同阶段"。

### 问题 2：cases.json 不声明 severity

```python
# gui_app.py:337 — 实际运行
disease = create_disease("pneumonia")  # severity 未指定
# → config_driven.py fallback 到 moderate
```

### 问题 3：difficulty 和 severity 混淆

| 字段 | 正确含义 | 当前状态 |
|------|---------|---------|
| `difficulty` | 时间预算（游戏体验参数） | ✅ 正确 |
| `severity` | 临床分期（生理状态标签） | ❌ 缺失 |
| `warmup_minutes` | 病史长短（就诊时机） | ✅ 正确，但未利用 |

---

## 建议的设计方向

### 方向一：warmup_minutes 作为唯一分期机制

**思路**：同一疾病、同一 ODE 路径，病例差异来自"什么时候来就诊"。

```json
// 早期肺炎 — 症状轻，线索典型
{
  "id": "case_pneuma_early",
  "title": "咳嗽3天伴精神沉郁",
  "disease": "pneumonia",
  "warmup_minutes": 2,
  "difficulty": 1
}

// 晚期肺炎 — 症状重，已出现呼吸窘迫
{
  "id": "case_pneuma_late",
  "title": "呼吸急促、拒食、倒地不起",
  "disease": "pneumonia",
  "warmup_minutes": 30,
  "difficulty": 2
}
```

**实现要求**：

1. 移除 `severity_presets` 中的 mild/moderate/severe 参数变体，保留**单一参数集**
2. 临床分期（轻度/中度/重度）由 `state_variables` 的当前值计算得出，**不传入**
3. `build_presented_engine(warmup_minutes)` 将 warmup 时间作为疾病 ODE 的预热时长

**临床分期计算示例**（pneumonia）：

```
轻度（early）：  alveolar_exudate < 0.3
中度（moderate）：0.3 ≤ alveolar_exudate < 0.7
重度（severe）：  alveolar_exudate ≥ 0.7
```

或用多个指标综合评分：

```python
def compute_clinical_severity(state: dict) -> str:
    exudate = state.get("alveolar_exudate", 0)
    bacterial_load = state.get("bacterial_load", 0)
    fever = state.get("fever_state", 0)

    score = exudate * 0.4 + bacterial_load * 0.01 + fever * 0.3
    if score < 0.3: return "mild"
    if score < 0.6: return "moderate"
    return "severe"
```

---

### 方向二：物种差异作为生理响应差异

**思路**：同一种病，在不同物种身上的临床表现不同，源于物种特异的生理参数。

物种差异在引擎层已支持（`NORMAL_HR_FELINE`、`NORMAL_HB_CANINE` 等），但疾病 ODE 参数本身不需要按物种变化。

**需要确认的物种差异点**：

| 生理参数 | 犬 | 猫 | 马 |
|---------|----|----|-----|
| 正常心率 (bpm) | 60-120 | 140-220 | 28-44 |
| 血容量 (ml/kg) | 86 | 55 | 76 |
| 血红蛋白 (g/dL) | 14.0 | 12.0 | 13.0 |
| 呼吸频率 (/min) | 10-30 | 20-30 | 10-14 |
| 发热阈值 (°C) | >39.2 | >39.5 | >38.5 |

**对疾病表现的影响**：

- **肺炎**：犬血氧下降更明显（血容量大），猫呼吸代偿更快（基础RR高）
- **心包积液**：大型犬（杜宾、大丹）更多见，猫罕见但更急性
- **肾衰**：老龄犬高发，马的GFR基线更高

**实现**：species 参数已经在 `VirtualCreature.__init__` 中，使用物种特定基线，不需要改动 ODE。

---

### 方向三：合并症（多疾病叠加）

**思路**：患宠在就诊时已有基础病，再合并急性病，临床表现更重。

```python
# 游戏初始化时
creature.attach_disease(create_disease("dilated_cardiomyopathy"))  # 基础心脏病
creature.attach_disease(create_disease("pneumonia"))               # 急性肺炎
```

**合并症的表现**：

| 基础病 | 合并症 | 效果 |
|--------|--------|------|
| 扩张型心肌病 | 肺炎 | 心输出量进一步下降 → 缺氧加重 |
| 慢性肾病 | 肺炎 | 免疫低下，感染扩散更快 |
| 糖尿病 | 泌尿感染 | 血糖控制困难，酮症风险 |

**架构要求**：

1. `VirtualCreature.attach_disease()` 需要支持多疾病（目前可能只支持一个）
2. 多疾病同时输出到同一参数时，需要**优先级/叠加规则**（FactorCommand 合并）
3. 临床线索可能重叠或矛盾（心电图同时有心脏病和肺病的特征）

**需要确认**：当前 `attach_disease()` 是否支持多疾病同时 attached。

---

## 不再使用的设计

以下设计建议**废弃**，不再实现：

- `severity_presets` 中的 mild/moderate/severe 三套参数变体（severity 应从状态计算）
- cases.json 的 `severity` 字段（用 warmup_minutes 代替）
- `difficulty` 和 `severity` 的映射表（两个概念应分离）

---

## 实施步骤建议

### 第一步（数据层）

1. 审计所有疾病的 `severity_presets`，确认哪些疾病有"真三套参数"需求（不同病程）
2. 对有需要的疾病，保留多参数集；对只需要单一路径的疾病，统一为一套参数
3. 在 `ode_diseases.json` 中为需要多套参数的疾病标注 `multi_path: true`

### 第二步（计算层）

1. 实现 `compute_clinical_severity(state, disease_name) → str` 函数
2. 在 `clinical_signs_engine.py` 或新模块中调用，返回 mild/moderate/severe
3. 严重度用于生成临床报告的语言（"轻度呼吸急促" vs "严重低氧血症"）

### 第三步（病例层）

1. 删除 cases.json 中不需要的 severity 字段（如果添加了的话）
2. 通过 `warmup_minutes` 控制就诊时机，不同时间预算的病例用不同的 warmup
3. 增加合并症病例：在 cases.json 中用 `comorbidities: ["disease_name"]` 字段声明

### 第四步（物种层）

1. 确认现有 species 参数覆盖了需要的所有生理差异
2. 补充缺失的物种差异（如猫的呼吸代偿机制）
3. 为每种疾病标注"对哪些物种有显著差异"

---

## 附录：需要确认的技术问题

1. **attach_disease 多疾病支持**：当前是否支持同一 creature 挂载多个疾病模块？
2. **FactorCommand 冲突合并**：两个疾病同时输出到 `heart.heart_rate` 时，优先级如何定？
3. **species 参数完整性**：现有物种参数是否足够支持方向二的需求？