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

## 附录：技术问题核实结果

> 状态更新（2026-06-14 第二次更新）：Q1 + Q2 **已决策 + 已实施**（见下方"已决定"框）。
> 本节上半段"现状 / 证据 / 建议"是 2026-06-14 上午的摸底结论；下半段"已决定"是下午的决策与落地状态。

### Q1：attach_disease 多疾病支持

#### ✅ 已决定（2026-06-14 下午）

**决策**：✅ **实施**。`self.disease` (单数) → `self.diseases: list[DiseaseModule]`。

落地：

- `src/simulation.py::VirtualCreature.__init__` 改 `self.diseases: list = []`
- `attach_disease()` 改为 `append` 模式（支持重复调用叠加）
- 12 处 `self.disease` 引用全部重构（Euler 路径 / Radau 状态向量 / summary / _ivp_rhs 等）
- 状态向量 namespace: `disease.{name}`（每病独立 state var 命名空间，避免冲突）
- 向后兼容 `@property disease` 返回 `self.diseases[0] if self.diseases else None`
- 配套测试：`tests/test_multi_disease.py` 9 个用例全过
- `tests/test_manifest.json` 注册新文件（lane=fast, bundle=fast-engine）

回归：原有 7 个测试文件（twin_run / cross_module_coupling / neuro / organ_health / coupling / scenarios / factor_command）**119 passed, 0 failed**，证明 backward-compat property 保住单病场景。

#### 现状（2026-06-14 上午摸底）：不支持（单数存储）

证据：

- `src/simulation.py:165` — `self.disease = None`（**单数**）
- `src/simulation.py:352` — `self.disease = disease_module`（**单数赋值，直接覆盖**）
- 全文 8 处引用全是 `self.disease` 单数：
  `simulation.py:574,585,676,984,995,1003,1027,1230`
- `src/simulation.py:585` — `for cmd in self.disease.compute(dt, engine_state)`（**单数调用**）

连续 `attach_disease(A); attach_disease(B)` → B 覆盖 A，A 的 compute 永远不再跑。

**底层 DiseaseModule ABC**（`src/diseases/__init__.py:79`）本身是无状态纯函数式
（`compute(dt, engine_state) -> list[FactorCommand]`），**支持多实例**；缺的是
VirtualCreature 的胶水代码：把 `self.disease` 改成 `self.diseases: list[DiseaseModule]`,
每步 `for d in self.diseases: for cmd in d.compute(...): self.apply_factor(cmd)`。

**工作量评估**：~30 行代码改动 + 1 个新 list 字段 + 8 处引用改 list 迭代。
低风险（DiseaseModule 接口无需变化，回归测试套件覆盖 compute → apply_factor 全链路）。

### Q2：FactorCommand 冲突合并

#### ✅ 已决定（2026-06-14 下午）：选 **A — 显式契约 "chained-rebase"**

**依据**：

- 临床 3 个核心 multi-disease 场景（DCM+肺炎、CKD+肺炎、糖尿病+UTI）都需要**复合效果**，不是"覆盖"
- `multiply` 链 = 复合（DCM 0.7 × 肺炎 0.8 = 0.56）✓ 临床对得上
- `add` 链 = 累加（+5 + +10 = +15）✓
- `set` 链 = 后写者赢（most recent disease = most relevant clinical context）✓

**为什么不选 B（priority 字段）**：

- B 让高 priority 覆盖低 priority，但提案 3 场景都需要**复合**，B 生理上错
- B 还给每个 disease author 增加认知负担（要思考 priority）

**为什么不选 C（聚合策略 max/sum/last-wins）**：

- `sum-factor for multiply` ≡ A（等价）
- `last-wins for set` ≡ A（等价）
- `max-severity` 不生理（0.7 × 0.8 应该是 0.56 而不是 min=0.7）
- C 复杂度 > A，但没带来额外临床价值

**实施状态**：

- ✅ `src/diseases/__init__.py::DiseaseModule` 加了 Q2 spec docstring（chained-rebase 三种 op 的语义说明）
- ✅ `tests/test_multi_disease.py` 9 个回归用例覆盖 multiply/add/set 三种链 + 顺序无关性 + backward compat
- 文档：所有"决策 + 实施"细节见上方 Q1 落地清单（共享同一 refactor 提交）

#### 现状（2026-06-14 上午摸底）：无显式合并语义，按"调用顺序 chained-rebase"

证据 — `src/engine/factor_pipeline.py:65-117` 的 `apply_factor`：

```python
current = getattr(module, attr_name, None)   # 读当前引擎值
if cmd.op == "multiply": new_value = current * cmd.value
elif cmd.op == "add":    new_value = current + cmd.value
elif cmd.op == "set":    new_value = cmd.value
setattr(module, attr_name, new_value)        # 立即写回
```

每次 `apply_factor` 立即 setattr 写回，**引擎值被污染给下一个 cmd**。举例（HR 初始 100）：

1. 肺炎发 `multiply 1.5` → 引擎值变 150
2. DCM 紧跟着发 `add 30` → 读到的 current 已是 150 → 引擎值变 180

结果 = **乘法再加成法的串联**。没有优先级、没有"取更严重者"、没有 spec 化合并规则。
`DiseaseModule` 也没有 `priority` 字段（搜索确认）。

**不是 bug，是欠设计**。多病叠加时（提案方向三）这个语义必须先明确，三个候选：

- **A. 显式契约**："按 diseases list 顺序 chained-rebase"，写入 DiseaseModule 文档
  → 零代码改动，仅规范（最简）
- **B. 引入 `priority` 字段**：DiseaseModule 声明优先级，apply 前按 priority 排序
  → ~10 行代码 + 元数据改动
- **C. 同 target 聚合策略**：max-severity / sum-factor / last-wins
  → 需要新策略枚举 + 测试矩阵，工作量最大

**建议**：方向三启动前**必须**先在 A/B/C 之间选一个，并补一条 multi-disease 回归测试
（两个 disease 同时发同 target，断言合并行为符合 spec）。当前没有这条测试。

### Q3：species 参数完整性

#### 现状：能跑，但缺 4 项关键值

| 生理量 | 犬 | 猫 | 马 | 状态 |
| --- | :--: | :--: | :--: | --- |
| 静息心率 | ❌ 用基线 | ✅ FELINE=150 | ✅ EQUINE=35 | **缺犬显式常量** |
| 应激心率 | ❌ | ✅ 250 | ✅ 70 | **缺犬** |
| 静息 RR | ❌ | ✅ 25 | ✅ 12 | **缺犬** |
| 应激 RR | ❌ | ✅ 50 | ❌ | **缺犬 + 马** |
| 动脉 PaCO₂ | ❌ | ✅ 35.0 | ✅ 42.0 | **缺犬** |
| 血红蛋白 Hb | ✅ 14.0 | ✅ 12.0 | ✅ 13.0 | **唯一 3 物种齐** |
| 血容量 ml/kg | ❌ | ❌ | ❌ | **全缺** |
| 发热阈值 °C | ❌ | ❌ | ❌ | **全缺** |
| 体重归一 SV | ✅ fallback | ✅ 专用 | ✅ 专用 | 犬做兜底 |
| 体重归一 TV | ✅ fallback | ✅ 专用 | ✅ 专用 | 犬做兜底 |

证据：

- `src/parameters.py:2` — `# 基于犬科动物正常生理值`（犬是默认基线）
- 搜 `FEVER|BODY_TEMP|BLOOD_VOLUME|TEMP_` → **0 命中**（血容量/体温完全没建模）
- 提案方向二"犬血氧下降更明显（血容量大）"需要血容量数据 → **缺**
- 提案方向二"猫呼吸代偿更快"需要应激 RR 猫 vs 犬对照 → **缺犬 RR 基线**

**如果走方向二，must-do 清单**：

1. 加 `NORMAL_HR_CANINE` / `NORMAL_HR_STRESS_CANINE` / `NORMAL_RR_CANINE` / `NORMAL_PACO2_CANINE`
   等显式常量（让 3-way lookup 统一，犬不再走隐式 fallback）
2. 加 3 物种 `BLOOD_VOLUME_ML_KG_*`（休克模型关键，犬 86 / 猫 55 / 马 76 来自提案表）
3. 加 3 物种 `FEVER_THRESHOLD_C_*`（pneumonia / sepsis 提案分级用，犬 >39.2 / 猫 >39.5 / 马 >38.5）
4. `base_DO2_normal_ml_min` 现有 Hb 三路 if-else 是**正确范本**，照此扩展到 HR/RR/PaCO₂

**工作量**：~20 行常量 + 3 个 lookup helper（统一抽 `NORMAL_HR[species]` 形式），改动局部，
不影响疾病 ODE。可与方向二实施一起做。

---

## 方向三 (合并症) 治疗半边 — Q4（2026-06-14 记入调研项）

**状态**：⏸ **未做**。这是重要工程，**需要设计调研 + 决策讨论**才能动手写代码，不能直接 commit。

### 现状（2026-06-14）

方向三的**诊断半边**已落地（Q1 engine / Q2 spec / game-layer wiring / comorbidity cases / 多病 hint & target_diseases），但**治疗半边**还没碰：

| 组件 | 现状 | 多病需要 |
|------|------|---------|
| `treatments.json` | 1 个 disease → 1 个 drug protocol | 1 个 case → N 个 disease → N 个 protocol？合并 protocol？ |
| `game/treatment.py::is_correct_treatment` | `guess == state.disease_name` | 单数猜 → 集合匹配（猜 1 个算部分对？猜全算全对？）|
| `apply_treatment` | 跑 guess 对应的 protocol | 多病 case 怎么 admin？ |
| Win/loss 消息 | 单病 win/loss 文案 | 多病 case 怎么算 "已治愈"？ |
| UI 提示 | 选 1 个 disease 治疗 | 多病 case 怎么选？dropdown list？ |

### 3 个待决策的设计问题

**Q4.1：治疗输入的"颗粒度"**

- **A. 一次性治疗所有**：case start 时固定给"主诊断 + 合并症"的合并 protocol，玩家无需选
- **B. 玩家逐个选**：UI 让玩家在 dropdown 选要治哪个 disease；选错（或不完整）算 partial lose
- **C. 自动推断**：基于玩家提交的诊断（`/api/diagnose` 时的 guess list），自动 admin 所有猜中的 protocol

**Q4.2：Win/loss 条件**

- **A. 严格全对**：所有 `state.disease_names` 都被正确诊断 + 正确治疗才 win
- **B. 主诊断必须对**：仅要求 `disease_name`（主诊断）猜对 + 治对，合并症错也 win
- **C. 加权进度**：每猜对 1 个病算 N% 进度（如 2 病 = 50%/50%），> 80% 算 win

**Q4.3：多病 protocol 在 `treatments.json` 的存法**

- **A. 复用单病条目**：`treatments.json` 加 `"dilated_cardiomyopathy + pneumonia"` 这种 **组合 key** 的 protocol
- **B. 运行时合并**：保持单病 protocol，运行时按 `state.disease_names` 依次 admin（顺序可配置）
- **C. 共享 protocol**：识别 common syndrome (e.g., "心源性肺水肿") 用 1 个 protocol 覆盖

### 跟已有代码的耦合点

- `gui_app.py:570-606` (treatment API) 需要扩展
- `game/treatment.py:64-101` (`is_correct_treatment` + `apply_treatment`) 核心改动
- `treatments.json` 现有结构（disease → [drug_steps]）需扩
- `tests/test_treatment*.py` 现有断言需重写
- `docs/disease_references_plan.md` 如果有 plan 要更新

### 建议调研路径

1. **本周不动代码**——只设计 + 讨论，写调研结论到本节下方
2. **临床专家 review**：跟合作兽医确认"方向三 3 个场景里，玩家应该怎么被奖励/惩罚"
3. **技术 review**：`treatments.json` 的修改是否向后兼容已有 19 个 case
4. **做完调研再 commit 改动**

### 相关 commits（诊断半边已完成）

- `379557f` Q1 engine: `self.diseases` list + chained-rebase spec
- `db9958e` game-layer wiring: PresentationRequest/GameState/gui_app
- `7d9a42b` 2 comorbidity cases (DCM+肺炎, CKD+肺炎) + 端到端测试
- `4ce5a0f` 多病诊断 (/api/hint top-2 + /api/diagnosis target_diseases)


### ✅ Q4 已决定（2026-06-14）

| 问题 | 决策 | 理由 |
|------|------|------|
| Q4.1 治疗输入 | **C. 自动推断** | 零 UI 改动，复用 `/api/diagnose` 流程。玩家通过诊断表达"我认为是什么病"，系统自动 admin 对应 protocol |
| Q4.2 Win/loss | **B. 主诊断必须对** | 降低难度。合并症猜对 → bonus 消息；猜错 → 不影响 win 判定 |
| Q4.3 Protocol 存法 | **B. 运行时合并** | 保持 `treatments.json` 单病条目，运行时按 guess list 顺序依次 admin |

实施：
- `game/treatment.py`: `apply_treatment` 接受 `str | list[str]`，`_resolve_guesses` 归一化，`comorbidity_correct` 字段
- `gui_app.py`: `/api/diagnose` accept list or string，`game_over` 包含 `target_diseases` + comorbidity 消息
- `tests/test_multi_disease_treatment.py`: 16 用例全过
