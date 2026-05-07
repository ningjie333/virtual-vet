# Game 层硬编码消除方案

> 日期：2026-05-05
> 状态：全部阶段已完成（2026-05-07）

## 一、问题诊断

疾病 ODE 模拟层已完全配置驱动（`data/ode_diseases.json`），但 game 层仍在用"硬编码函数 + 字符串匹配"对接。每次新增疾病/检查类型必须改多个 Python 文件。

### 硬编码清单

| 文件 | 硬编码内容 | 影响 |
|------|-----------|------|
| `game/test_translator.py` | `NORMAL_RANGES`（18 个参数参考范围） | 新增参数需改代码 |
| `game/test_translator.py` | `CRITICAL_THRESHOLDS`（8 个参数危急值） | 新增参数需改代码 |
| `game/test_translator.py` | `_get_state()`（引擎状态快照硬编码映射） | 新增参数需改代码 |
| `game/test_translator.py` | 21 个 `_xxx()` 报告生成函数 | 新增检查类型需写新函数 |
| `game/test_translator.py` | `_TEST_DISPATCH`（手动分派表） | 新函数需手动注册 |
| `game/diagnosis_engine.py` | `clue_map`（参数名×flag → 线索 ID 手写映射） | 双向耦合 |
| `game/diagnosis_engine.py` | 中文字符串匹配（"湿啰音"、"实变"等） | 改措辞即断诊断 |
| `game/action_system.py` | `_EXAM_CONFIG`（21 条检查配置） | 与 examinations.json 重复 |

## 二、配置文件变更

### 新增文件

**1. `data/vitals_ranges.json`** — 替代 `NORMAL_RANGES` + `CRITICAL_THRESHOLDS` + `clue_map`

```json
{
  "HR": {
    "unit": "bpm",
    "normal": [60, 120],
    "critical": [40, 180],
    "clue_flags": {
      "high": "hr_high",
      "low": "hr_low",
      "critical_high": "hr_critical"
    }
  }
}
```

**2. `data/exam_templates.json`** — 替代 21 个 `_xxx()` 函数 + `_TEST_DISPATCH`

```json
{
  "blood_gas": {
    "vitals": ["blood.pH", "blood.PaCO2", "blood.PaO2", "blood.HCO3"],
    "summary_rules": [
      {
        "cond": "blood.pH < 7.35 and blood.PaCO2 > 45",
        "tag": "respiratory_acidosis"
      }
    ],
    "narrative_template": "pH:{blood.pH} PaCO2:{blood.PaCO2} 提示 {summary_tag}"
  }
}
```

### 扩展已有文件

**3. `data/examinations.json`** — 补充 `latency_turns` + `report_params`，替代 `_EXAM_CONFIG`

```json
{
  "blood_gas": {
    "tier": 3,
    "cost": 3,
    "category": "lab",
    "latency_turns": 1,
    "report_params": ["PaO2", "PaCO2", "pH"]
  }
}
```

## 三、新增引擎模块

```
src/
  report_engine.py    → 通用报告生成器（读 exam_templates.json 驱动）
  clue_extractor.py   → 结构化线索提取（消费 tags，不碰中文字符串）
  exam_registry.py    → 检查注册表（替代 _TEST_DISPATCH + _EXAM_CONFIG）
```

## 四、核心数据结构

```python
# translator 输出 — 结构化 + 可读文本双字段
@dataclass
class ExamReport:
    test_type: str
    tags: list[str]        # 新增：结构化标签（诊断引擎消费这个）
    summary: str           # 保留：中文可读文本（UI 显示用这个）
    display_values: dict   # 新增：带单位的显示值
    flags: list[str]       # 保留：normal/low/high/critical
```

**关键原则**：diagnosis_engine **只消费 tags**，不再碰 summary 中的中文字符串。

## 五、解耦机制对照

| 原来 | 现在 |
|------|------|
| `if "湿啰音" in text` | translator 直接 emit tag `"crackles"` |
| 手写 `clue_map` 字典 | 从 `vitals_ranges.json` 的 `clue_flags` 自动推导 |
| 21 个 `_xxx()` 函数 | `generate_report()` 读模板 + 执行规则 + 填充占位符 |
| `_TEST_DISPATCH` 手动分派 | `exam_registry.get(exam_type)` 自动查表 |
| `_EXAM_CONFIG` 硬编码 | 从 `examinations.json` 读取 |

## 六、分阶段迁移路径

| 阶段 | 内容 | 验证方式 | 可回滚 |
|------|------|---------|--------|
| **Phase 1** | 新增 `vitals_ranges.json`，数据从 Python 字典搬迁到 JSON | 跑现有测试，输出完全一致 | ✅ |
| **Phase 2** | `ExamReport` 加 `tags[]` 字段，diagnosis_engine 新路径优先，旧字符串匹配做 fallback | 两种路径输出对比 | ✅ |
| **Phase 3** | 实现 `report_engine` 通用引擎，逐个迁移 21 个函数为模板 | 每迁移一个跑对应测试 | ✅ |
| **Phase 4** | 删除旧代码：手写函数、字符串匹配、`_TEST_DISPATCH`、`_EXAM_CONFIG`、`clue_map` | 全量测试通过 | ✅ |

每阶段独立可回滚，前端 API 响应格式不变（summary 字段继续存在，只是新增了 tags 字段）。

## 七、扩展点设计

| 新增需求 | 需要改的文件 | Python 代码 |
|----------|-------------|------------|
| 新疾病 | `ode_diseases.json` + `diseases.json` | ❌ 不改 |
| 新检查类型 | `examinations.json` + `exam_templates.json` | ❌ 不改 |
| 新生理参数 | `vitals_ranges.json` | ❌ 不改 |
| 新线索 | `diseases.json` 的 clues 节 + `exam_templates.json` 的 tag_rules | ❌ 不改 |

## 八、数据流向

```
vitals_ranges.json ──→ VitalsConfig（只读）
        ├──→ report_engine：读 normal/critical 生成报告
        └──→ clue_extractor：读 clue_flags 反向匹配线索

exam_templates.json ──→ ReportTemplate（只读）
        └──→ report_engine：读模板生成报告

examinations.json ──→ ExamConfig（只读）
        ├──→ exam_registry：AP 成本/层级/延迟
        └──→ report_engine：report_params 参数列表
```
