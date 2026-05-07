# 项目上下文 — 兽医诊断 ODE 仿真游戏

> 下次对话开始时，直接把此文件内容粘贴给 AI，即可快速接手。

---

## 一、项目总览

**类型**：兽医临床诊断教育游戏。玩家扮演兽医，通过开具检查→分析报告→做出诊断→治疗患犬，学习临床推理。

**技术栈**：
- **后端**：Python 3 + Flask（`gui_app.py` 为入口），多器官 ODE 仿真引擎
- **前端**：Vue 3 + TypeScript + Vite，构建后产物放 `static/`，由 Flask 模板 `templates/game.html` 引用
- **数据**：JSON 文件（病例、检查项目、治疗方案）

**启动方式**：
```bash
# 终端 1：Flask 后端
cd Desktop/my_project
python gui_app.py          # http://127.0.0.1:5000

# 终端 2：Vite 开发服务器（可选，用于前端热更新）
cd Desktop/my_project/vet-game-frontend/vite-project
npx vite --host 0.0.0.0 --port 5173
```

**⚠️ 构建产物同步**：每次前端代码变更后必须重新构建并更新模板引用：
```bash
cd vet-game-frontend/vite-project
npx vite build --outDir ../static
# 然后手动更新 templates/game.html 中的 JS/CSS 文件名（hash 会变）
```

---

## 二、目录结构

```
Desktop/my_project/
├── gui_app.py              # Flask 入口，所有 API 路由
├── main.py                 # CLI 入口
├── src/                    # ODE 仿真引擎核心
│   ├── simulation.py       # VirtualCreature — 整合所有器官的主引擎
│   ├── blood.py            # BloodCompartment — 血液隔室
│   ├── heart.py            # HeartModule — 心脏（HR, SV, CO, SVR）
│   ├── lung.py             # LungModule — 肺（通气、氧合、SpO2）
│   ├── kidney.py           # KidneyModule — 肾脏（GFR、尿量、RAAS）
│   ├── fluid.py            # FluidCompartment — 三室体液模型（血管/ISF/ICF）+ HendersonHasselbalch
│   ├── toxicology.py       # ToxicologyModule
│   ├── organ_health.py     # OrganHealthTracker
│   ├── pharmacology.py     # Drug / PharmacologyState — PK/PD 药物模型
│   ├── parameters.py       # 生理参数常量（按体重缩放）
│   └── diseases/           # 疾病模块
│       ├── __init__.py     # DiseaseModule 基类 + create_disease() 工厂
│       ├── pneumonia.py    # PneumoniaModule — 4 ODE（渗出物/细菌/发热/缺氧）
│       ├── acute_renal_failure.py
│       └── dilated_cardiomyopathy.py
├── game/                   # 游戏逻辑层
│   ├── action_system.py    # GameState + process_action() — 行动处理、阶段判定、死亡倒计时
│   ├── diagnosis_engine.py # 线索提取 + 置信度匹配 + 建议检查
│   ├── treatment.py        # 治疗判定（is_correct / apply_treatment）+ 药物协议执行
│   ├── time_manager.py     # 游戏时钟、夜间检测（22:00-06:00）、夜间 HR/疾病进展修正
│   ├── test_translator.py  # 引擎数值 → 可读检查报告
│   └── case_generator.py   # 病例生成器
├── data/
│   ├── cases.json          # 3 个病例（肺炎/肾衰/DCM）
│   ├── examinations.json   # 10 种检查（体格/听诊/视诊/血常规/生化/血气/X光/超声/CT/心电图）
│   ├── treatments.json     # 4 个治疗选项（3 疾病 + 支持治疗）
│   └── drugs.json          # 药物库
├── templates/
│   └── game.html           # Flask 模板，引用 static/assets/ 下的构建产物
├── static/                 # Vite 构建产物（npx vite build --outDir ../static）
│   ├── index.html
│   └── assets/
├── tests/                  # pytest 测试
│   ├── test_fluid.py       # 37 项 — 三室体液/Starling/电解质/HH 方程
│   ├── test_time_management.py  # 21 项 — 行动点/时间流速/夜间/HR 可逆性
│   ├── test_game.py        # 游戏流程测试
│   ├── test_pharmacology.py
│   └── ...（其他器官测试）
└── vet-game-frontend/vite-project/  # Vue 前端源码
    ├── src/
    │   ├── App.vue          # 根组件 — 状态管理、API 调用、夜间主题 toggle
    │   ├── api.ts           # API 客户端（封装所有 /api/* 调用）
    │   ├── types.ts         # TypeScript 接口定义
    │   └── components/
    │       ├── CaseSelect.vue      # 病例选择页
    │       ├── PatientCard.vue     # 患犬信息卡
    │       ├── ExamGrid.vue        # 检查项目网格
    │       ├── ReportList.vue      # 检查报告列表（可折叠）
    │       ├── DiagnosisPanel.vue  # 诊断选项 + 置信度面板 + 建议检查
    │       ├── VitalCard.vue       # 单个体征卡片（含夜间 HR 提示）
    │       ├── GameLog.vue         # 操作日志
    │       └── GameOverOverlay.vue # 游戏结束弹窗
    └── src/style.css        # 全局样式（含 body.night-mode 夜间主题）
```

---

## 三、核心数据流

### 游戏流程
```
1. GET  /api/cases              → 加载病例列表
2. POST /api/new-game {case_id} → 创建 session，初始化 VirtualCreature + 注入疾病
3. POST /api/examine {test_type}→ 开具检查 → test_translator 生成报告 → 返回报告 + 最新体征
4. GET  /api/diagnosis          → 获取置信度匹配结果 + 建议检查
5. POST /api/diagnose {diagnosis}→ 提交诊断 → treatment.py 判定 → 正确则给药+进入 won
6. POST /api/wait               → 等待 → 推进仿真 60s → 疾病进展
7. POST /api/administer-drug    → 紧急给药（PK/PD 模型）
```

### GameState（action_system.py）
```python
@dataclass
class GameState:
    engine: VirtualCreature      # 仿真引擎实例
    disease_name: str            # 真实疾病名称
    phase: str                   # "playing" / "won" / "lost"
    death_timer: int | None      # 濒死倒计时（进入 moribund 后）
    current_ap: int              # 剩余时间预算（AP = 时间单位）
    max_ap: int                  # 时间预算上限
    total_ap_spent: int          # 累计消耗 AP → 游戏时间 = total_ap_spent × 60s
```

### 病情阶段判定（自动涌现，非硬编码时间表）
- 基于 MAP / SpO2 / HR / pH 的阈值判定
- stable → worsening → critical → moribund → lost（死亡）
- moribund 后 `death_timer = 3`（还能做 3 次行动）

### 疾病模块架构
每个疾病是独立的 ODE 系统，返回**乘法因子**给引擎：
```python
factors = {
    "lung":  {"diffusion_multiplier": 0.7},  # 肺扩散能力降至 70%
    "heart": {"heart_rate_offset": 20, "svr_multiplier": 0.8},
    "kidney": {"gfr_multiplier": 0.3},
}
```
引擎每步 `step(dt)` 调用所有器官模块 + 疾病模块的 `compute()`。

### 检查报告线索系统（diagnosis_engine.py）
- 每种疾病有预定义的线索 ID 列表（如 `"PaO2_low"`, `"crackles"`）
- 检查报告通过 `test_translator.py` 从引擎数值生成，包含 `flag`（high/low/critical）
- `match_diseases()` 根据已收集线索计算置信度 = 匹配线索数 / 总线索数
- `get_suggested_tests()` 根据未匹配线索推荐下一步检查

---

## 四、关键 API 路由

| 路由 | 方法 | 功能 |
|------|------|------|
| `/` | GET | 渲染 game.html |
| `/assets/<path>` | GET | 提供构建产物 |
| `/api/cases` | GET | 所有病例 |
| `/api/examinations` | GET | 所有检查定义 |
| `/api/treatments` | GET | 所有治疗选项 |
| `/api/drugs` | GET | 所有药物 |
| `/api/new-game` | POST | `{case_id}` → 创建游戏 |
| `/api/examine` | POST | `{session_id, test_type}` → 开具检查 |
| `/api/wait` | POST | `{session_id}` → 等待 |
| `/api/diagnose` | POST | `{session_id, diagnosis}` → 提交诊断 |
| `/api/administer-drug` | POST | `{session_id, drug}` → 给药 |
| `/api/game-state` | GET | `{session_id}` → 当前状态 |
| `/api/diagnosis` | GET | `{session_id}` → 置信度匹配 |
| `/api/hint` | GET | `{session_id}` → 提示 |

---

## 五、游戏数据

### 病例（data/cases.json）
| ID | 疾病 | 难度 | 体重 |
|----|------|------|------|
| case_001 | 肺炎 pneumonia | ★☆☆ | 20kg |
| case_002 | 急性肾衰竭 acute_renal_failure | ★★☆ | 30kg |
| case_003 | 扩张型心肌病 dilated_cardiomyopathy | ★★★ | 35kg |

### 治疗选项（data/treatments.json）
- key = 治疗 ID，`correct_for` = 对应疾病
- 诊断正确后，treatment.py 中的 `_DRGUG_PROTOCOL` 执行实际给药
  - DCM: pimobendan 0.25 mg/kg + furosemide 1.0 mg/kg
  - 肺炎: fluid_bolus 200 mL
  - 肾衰: fluid_bolus 300 mL

### 夜间系统（game/time_manager.py）
- 游戏从 08:00 开始，夜间 = 22:00-06:00
- 夜间 HR × 0.85（生理性心动过缓），疾病进展 × 0.8
- HR 可逆：进入夜间时保存 `_original_hr_rest`，白天恢复
- 前端 `body.night-mode` class 切换深蓝紫色主题

---

## 六、已完成功能清单

- [x] 多器官 ODE 仿真引擎（心/肺/肾/血液/毒理）
- [x] 三室体液模型 + Starling 力 + 电解质转运 + Henderson-Hasselbalch pH
- [x] 三种疾病 ODE 模型（肺炎/肾衰/DCM）
- [x] PK/PD 药物模型（一室 PK + Hill 方程 PD）
- [x] 行动点系统（不同检查消耗不同点数）
- [x] 游戏时钟 + 夜间系统 + HR 可逆性
- [x] 检查报告翻译 + 线索提取 + 置信度匹配
- [x] 治疗判定（诊断→给药→胜负）
- [x] 濒死倒计时 + 死亡判定
- [x] Vue 3 前端（病例选择/检查/报告/诊断/体征/日志）
- [x] 夜间 UI 主题（body.night-mode + 时钟显示 + HR 夜间提示）
- [x] 前端构建产物由 Flask 模板引用

---

## 七、已知问题与注意事项

1. **模板 hash 同步**：Vite 构建后文件名 hash 会变，必须手动更新 `templates/game.html` 中的 JS/CSS 引用。每次前端改代码后都要做。

2. **Session 存储**：`gui_app.py` 用全局 dict `SESSIONS: dict[str, GameState]` 存 session，重启 Flask 后所有 session 丢失。

3. **Flask 热重载**：修改 Python 代码后 Flask debug 模式会自动重启，但修改后如果报 import 错误需要手动重启。

4. **前端类型安全**：`updateFrom()` 使用 `Record<string, unknown>` + 手动类型断言，不是类型安全的。新增 API 字段时需要同步更新 `types.ts` 和 `updateFrom()`。

5. **检查 cost=0 但消耗 1 行动点**：`_get_examine_cost()` 对 cost=0 的检查返回 1（至少消耗 1 行动）。

6. **诊断选项只显示疾病名**：`DiagnosisPanel.vue` 中 `diagnosisOptions` 的 label 来自 `diseaseNameMap[correct_for]`，不再显示治疗描述。

---

## 八、测试

```bash
# 运行所有测试
cd Desktop/my_project
python -m pytest tests/ -v

# 运行特定测试
python -m pytest tests/test_fluid.py tests/test_time_management.py -v
```

测试覆盖：fluid(37), time_management(21), game, pharmacology, diseases, heart, lung, kidney, blood, interface 等。

---

## 九、开发约定

- **代码风格**：Python 遵循 PEP 8 + ruff 格式；前端 TypeScript 严格模式
- **TDD**：核心模块（fluid, time_manager, pharmacology）先写测试再实现
- **不可变优先**：数据类用 `@dataclass(frozen=True)`
- **注释**：只写"为什么"，不写"做了什么"；hack/TODO 必须带日期
- **API 响应格式**：`{success: bool, ...}` 或直接在顶层返回数据
- **日志**：用 `logging` 模块，不用 `print()`
