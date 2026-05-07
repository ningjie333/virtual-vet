# Virtual Vet Gate Check — 具体实施方案

> 日期：2026-05-07
> 目标：消灭跨文件一致性问题，让新增疾病/检查类型只改 JSON 不踩坑

---

## 一、要检查什么

### 检查 1：API 端点一致性（对应 WAT 方案的路由死链检查）

| 检查项 | 规则 | 严重度 |
|--------|------|--------|
| 前端调用了后端未注册的端点 | `api.ts` 中每个 `invoke` 的 URL，`gui_app.py` 必须有对应的 `@app.route` | CRITICAL |
| 前端 HTTP 方法与后端不一致 | `api.ts` 用 POST 但后端只注册了 GET（或反之） | CRITICAL |
| 后端有端点前端从未调用 | `gui_app.py` 注册了但 `api.ts` 没调用的端点（可能是废弃代码） | LOW |
| 前端调用了 `/api/drugs` 但返回类型不完整 | `AdministerDrugResponse` 缺少后端实际返回的字段 | HIGH |

**当前已知问题：**
- `api.ts` 有 12 个调用，`gui_app.py` 有 11 个 API 路由，全部匹配 ✅
- `api.ts` 没有调用 `GET /api/drugs`（后端注册了但前端没用）— LOW
- `AdministerDrugResponse` 缺少 `ap`/`max_ap`/`stress`/`pending_reports` 字段 — HIGH

### 检查 2：前后端类型一致性（对应 WAT 方案的命令注册检查）

| 检查项 | 规则 | 严重度 |
|--------|------|--------|
| `types.ts` 字段与后端返回不匹配 | `types.ts` 中每个接口的字段，`gui_app.py` 对应返回的 JSON 是否包含 | HIGH |
| `updateFrom()` 手动断言了 `types.ts` 未声明的字段 | `App.vue` 中 `updateFrom()` 的 assert 字段在 `types.ts` 中存在 | MEDIUM |
| `api.ts` 返回类型与 `types.ts` 不一致 | `api.ts` 中每个函数的泛型参数与 `types.ts` 接口匹配 | MEDIUM |

**当前已知问题：**
- `AdministerDrugResponse` 缺少后端实际返回的 6 个字段

### 检查 3：JSON 配置文件交叉一致性（对应 WAT 方案的数据管线检查）

| 检查项 | 规则 | 严重度 |
|--------|------|--------|
| 病例引用了不存在的疾病 | `cases.json[].disease` 必须在 `diseases.json.disease_names` 和 `ode_diseases.json` 中都存在 | CRITICAL |
| 线索 ID 没有描述 | `diseases.json.clues.*[]` 中的每个 clue_id 必须在 `clue_descriptions` 中有定义 | CRITICAL |
| 线索映射到了不存在的检查 | `diseases.json.clue_to_test` 的值必须是 `examinations.json` 中的 key | CRITICAL |
| 检查模板引用了不存在的生命体征 | `exam_templates.json.*.vitals.*` 必须是 `vitals_ranges.json` 中的 key | CRITICAL |
| 检查模板引用了不存在的检查类型 | `exam_templates.json.*.test_type` 必须是 `examinations.json` 中的 key | CRITICAL |
| 线索规则的 clue_id 没有描述 | `exam_templates.json.*.tag_rules.*.clue_id` 必须在 `clue_descriptions` 中有定义 | HIGH |
| 疾病有 clues 但无治疗协议 | `diseases.json.clues` 中的疾病必须在 `treatment_protocols` 中有对应 | HIGH |
| 疾病有协议但无比病例 | `diseases.json.disease_names` 中的疾病应至少在 `cases.json` 中被引用一次 | LOW |
| 检查模板与检查定义数量不一致 | `examinations.json` 有 21 个，`exam_templates.json` 有 20 个模板（允许无模板=纯信息检查） | LOW |
| 组合奖励引用了不存在的检查 | `game_config.json.combo_bonuses.*.tests.*` 必须是 `examinations.json` 中的 key | HIGH |
| ODE 输出目标路径有效 | `ode_diseases.json.*.outputs.*.target` 的 dot-path 必须在 `_PARAM_PATHS` 中存在 | HIGH |

**当前已知问题：**
- `examinations.json` 有 21 个检查，`exam_templates.json` 有 21 个模板（含 vestibular 可能没模板）— 需确认
- `ode_diseases.json` 有 10 个疾病，`diseases.json.disease_names` 也有 10 个，全部匹配 ✅
- `cases.json` 10 个病例全部引用了存在的疾病 ✅

### 检查 4：数据完整性（扩展项）

| 检查项 | 规则 | 严重度 |
|--------|------|--------|
| 有 TODO/FIXME 空实现 | `game/` 目录 `.py` 文件中的 `pass` 或 `return {}` 且带 TODO 注释 | MEDIUM |
| 疾病缺少 win/loss 消息 | `diseases.json.messages.win/loss` 应覆盖所有疾病 | MEDIUM |

---

## 二、工具设计

### 文件结构

```
virtual-vet/
├── tools/
│   └── dev/
│       ├── gate_check.py          # 统一入口 + hook 安装
│       ├── check_api_consistency.py   # 检查 1：API 端点一致性
│       ├── check_type_consistency.py  # 检查 2：前后端类型一致性
│       └── check_data_consistency.py  # 检查 3+4：JSON 交叉一致性 + 数据完整
├── docs/
│   └── gate_check_proposal.md     # 本文档
└── .git/hooks/pre-commit          # 自动安装
```

### gate_check.py — 统一入口

```python
#!/usr/bin/env python3
"""
Virtual Vet Gate Check — 提交前一致性检查

用法:
    python tools/dev/gate_check.py --quick     # API + 类型检查，<3s
    python tools/dev/gate_check.py --full      # 全套检查，<10s
    python tools/dev/gate_check.py --install-hook  # 安装 pre-commit hook

退出码: 0=通过, 1=CRITICAL/HIGH, 2=MEDIUM/LOW
环境变量: GATE_SKIP=1 跳过所有检查
"""
```

- `--quick`：只跑检查 1+2（API + 类型），3 秒内
- `--full`：跑检查 1+2+3+4，10 秒内
- `--install-hook`：写入 `.git/hooks/pre-commit`，每次 commit 自动跑 `--quick`
- `GATE_SKIP=1` 环境变量可跳过（输出 `[SKIPPED]`）

### 各检查脚本设计

#### check_api_consistency.py

**方法：** 静态解析，不运行服务

1. 读取 `gui_app.py`，用 `ast` 解析所有 `@app.route` 装饰器，提取 `(path, methods, function_name)`
2. 读取 `api.ts`，用正则提取所有 `invoke<...>(...)` 调用，提取 `(method, url)`
3. 对比：
   - 前端 URL 在后端路由中是否存在（精确匹配 + 路径参数匹配 `/api/cases/:id` ↔ `/api/cases/{id}`）
   - HTTP 方法是否一致
   - 后端有但前端没调用的路由 → LOW

**输出示例：**
```
[CRITICAL] api.ts:25 → POST /api/examine 后端未注册
[LOW] gui_app.py:137 → GET /api/drugs 前端从未调用
```

#### check_type_consistency.py

**方法：** 静态解析 + 字段对比

1. 用 `ast` 解析 `types.ts`（TypeScript 子集），提取所有 `interface` 的字段名和类型
2. 用 `ast` 解析 `gui_app.py`，找到每个 API 函数的 `return jsonify(...)` 语句，提取返回的字段名
3. 对比关键字段：
   - `GameState` ↔ `api_game_state` 返回的字段
   - `Report` ↔ `api_examine` 返回的字段
   - `AdministerDrugResponse` ↔ `api_administer_drug` 返回的字段

**注意：** 不做完整 TypeScript 类型检查（那是 `vp check` 的事），只检查字段是否存在。

#### check_data_consistency.py

**方法：** 读取所有 JSON，交叉验证

1. 加载 6 个 JSON 文件
2. 按检查 3 和检查 4 的规则逐项验证
3. 对 ODE 输出目标路径，额外检查 dot-path 是否以 `heart.` / `lung.` / `kidney.` / `blood.` / `fluid.` 开头（已知有效的 `_PARAM_PATHS` 前缀）

**输出示例：**
```
[CRITICAL] cases.json:case_011 → disease="foo" 在 diseases.json 中不存在
[HIGH] exam_templates.json:ecg → vitals=["XXX"] 在 vitals_ranges.json 中不存在
[LOW] diseases.json:urinary_obstruction → 未被任何病例引用
```

---

## 三、pre-commit Hook

### 安装方式

```bash
python tools/dev/gate_check.py --install-hook
```

### Hook 内容

```bash
#!/bin/sh
# .git/hooks/pre-commit
# 由 gate_check.py --install-hook 自动生成

if [ "$GATE_SKIP" = "1" ]; then
    echo "[GATE SKIPPED]"
    exit 0
fi

cd "$(git rev-parse --show-toplevel)"
python tools/dev/gate_check.py --quick
exit $?
```

### 行为

- `--quick` 模式，< 3 秒
- CRITICAL/HIGH → 阻止 commit，提示"修复后重试或使用 git commit --no-verify 跳过"
- MEDIUM/LOW → 警告但不阻止
- `--no-verify` 可跳过（留痕）

---

## 四、与现有工作流的关系

| 现有工具/流程 | gate_check 的关系 |
|---------------|------------------|
| `pytest tests/` | gate_check 不替代测试，检查的是测试覆盖不到的文件间一致性 |
| `vp check`（前端 format+lint+type） | gate_check 不替代，vp check 管前端内部质量，gate_check 管跨文件契约 |
| `python gui_app.py` | gate_check 是静态分析，不启动服务 |
| CLAUDE.md 中的 SOP | gate_check 是 SOP 的自动化执行，SOP 指导人，gate_check 强制执行 |

**建议的提交前流程：**
```
代码修改 → gate_check --quick（自动，<3s）→ vp build（前端改动时）→ pytest（核心改动时）→ commit
```

---

## 五、落地路线图

### Phase A：核心检查（1 天）

| 任务 | 文件 | 工时 |
|------|------|------|
| check_api_consistency.py | `tools/dev/check_api_consistency.py` | 2h |
| check_data_consistency.py | `tools/dev/check_data_consistency.py` | 3h |
| gate_check.py + hook | `tools/dev/gate_check.py` | 1h |
| 安装并测试 hook | 本地 git config | 0.5h |
| **合计** | | **6.5h** |

**验收标准：**
- 对当前代码库运行 `--full`，发现至少 1 个已知问题（`AdministerDrugResponse` 字段缺失）
- pre-commit hook 能成功拦截有问题的 commit
- 全量检查 < 10 秒

### Phase B：类型检查（0.5 天）

| 任务 | 文件 | 工时 |
|------|------|------|
| check_type_consistency.py | `tools/dev/check_type_consistency.py` | 3h |
| 修复发现的不一致 | `types.ts` | 1h |
| **合计** | | **4h** |

### Phase C：长期优化

- 引入 JSON Schema 校验（替代手写检查逻辑）
- 冒烟测试：启动 Flask → 调每个 API → 确认 200
- 新增疾病/检查的 SOP checklist（补全 CLAUDE.md）

---

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| 脚本过时（API 写法变化导致误报） | 输出标注置信度；提供 `.gateignore` |
| 假阳性过高导致集体跳过 | Phase A 优先校准精确度 > 覆盖面 |
| hook 拖慢 commit | --quick < 3s；GATE_SKIP=1 逃生舱 |
| Python 版本兼容 | 零外部依赖，仅 stdlib + ast |
