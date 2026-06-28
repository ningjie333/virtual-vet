# Virtual Vet — Code Wiki

> 结构化代码百科文档。本文档自动整理自项目源码分析，覆盖整体架构、模块职责、关键类与函数、依赖关系与运行方式。
> 权威性参考：`README.md` 与 `docs/architecture.md`。本文档为代码导览，遇到语义冲突以权威文档为准。

---

## 目录

1. [项目概述](#1-项目概述)
2. [整体架构](#2-整体架构)
3. [目录结构总览](#3-目录结构总览)
4. [生理内核层 (Kernel)](#4-生理内核层-kernel)
5. [临床解释层 (Clinical Interpretation)](#5-临床解释层-clinical-interpretation)
6. [应用 / 游戏层 (Application / Game)](#6-应用--游戏层-application--game)
7. [GUI 与入口点](#7-gui-与入口点)
8. [前端层 (Frontend)](#8-前端层-frontend)
9. [数据文件与配置](#9-数据文件与配置)
10. [依赖关系](#10-依赖关系)
11. [项目运行方式](#11-项目运行方式)
12. [测试体系](#12-测试体系)
13. [关键设计模式与约定](#13-关键设计模式与约定)

---

## 1. 项目概述

**Virtual Vet** 是一个以生理学引擎为核心、外层包裹临床诊断教学游戏的兽医虚拟仿真项目。

**定位**：文献驱动、临床落地的多器官生理仿真引擎，外加围绕其构建的教学应用。验证仍在持续进行；文档刻意避免将游戏层的抽象当成内核真相。

**技术栈**：

| 层 | 技术 |
|----|------|
| 后端内核 / 应用 | Python 3.10+，NumPy / SciPy / Flask |
| 前端 | Vue 3 (`<script setup lang="ts">`) + TypeScript + Vite+ (`vp` CLI) |
| 数据 | JSON Schema 校验的声明式配置（疾病/检查/报告/线索） |
| 测试 | pytest（多通道：fast / core / heavy / benchmark） |
| 持久化 | SQLite（会话与动作日志） |

**核心价值**：

- 以"内核优先"原则组织代码：生理引擎是产品核心，游戏与应用是外层。
- 多器官 ODE 耦合仿真：心血管 / 呼吸 / 肾 / 肝 / 血液 / 体液 / 肠道 / 内分泌 / 神经 / 免疫 / 凝血 / 淋巴共 11 个器官系统。
- 双求解器路径：Euler（生产）+ Radau（验证 / 研究）。
- 配置驱动扩展：新增疾病 / 检查 / 报告模板只需编辑 JSON，无需写 Python。

---

## 2. 整体架构

### 2.1 三层架构

```
┌──────────────────────────────────────────────────────────────┐
│  Application / Game Layer                                    │
│  game/ · gui_app.py · vet-game-frontend/ · case JSON          │
│  病例编排 · 诊断玩法 · 时间预算 · 会话持久化 · UI             │
└──────────────────────────────────────────────────────────────┘
                          │  允许调用
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  Clinical Interpretation Layer                               │
│  clinical_signs_engine · report_engine · clinical_interpreter│
│  clinical_snapshot · clinical_stage · debug_params · ...     │
│  将引擎状态翻译为可观察体征 / 报告 / 阶段 / 摘要             │
└──────────────────────────────────────────────────────────────┘
                          │  允许调用
                          ▼
┌──────────────────────────────────────────────────────────────┐
│  Physiology Kernel                                           │
│  simulation.py · src/organs/ · src/diseases/ · src/engine/   │
│  parameters.py · common_types.py                             │
│  在物理时间中演化生理状态 · 维持求解器行为 · 定义疾病写入接口 │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 依赖方向（强约束）

**允许**：

- `application/game → clinical interpretation`
- `application/game → kernel`
- `clinical interpretation → kernel`

**禁止**：

- `kernel → game/application`（内核不得反向依赖应用层）
- 内核方程依赖 AP / 时间预算 / 回合数 / UI 状态
- 为了游戏节奏在内核内部重标度疾病率常数

### 2.3 三种时间语义

| 时间类型 | 归属 | 示例 | 规则 |
|----------|------|------|------|
| **物理时间 (Physical)** | 内核原生 | `current_time_s`、`dt`、ODE 状态演化 | 改变生理学的行为必须以物理时间表达 |
| **场景时间 (Scenario)** | 应用层调度 | "wait 10 min"、"CT 消耗 45 min" | 应用层决定推进多少物理时间，不得重定义内核率 |
| **表现时间 (Presentation)** | 仅显示 | `08:00`、夜/昼标签、UI 时间戳 | 可从场景时间派生，本身非内核机制 |

**当前时间映射**（应用层映射，非内核定义）：游戏动作按相同分钟数推进引擎，即 `1 游戏分钟 = 1 引擎分钟`。

### 2.4 求解器状态

- `VirtualCreature` 同时包含 Euler 与 Radau 两条执行路径
- **当前游戏应用默认使用 Euler**（`SolverRegistry.get("euler")`）
- Radau 仍是重要的验证与研究路径，但不应被默认文档化为游戏默认

---

## 3. 目录结构总览

```
virtual-vet/
├── src/                         # 生理内核 + 临床解释层
│   ├── simulation.py            # VirtualCreature 总装配类
│   ├── parameters.py            # 物种参数与生理常数
│   ├── common_types.py          # FactorCommand 与参数路径白名单
│   ├── engine/                  # 求解器 / 状态向量 / 因子管线 / 信号总线 / 拓扑
│   │   ├── solvers/             # SolverPlugin 抽象 + Euler/Radau 实现
│   │   ├── factor_pipeline.py
│   │   ├── signal_bus.py
│   │   ├── state_vector.py
│   │   ├── step_common.py
│   │   ├── topology.py
│   │   └── twin_run.py
│   ├── organs/                  # 器官契约 (Protocol) 与耦合引擎
│   │   ├── contracts.py
│   │   └── coupling.py
│   ├── diseases/                # 疾病模块框架与配置驱动引擎
│   │   └── config_driven.py
│   ├── *.py                     # 11 个器官模块（heart/lung/kidney/...）
│   ├── clinical_*.py            # 临床解释层（signs/snapshot/stage/state/interpreter）
│   ├── report_engine.py
│   ├── exam_registry.py
│   ├── vitals_config.py
│   ├── pharmacology.py          # 药理 PK/PD
│   ├── toxicology.py            # 毒理（可卡因）
│   ├── presentation_state.py    # 就诊起始状态构建器
│   ├── engine_advancer.py       # 应用层推进器接口
│   ├── organ_health.py         # 不可逆器官损伤追踪
│   ├── organ_guard.py           # 器官写保护
│   ├── lifecycle*.py            # 生命周期引擎（发育/衰老/死亡）
│   ├── db/                      # SQLite 持久化
│   ├── textual_monitor.py      # Textual 终端 UI
│   ├── ascii_dashboard.py       # ASCII 仪表盘
│   ├── cli.py / cli_common.py   # vet-monitor CLI
│   └── ...
├── game/                        # 应用 / 游戏层
│   ├── action_system.py         # GameState + process_action 中央循环
│   ├── runtime.py               # GameRuntime 组合根
│   ├── runtime_composition.py   # 解释栈外层组合
│   ├── case_generator.py        # 病例生成器
│   ├── diagnosis_engine.py      # 诊断匹配引擎
│   ├── treatment.py             # 治疗判定
│   ├── time_manager.py          # 游戏时钟 + 夜间逻辑
│   └── test_translator.py       # Legacy 报告翻译
├── gui_app.py                   # Flask 主应用 + REST API
├── main.py / cli_daemon.py / vet_monitor.py / cli_shim.py  # 各类入口
├── data/                        # 声明式 JSON 配置（疾病/检查/报告/线索/...）
├── vet-game-frontend/vite-project/   # Vue 3 前端
├── tests/                       # pytest 测试套件
├── tools/dev/                   # 开发工具（gate_check / 一致性校验 / 敏感度）
├── docs/                        # 架构与设计文档
├── pyproject.toml               # Python 项目配置
└── AGENTS.md / CLAUDE.md        # Agent 与贡献者指南
```

---

## 4. 生理内核层 (Kernel)

内核位置：`src/simulation.py`、`src/organs/`、`src/diseases/`、`src/engine/`、`src/common_types.py`、`src/parameters.py`，以及散在 `src/*.py` 的各器官模块。

**内核职责**：

- 在物理时间中演化生理状态
- 维持求解器行为与模块耦合
- 定义疾病状态演化与干预写入接口
- 向下游消费者暴露引擎状态

**内核不得拥有**：动作预算、病例节奏、检查延迟、胜负逻辑、会话存储、UI 时钟或显示标签。

### 4.1 `VirtualCreature` — 总装配类

文件：[src/simulation.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/simulation.py)

#### 构造函数

```python
class VirtualCreature:
    def __init__(
        self,
        body_weight_kg: float = 20.0,
        species: str = "canine",
        age_days: float = 1095.0,            # DEFAULT_AGE_DAYS
        dt: float = None,                    # None → DT_SECONDS = 0.1s
        solver: str = "euler",               # 通过 SolverRegistry.get() 注入
        lifecycle_mode: str = "bypass",
        record_history: bool = True,
        legacy_clinical_signs_enabled: bool = True,
    )
```

#### 主要属性

| 属性 | 说明 |
|------|------|
| `self.w` / `self.species` | 体重、物种 |
| `self._solver` | 注入的 `SolverPlugin` 实例 |
| `self._signal_bus` | Phase 4 引擎数据总线（`SignalBus`） |
| `self._real_blood` / `self.blood` | `BloodCompartment` 实体与其 `BloodShim` 透明代理 |
| `self.heart / lung / kidney / ...` | 11 个器官实例 |
| `self.coupling_engine` | `CouplingEngine` 多器官耦合规则引擎 |
| `self._organ_contexts` | `dict[str, OrganContext]` 每器官信号总线 |
| `self.organ_health` | `OrganHealthTracker` 不可逆器官损伤追踪 |
| `self.lifecycle` | `LifecycleEngine` 生长发育/衰老/死亡引擎 |
| `self.diseases` | `list[DiseaseModule]` 多病叠加列表 |
| `self._cached_inputs` | 半隐式耦合缓存（Radau 路径） |
| `self.history` | `dict[str, list]` 完整历史时间序列（约 40 个键） |
| `self._scheduled_events` | 场景事件队列 |

#### 核心方法

| 方法 | 签名 | 职责 |
|------|------|------|
| `step` | `step() -> dict` | 委托给注入的 `SolverPlugin.step()`（Euler 或 Radau） |
| `_step_euler` | `_step_euler() -> dict` | Euler 显式路径（**生产路径**）。Steps 0~8：事件→毒理→药理→心脏→疾病→肺→肾→肠道→肝→内分泌→凝血→淋巴→神经→免疫→耦合→器官健康→静脉血气→代谢物→fluid→耦合→记录 |
| `_step_radau` | `_step_radau() -> dict` | 委托给 `engine.solvers.radau.run_radau_step`，调用 `scipy.solve_ivp(method="Radau")` 隐式积分 |
| `attach_disease` | `attach_disease(disease_module)` | 追加疾病到 `self.diseases`（支持多病叠加，chained-rebase 合并语义） |
| `apply_factor` | `apply_factor(cmd: FactorCommand) -> None` | 统一因子写入接口，委托给 `engine.factor_pipeline.apply_factor` |
| `schedule_event` | `schedule_event(time_s, event_type, params)` | 注册场景事件（blood_loss / fluid_infusion / exercise / food_intake / cocaine） |
| `set_blood_loss_scenario` | `set_blood_loss_scenario(t_onset, total_ml, duration=300.0, width=5.0)` | 配置连续 ODE 失血场景 |
| `to_persistence_snapshot` | `to_persistence_snapshot() -> dict` | 序列化引擎状态用于会话持久化 |
| `advance_seconds` | `advance_seconds(duration_seconds, verbose=False)` | 推进物理时长 |
| `simulate` | `simulate(duration_minutes, verbose=False)` | 兼容旧接口（按分钟） |
| `run_ivp` / `run_unified_ivp` | `(t_end, dt_save=1.0)` | 直接 `scipy.solve_ivp` 跑 ODE 子系统 |
| `_unified_rhs` | `_unified_rhs(t, y) -> np.ndarray` | 统一 ODE 右端（转发到 `state_vector.unified_rhs`） |
| `_handle_death` | `_handle_death(cause: str) -> None` | 记录死亡原因，停止仿真 |
| `run_scenario` | `run_scenario(scenario_name)` | 运行预设场景 |

### 4.2 参数与类型契约

#### `src/parameters.py`

文件：[src/parameters.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/parameters.py)

**设计原则**：参数分两类
- **A 类（函数）**：随体重变化，调用时传入 `weight_kg`
- **B 类（常量）**：通用生理常数

**关键函数**：

| 函数 | 说明 |
|------|------|
| `species_hr(species, stress=False) -> float` | 物种感知心率（canine=85 / feline=150 / equine=35 bpm） |
| `species_rr(species, stress=False) -> float` | 物种感知呼吸频率 |
| `species_paco2(species) -> float` | 物种感知 PaCO2 |
| `fever_threshold_c(species) -> float` | 发热阈值（犬 39.2 / 猫 39.5 / 马 38.5°C） |
| `total_blood_volume_ml(weight_kg, species="canine") -> float` | 总血容量 |
| `stroke_volume_ml(weight_kg) -> float` | 每搏输出量 |
| `base_cardiac_output_ml_min(weight_kg) -> float` | 基础心输出量 |
| `base_DO2_normal_ml_min(weight_kg, species="dog") -> float` | 正常氧输送 |

**关键常量**：

- 物种血容量系数：`BLOOD_VOLUME_ML_KG_CANINE=86.0 / FELINE=55.0 / EQUINE=76.0`
- 心率：`HEART_RATE_REST_BPM=85`（含 `_CANINE/_FELINE=150/_EQUINE=35` 别名）
- 硬限：`HEART_RATE_HARD_MIN=5.0`, `HEART_RATE_HARD_MAX=250.0`
- 血管阻力：`SYSTEMIC_VASCULAR_RESISTANCE=1.41`, `PULMONARY_VASCULAR_RESISTANCE=0.18`
- 求解器参数：`DT_SECONDS=0.1`, `SIMULATION_STEP_MS=100`, `T_MAX_MINUTES=10`

#### `src/common_types.py`

文件：[src/common_types.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/common_types.py)

**核心数据结构**：

```python
@dataclass(frozen=True)
class FactorCommand:
    """单条因子指令 — 跨模块写入的唯一来源"""
    target: str                                  # "module.attr" 如 "heart.heart_rate"
    op: Literal["multiply", "add", "set"]
    value: float
```

**参数路径白名单**：`_PARAM_PATHS: dict[str, tuple[str, str]]`
- 约 100+ 条目，将逻辑路径 `"heart.heart_rate"` 映射到 `("heart", "heart_rate")`（模块名 + 属性名）
- 涵盖 heart / lung / kidney / blood / gut / liver / endocrine / neuro / immune / coagulation / lymphatic 全部可写参数

**辅助函数**：
- `resolve_param_path(target: str) -> tuple[str, str] | None`
- `validate_target(target: str) -> bool`

### 4.3 求解器架构 (`src/engine/`)

#### `engine/solvers/__init__.py` — SolverPlugin 插件框架

文件：[src/engine/solvers/__init__.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/solvers/__init__.py)

```python
class SolverPlugin(ABC):
    @abstractmethod
    def step(self, engine: "VirtualCreature") -> dict: ...
    @property
    @abstractmethod
    def name(self) -> str: ...
    @property
    @abstractmethod
    def order(self) -> int: ...            # Euler=1, RK4=4, Radau=5
    @property
    @abstractmethod
    def solver_type(self) -> Literal["explicit", "implicit"]: ...

class SolverRegistry:
    _entries: dict[str, type[SolverPlugin]]
    @classmethod
    def register(cls, name, solver_cls): ...
    @classmethod
    def get(cls, name) -> SolverPlugin: ...
```

**已注册插件**：`EulerSolver` (euler) + `RadauSolver` (radau)

#### `engine/solvers/radau.py` — Radau 隐式求解器

文件：[src/engine/solvers/radau.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/solvers/radau.py)

**核心函数**：`run_radau_step(engine: VirtualCreature) -> dict`

**执行流程**：
1. `_process_events(t)` 处理事件
2. `lifecycle.apply_age_factors` + `death_check`
3. `_pack_unified_state()` 打包 `y0`
4. 预热 `_unified_rhs(t, y0)` 初始化缓存
5. `solve_ivp(method='Radau', rtol=1e-5, atol=1e-8)` 在 `[t, t+dt]` 上积分
6. 失败则退化到 `_step_euler()`，计数 `_solver_fallback_count`
7. 解包结果，通过 `apply_factor` 应用 lung/kidney/immune/endocrine/coagulation/gut 的 blood 输出
8. `run_physiology_post` + `run_coupling` 后处理
9. 8 个模块的 `compute()` 补全调用
10. 疾病模块计算
11. 器官健康追踪 + organ_health 因子应用
12. 记录 history，推进时间

#### `engine/factor_pipeline.py` — 因子管线

文件：[src/engine/factor_pipeline.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/factor_pipeline.py)

**核心函数**：

```python
def apply_factor(cmd: FactorCommand, engine: Any) -> None
```

- 查找 `_PARAM_PATHS` 白名单
- 执行 `multiply` / `add` / `set`
- C7 特殊保护：`heart.blood_volume` 不允许变负
- 未知 target/op 静默警告（fail-safe）

**辅助类**：`FactorCommandRegistry`（白名单查询封装，Phase 5+ 用于遥测/重放）

#### `engine/signal_bus.py` — 信号总线

文件：[src/engine/signal_bus.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/signal_bus.py)

**两个核心类**：

1. **`SignalBus`** — 引擎数据总线
   - `_write_count` / `_read_count`：诊断用字段计数
   - `_module_contracts`：Phase 5 I/O 契约注册表
   - `publish_blood(name, value)` / `read_blood(name)`
   - `register_module(name, inputs, outputs, reads_blood, writes_blood)`
   - `real_blood` property — 暴露真实 `BloodCompartment`（Phase 6 迁移用）
   - `stats()` — 诊断统计

2. **`BloodShim`** — `BloodCompartment` 透明代理
   - `__slots__ = ("_real", "_bus")`
   - `__getattr__` 拦截读取 → 记录到 bus → 转发到 real
   - `__setattr__` 拦截写入 → 记录到 bus → 转发到 real
   - 9 个器官模块代码不变（`self.blood.X = value` 仍工作）

#### `engine/state_vector.py` — 状态向量

文件：[src/engine/state_vector.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/state_vector.py)

**模块注册表**：

```python
UNIFIED_MODULES = [
    ("heart", "heart"), ("lung", "lung"), ("kidney", "kidney"),
    ("fluid", "fluid"), ("gut", "gut"), ("liver", "liver"),
    ("endocrine", "endocrine"), ("neuro", "neuro"), ("immune", "immune"),
    ("coagulation", "coagulation"), ("lymphatic", "lymphatic"),
]
```

**核心函数**：

- `build_state_map(engine) -> dict[(module, ode_name), int]` — 从各模块 `STATE_VARS` 构建索引
- `pack_state(engine) -> np.ndarray` — 状态打包
- `unpack_state(engine, y)` — 状态解包，调用可选 `_post_unpack_state` 钩子（仅 heart 用于 MAP 同步）
- `unified_rhs(engine, t, y) -> np.ndarray` — **统一 ODE 右端函数**

**半隐式 Gauss-Seidel 耦合策略**（关键设计）：
- 每次 `rhs(t, y)` 调用时，各模块的 `derivatives()` **只读 `_cached_inputs`**（上一次调用的 outputs 经 CONNECTIONS 路由）
- 模块按固定顺序求导（heart → lung → kidney → gut → liver → ... → fluid）
- gut 输出直接作为 liver 输入（intra-call 直传）
- Radau 的 Newton 迭代自动收敛到耦合不动点

#### `engine/step_common.py` — 通用步进

文件：[src/engine/step_common.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/step_common.py)

**辅助函数**：

- `_apply_urine_blood_loss(engine, dt)` — Step 7.5：尿量 → 循环血量损失
- `_apply_fluid_and_ph(engine, dt)` — Step 7.6：三室体液 + Henderson-Hasselbalch pH
- `_sync_blood_volume(engine)` — Step 7.7：同步 `blood.total_volume_ml` 与 `heart.circulating_volume_ml`

**主入口**：

- `run_pre_dispatch(engine) -> bool` — Steps 0-0.5（事件 + 连续失血 sigmoid + lifecycle + death_check），返回 True 表示应停止
- `run_physiology_post(engine, dt) -> dict` — Steps 7.5-7.7
- `run_coupling(engine, dt, signal_time)` — Step 8：发布信号 + 解析耦合规则
- `run_post_dispatch(engine, dt, signal_time) -> dict` — 便捷包装

**信号发布辅助函数**：`_publish_heart_signals` / `_publish_lung_signals` / `_publish_kidney_signals` / `_publish_blood_signals` / `_publish_fluid_signals` / `_publish_liver_signals`

#### `engine/topology.py` — 拓扑结构

文件：[src/engine/topology.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/topology.py)

**三个核心组件**：

1. **`CONNECTIONS: dict[(src_module, src_var), list[(tgt_module, tgt_var)]]`**
   - **仅 Radau 路径使用**（intra-step 数据流，供 `_unified_rhs` 路由 outputs→cached_inputs）
   - **Euler 路径不用**，使用 `CouplingEngine` + `data/coupling_rules.json`
   - 涵盖 heart/lung/blood/kidney/fluid/endocrine/neuro/immune/coagulation/liver/gut/lymphatic 跨模块信号
   - 文档明确标注已知 dead routes（命名不匹配被静默跳过）

2. **`_PARAM_PATHS: dict[str, tuple[str, str]]`** — `apply_factor` 白名单协议（与 `common_types.py` 中定义的相同，已迁移至此）

3. **`Topology` dataclass + `discover_topology(modules)`** — Phase 5 占位符，未来从模块 `INPUTS/OUTPUTS` 自动派生 CONNECTIONS

#### `engine/twin_run.py` — 双生运行

文件：[src/engine/twin_run.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine/twin_run.py)

**用途**：求解器重构的安全网。同一场景通过两条积分路径运行并对比 vital 轨迹。

**关键数据结构**：

- `VITAL_TOLERANCES: dict[str, float]` — 每 vital 相对容差（如 `HR_bpm=0.02`, `urine=0.20`）
- `SCENARIO_MULTIPLIERS: dict[str, float]` — 场景严重度倍数（healthy=1.0, disease_severe=3.0）
- `TwinRunConfig` — 配置（body_weight_kg, species, dt_prod=0.1, refinement=10, n_steps_prod=60, reference_solver）
- `TwinRunResult` — 结果（converged, max_rel_error, tolerance, fallback_count, worst_vital）

**场景注册表** `SCENARIOS`：healthy / blood_loss_mild / blood_loss_severe / fluid_resuscitation / arf_moderate / arf_severe / dcm_moderate / hypoadrenocorticism_moderate / exercise / cocaine

**核心函数**：
- `run_twin(scenario, config) -> TwinRunResult` — 跑生产 + 参考路径，按 vital 对比
- `run_all(config) -> dict[str, TwinRunResult]` — 跑所有场景

### 4.4 器官契约与耦合 (`src/organs/`)

#### `organs/contracts.py` — 器官契约

文件：[src/organs/contracts.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/organs/contracts.py)

**核心 Protocol**：

```python
@runtime_checkable
class ModuleContract(Protocol):
    INPUTS: tuple[str, ...] = ()
    OUTPUTS: tuple[str, ...] = ()
    READS_BLOOD: tuple[str, ...] = ()
    WRITES_BLOOD: tuple[str, ...] = ()
```

**辅助函数**：
- `has_contract(cls) -> bool` — 是否声明了任何契约
- `collect_contract(cls) -> dict` — 返回 I/O surface 字典

**设计原则**：契约是纯声明性的，不改变运行时行为。Phase 5+ 用于自动派生 CONNECTIONS 表、拓扑验证、模块文档生成、测试桩。

#### `organs/coupling.py` — 器官耦合

文件：[src/organs/coupling.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/organs/coupling.py)

**核心数据结构**：

```python
@dataclass(frozen=True)
class PhysiologicalSignal:
    name: str
    value: float
    unit: str
    source_module: ORGANS
    timestamp_s: float = 0.0
```

**`OrganContext` 类**：每器官信号总线
- `__slots__ = ("_module_name", "_signals")`
- `publish(signal)` / `get_signal(name)` / `get_value(name, default)` / `all_signals()`
- 只保留最新值

**`CouplingEngine` 类**：解析 `data/coupling_rules.json` → `FactorCommands`
- 构造函数加载并 jsonschema 校验规则文件
- `resolve(organ_contexts, dt) -> list[_CouplingFactorCommand]`：
  1. 构建扁平信号图（`"module.signal" → value`）
  2. 按 priority 升序评估每条启用规则
  3. Python 表达式 `fn` 求值
  4. 若 `time_constant > 0`，应用一阶滞后
  5. 检测振荡（信号变化 >50% 警告）

### 4.5 疾病系统 (`src/diseases/`)

#### `diseases/__init__.py` — 疾病模块基类

- `DiseaseModule.__init__(name)` — `name`, `active=False`, `activated_at_s=0.0`
- `activate(current_time_s)` / `deactivate()`
- `elapsed_since_activation_s` property
- 抽象方法 `compute(dt, engine_state) -> list[FactorCommand]`
- 辅助 `_cmd(target, op, value)` 和 `_clamp(value, lo, hi)`
- 全局函数：`register_disease(name, cls, **extra)` / `list_diseases()` / `create_disease(name, **kwargs)`

**多病叠加 chained-rebase 语义（Q2 spec 2026-06-14）**：
- `multiply` 链 = 复合效应（DCM 0.7 × 肺炎 0.8 = 0.56）
- `add` 链 = 累加
- `set` 链 = 后写者赢
- 排序 = `attach_disease` 调用顺序

#### `diseases/config_driven.py` — 配置驱动疾病引擎

文件：[src/diseases/config_driven.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/diseases/config_driven.py)

**设计理念**：从 `data/ode_diseases.json` 读取疾病定义，自动执行 ODE 求解 + FactorCommand 输出。新增疾病只需 JSON 配置，无需写 Python 类。

**支持的 ODE 类型**：

| 类型 | 方程 | 用途 |
|------|------|------|
| `logistic` | `dS/dt = rate * S * (1 - S/K) + seed_boost` | 微生物增长、炎症扩散 |
| `algebraic` | `S = fn(其他状态变量)` | 纯代数映射 |
| `first_order_lag` | `dS/dt = (target - S) / tau` | 一阶滞后 |
| `custom` | `dS/dt = derivative_fn(...)` | 自定义导数 |

**关键函数与类**：

- `register_ode_type(name, solver_fn)` — 注册自定义 ODE 求解器
- `_compile_expr(fn_str)` — 预编译表达式为 code 对象（加速）
- `_eval_fn(code, namespace) -> float` — 求值（P0 修复：失败抛 ValueError 而非静默 0.0）
- `_load_config() -> dict` — 加载 `data/ode_diseases.json` + 校验

**`ConfigDrivenDiseaseModule` 类**：

```python
class ConfigDrivenDiseaseModule(DiseaseModule):
    def __init__(self, name: str, config: dict, severity: str = "moderate")
    def compute(self, dt: float, engine_state: dict) -> list[FactorCommand]
    def compute_derivatives(self, engine_state: dict) -> dict[str, float]  # 供 solve_ivp Radau
    def summary(self) -> dict
```

- 支持严重程度预设（`severity_presets`）
- 状态变量、参数、表达式均来自 JSON
- `compute_derivatives` 将 `algebraic` 用极小 tau=0.001s 一阶 lag 近似，融入 ODE 框架
- 通过 `__getattr__` / `__setattr__` 允许属性访问状态变量

模块末尾调用 `_register_all()`，将所有 JSON 中定义的疾病自动注册到全局 `_DISEASE_REGISTRY`。

### 4.6 各器官模块职责

所有器官模块共享以下特征：
- `__setattr__ = organ_setattr`（强制 FactorCommand-only writes）
- 构造函数使用 `_blood_escape(cls)` 上下文管理器注入 `self.blood`
- 声明 `INPUTS / OUTPUTS / READS_BLOOD / WRITES_BLOOD` 类属性（Phase 5 契约）
- 声明 `STATE_VARS: tuple[tuple[str, str], ...]`（ODE 状态变量：(ode_name, attr_name)）
- 提供 `compute(dt, *_inputs) -> dict` 和 `derivatives(dt, *_inputs) -> (dydt_dict, outputs_dict)` 双接口

#### 心血管系统

| 文件 | 类 | 职责 |
|------|----|----|
| [src/heart.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/heart.py) | `HeartModule` | 心血管循环系统：HR/SV/SVR/MAP/CVP 计算、压力感受器反馈、血容量动态、心肌缺血积累。`STATE_VARS`: HR, SV, SVR, blood_volume, sympathetic, parasympathetic, ISCHEMIA |
| [src/heart_v2.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/heart_v2.py) | （无类，ASCII 动画） | 心脏动画可视化（life-simulator 风格 ASCII 艺术），含相位函数和心室容量曲线 |
| [src/cardiac_electrophysiology.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/cardiac_electrophysiology.py) | `CardiacElectrophysiology` | Hodgkin-Huxley 1952 电生理计算器：心率、[K⁺] → 动作电位仿真、ECG 波形、K⁺ 毒性因子 |
| [src/noble_purkinje.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/noble_purkinje.py) | `NoblePurkinjeFiber(CardiacElectrophysiology)` | Noble 1962 浦肯野纤维模型：增加慢 Ca²⁺ 电流（平台期）、时间依赖 K⁺、起搏电流 If、传导速度/PR 间期 |

#### 呼吸系统

| 文件 | 类 | 职责 |
|------|----|----|
| [src/lung.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/lung.py) | `LungModule` | 肺气体交换：肺泡气方程、A-a gradient、O₂/CO₂ 扩散、血气饱和度曲线。`STATE_VARS`: RR, TV, VQ |
| [src/respiratory_rhythm.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/respiratory_rhythm.py) | `VanDerPolRespiratoryRhythm` | Van der Pol 振荡器呼吸节律发生器：化学感受器（PCO2/PO2/pH）调制频率与幅度，产生自然呼吸性窦性心律不齐 |

#### 泌尿系统

| 文件 | 类 | 职责 |
|------|----|----|
| [src/kidney.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/kidney.py) | `KidneyModule` | 肾脏泌尿：GFR (Starling 模型)、肾小管重吸收、尿量、电解质平衡、RAAS（肾素/血管紧张素II/醛固酮）、ADH。`STATE_VARS`: GFR, RBF(renin_activity 别名), urine_output, ADH |

#### 肝脏

| 文件 | 类 | 职责 |
|------|----|----|
| [src/liver.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/liver.py) | `LiverModule` | 肝脏代谢：糖代谢（糖原储存/糖异生）、氨解毒（尿素循环）、白蛋白合成、胆红素结合、CYP450 药物代谢、Cori cycle 乳酸摄取、凝血因子合成。`STATE_VARS`: glycogen_fraction, bilirubin_accumulation |

#### 血液与凝血

| 文件 | 类 | 职责 |
|------|----|----|
| [src/blood.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/blood.py) | `BloodCompartment` | 血液隔室：所有器官共享的物质浓度载体。动脉/静脉血气、代谢物（葡萄糖/乳酸/BUN/肌酐）、电解质、肝功能标志物、凝血因子、药物浓度等约 30+ 字段 |
| [src/coagulation.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/coagulation.py) | `CoagulationModule` | 凝血系统：因子 II/V/VII/IX/X/XI/VIII 动力学、PT/aPTT/纤维蛋白原临床指标、DIC 状态。`STATE_VARS`: factor_VII, factor_V, factor_II, factor_IX, factor_X, factor_XI, fibrinogen, coagulation_state |

#### 体液

| 文件 | 类 | 职责 |
|------|----|----|
| [src/fluid.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/fluid.py) | `FluidCompartment` + `HendersonHasselbalch` | 三室体液模型：Vascular(8%) / ISF(15%) / ICF(40%)。Starling 力驱动血管↔组织间液交换、渗透压梯度驱动 ISF↔ICF。`HendersonHasselbalch`: pH = pKa + log10([HCO₃⁻] / (0.03 × PCO₂)) |

#### 胃肠道

| 文件 | 类 | 职责 |
|------|----|----|
| [src/gut.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/gut.py) | `GutModule` | 肠道吸收：蠕动、屏障完整性、菌群活性、门静脉血流（≈15% CO）、葡萄糖/氨基酸/脂肪吸收、短链脂肪酸。`STATE_VARS`: motility, barrier, microbiome |

#### 内分泌

| 文件 | 类 | 职责 |
|------|----|----|
| [src/endocrine.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/endocrine.py) | `EndocrineModule` | 5 个内分泌轴：甲状腺（T3/T4 → 代谢率）、胰腺（胰岛素/胰高血糖素 → 血糖）、肾上腺（HPA → 皮质醇/应激）、甲状旁腺（PTH → 钙磷）、生长轴（GH/IGF-1 → 白蛋白）。`STATE_VARS`: T3, insulin, glucagon, cortisol, PTH, IGF1, HPA_axis |

#### 免疫与淋巴

| 文件 | 类 | 职责 |
|------|----|----|
| [src/immune.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/immune.py) | `ImmuneModule` | 固有免疫：细胞因子动力学、发热、毛细血管漏、血管扩张（感染性休克）、WBC/CRP 急性期反应、高凝状态。`STATE_VARS`: cytokine, acute_phase, wbc, coagulation_state |
| [src/lymphatic.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/lymphatic.py) | `LymphaticModule` | 淋巴/脾脏：间质液回流、脾脏储血动员（失血/休克时释放）、免疫细胞运输、脂质吸收转运。`STATE_VARS`: splenic_reserve_mL, interstitial_fluid_mL |

#### 神经系统

| 文件 | 类 | 职责 |
|------|----|----|
| [src/neuro.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/neuro.py) | `NeuroModule` | 神经系统：化学感受器（PO2/PCO2/pH 驱动）、疼痛通路、癫痫活动、CNS 意识、自主神经张力（交感/副交感）。`STATE_VARS`: sympathetic_tone, parasympathetic_tone, consciousness, seizure, pain |

### 4.7 辅助机制

#### `src/engine_advancer.py` — 应用层推进器接口

文件：[src/engine_advancer.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/engine_advancer.py)

```python
class EngineAdvancerProtocol(Protocol):
    def advance_minutes(self, engine: Any, minutes: float) -> None: ...

@dataclass(frozen=True)
class PhysicalMinuteAdvancer:
    """默认应用层映射：场景分钟 → 物理分钟"""
    def advance_minutes(self, engine, minutes):
        if hasattr(engine, "advance_seconds"):
            engine.advance_seconds(minutes * 60.0)
        else:
            engine.simulate(float(minutes))
```

**职责**：app 层适配器接口，将场景级时长推进委托给引擎。`GameRuntime` 缝合点之一，使应用层测试可注入 fake advancer。

#### `src/presentation_state.py` — 就诊起始状态构建器

文件：[src/presentation_state.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/presentation_state.py)

```python
@dataclass(frozen=True)
class PresentationRequest:
    disease_name: str
    disease: object
    weight_kg: float = 20.0
    species: str = "canine"
    age_days: float | None = None
    encounter_stage: str = "acute_progressed"
    history_duration_min: float | None = None
    extra_diseases: tuple = ()           # 多病支持（合并症）
    extra_disease_names: tuple = ()
```

**核心函数**：
- `build_presented_engine(*, request, engine_factory=None) -> VirtualCreature` — 实例化引擎 → attach_disease 主疾病 + extra_diseases → simulate(history_minutes)；多病按 attach 顺序 chained-rebase 合并
- `_resolve_history_duration_min(request) -> float` — explicit override 优先，否则按 stage 默认
- `_default_history_duration_min(encounter_stage) -> float` — stage 默认值（acute_early=5, acute_progressed=15, acute_critical=30, subacute=180, chronic_compensated=720, chronic_decompensated=1440 分钟）

**职责**：集中会诊开始的预演逻辑（pre-encounter replay），避免散乱的 `attach_disease() + simulate(...)` 调用。

#### `src/organ_health.py` — 器官健康追踪

文件：[src/organ_health.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/organ_health.py)

**类**：`OrganHealthTracker`

**职责**：追踪心脏/肺/肾脏/肝脏在危重期间的不可逆损伤。损伤累积后永久改变器官基线。

**关键参数**：
- 衰竭阈值（秒）：HEART=180, LUNG=180, KIDNEY=240, LIVER=240
- 衰竭速率（health/s）：0.002~0.0025
- 完全衰竭阈值：HEART=0.3, LUNG=0.2, KIDNEY=0.15, LIVER=0.15

**核心方法**：
- `track(dt, heart_state, lung_state, kidney_state, liver_state, heart_state_pre=None, lung_state_pre=None)` — 使用 pre-degradation 值避免 organ_factor × MAP 反馈振荡
- `heart_factor / lung_factor / kidney_factor / liver_factor` properties
- `any_failure` property
- `organ_state(health, failure_at) -> str` — 离散状态标签：stable / warning / critical / failure
- `_sigmoid_acceleration(ratio)` — S 型加速曲线（刚超阈值退化慢，超标 50% 后急剧恶化）

**Stress 触发**：心脏 MAP<65 或 HR>200；肺 PaO2<65；肾 MAP<65；肝 MAP<65 或代谢活性<0.3

#### `src/organ_guard.py` — 器官写保护

文件：[src/organ_guard.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/organ_guard.py)

**职责**：强制器官模块通过 FactorCommand 写入而非直接 `self.blood.X = ...`

**核心机制**：
- `_GUARD_STACK: dict[type, int]` — 每模块类的守卫栈深度
- `_blood_escape(cls)` 上下文管理器 — 临时禁用守卫（仅 `__init__` 时注入 blood 引用）
- `_is_guard_active(cls) -> bool` — 栈深度为 0 时守卫激活
- `organ_setattr(self, name, value)` — 替换器官模块的 `__setattr__`，拦截 `blood.*` 赋值并抛出 `AttributeError`

#### `src/lifecycle*.py` — 生命周期引擎

文件：
- [src/lifecycle.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/lifecycle.py)
- [src/lifecycle_curves.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/lifecycle_curves.py)
- [src/lifecycle_profiles.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/lifecycle_profiles.py)

**双轨架构**：`LifecycleEngine` 同时支持
- **旧轨（BYPASS/默认）**：使用 `growth_factor` / `decline_multiplier` 旧 API（向后兼容，零开销）
- **新轨（GROWTH/SENESCENCE/FULL）**：使用 `LifecycleSpeciesProfile` 可配置发育/衰退曲线，支持幼年/老年仿真、品种大小差异

**`lifecycle_curves.py`** — 数学函数：

```python
class CurveType(Enum):
    SIGMOID = "sigmoid"
    LINEAR_SATURATE = "linear_saturate"
    GOMPERTZ = "gompertz"
    CONSTANT = "constant"
```

- `sigmoid(age_days, k, midpoint_days, sign=1.0)` — 标准 sigmoid 发育曲线
- `linear_saturate(age_days, max_days)` — 线性饱和
- `sigmoid_three_phase(age_days, k_rise, k_fall, peak_days, peak_value=1.0)` — 三相曲线（CYP450 Type 1）
- `maturation_curve(...)` / `decline_curve(...)` — 工厂函数

**`lifecycle_profiles.py`** — 物种配置：

```python
class LifecycleMode(Enum):
    BYPASS = "bypass"          # 禁用
    GROWTH = "growth"          # 仅发育
    SENESCENCE = "senescence"  # 仅衰退
    FULL = "full"              # 完整生命周期

class LifePhase(Enum):
    NEONATAL / JUVENILE / ADULT / SENIOR / GERIATRIC / DEAD
```

- `@dataclass(frozen) MaturationConfig` — 发育曲线配置
- `@dataclass(frozen) DeclineConfig` — 衰退曲线配置
- `@dataclass(frozen) LifecycleOrganConfig` — 单器官的发育+衰退配置
- `@dataclass(frozen) LifecycleSpeciesProfile` — 物种 profile
- `LifecycleProfileLoader.get(species)` — profile 加载器

**`LifecycleEngine` 核心方法**：
- `capture_baselines(creature)` — 在引擎初始化后捕获器官基准值（仅一次）
- `apply_age_factors(creature)` — 应用发育×衰退因子（在 tox/pharma/coupling 之前）
- `apply_age_factors_post_tox(creature)` — 毒理学之后重新应用 contractility_factor
- `apply(creature)` — 新轨：从 profile 曲线应用因子到 `_NEW_TRACK_TARGETS`
- `is_dead()` / `death_check() -> str | None`
- `advance_time(delta_days)`
- `serialize() -> dict` / `deserialize(data) -> LifecycleEngine`

---

## 5. 临床解释层 (Clinical Interpretation)

位置：`src/clinical_signs_engine.py`、`src/report_engine.py`、`src/clinical_interpreter.py`、`src/clinical_snapshot.py`、`src/clinical_stage.py`、`src/clinical_state.py`、`src/debug_params.py`、`src/interpretation_refresher.py`、`src/exam_registry.py`、`src/vitals_config.py`、`src/pharmacology.py`、`src/toxicology.py`。

**职责**：从内核状态派生可观察体征、生成结构化与叙述性报告、提供教学/调试视图。下游于内核，不得修改内核方程或求解器语义。

### 5.1 `clinical_signs_engine.py` — 可观察体征推导

文件：[src/clinical_signs_engine.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/clinical_signs_engine.py)

**核心类：`ClinicalSignsEngine`**（`__init__(self, creature, definitions, species="dog")`）

**职责**：从生理引擎状态推导"玩家/医生可观察到的临床体征"。每个仿真步（dt=0.1s）评估一次症状规则。

**关键接口**：
- `compute(current_time_s: float) -> dict[str, SignInstance]` — 主入口，评估所有症状规则，返回当前活跃体征
- `get_active_signs() -> list[SignInstance]` — 供游戏层使用的活跃体征列表
- `get_sign_tags() -> list[str]` — 返回活跃体征的 clue_id 列表（供 `report_engine` 注入 tag）

**规则类型**：
- `threshold` — 单参数阈值比较
- `multi_parameter` — 多参数布尔表达式（含 `compound_rule` 复合条件）
- `sustained` — 必须持续一段时间的阈值（如晕厥）

**数据类型**：`@dataclass SignInstance`（字段：`sign_id, display_name, severity, onset_time_s, active, clue_id, organ_system, localizing_value`）

**实现亮点**：内部自带布尔表达式 AST 编译器（`_compile_expr`、`_ASTComparison/_ASTAnd/_ASTOr/_ASTBoolLiteral`），将规则字符串预编译为 AST 并缓存（`_ast_cache`）。参数解析顺序：state → blood.* → heart.* → lung.* → kidney.* → disease.*。Glu 自动做 mmol/L → mg/dL 单位转换。体征有 onset/offset 延迟机制防抖动。

### 5.2 `report_engine.py` — 通用检查报告生成器

文件：[src/report_engine.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/report_engine.py)

**核心函数**：`generate_report(test_type, creature, state=None, sign_tags=None) -> dict`

**职责**：从 `data/exam_templates.json` 加载模板 + `data/vitals_ranges.json` 配置，统一生成结构化检查报告，替代早期 21 个独立 `_gen_*` 函数。

**报告分类**：
- **定量检查**（`_generate_quantitative_report`）：vitals + extra_params → 数值条目 + flag + tags
- **叙述性检查**（`_generate_narrative_report`）：findings_rules + tag_rules → 描述文本 + 线索
- **混合检查**（`_generate_mixed_report`）：如 blood_gas（定量参数 + 酸碱类型判断）

**关键数据结构**：
- `@dataclass(frozen) ExamReportInput` — 归一化输入
- `@dataclass(frozen) DiseaseMarkerView` — disease 标记的显式只读视图，带 `__getattr__` 代理
- `@dataclass(frozen) PendingReport`（在 action_system 中）

**关键辅助函数**：
- `get_state(creature)` → 调 `extract_clinical_state`（适配器）
- `flag(value, param)` / `result_entry(param, value, flag_val)` — 标准化结果条目
- `_build_disease_marker_view(creature)` — 注入 `clinical_stage` 计算字段
- `_eval_formula(formula, ctx, fallback)` — **安全** eval（仅注入 `__builtins__` 白名单：float/int/str/round/abs/min/max），支持 thresholds / state / disease 变量
- `_apply_findings_rules` / `_apply_tag_rules` — JSON 规则引擎

### 5.3 `clinical_interpreter.py` — 临床解释器（首选公共接口）

文件：[src/clinical_interpreter.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/clinical_interpreter.py)

**核心类：`DefaultClinicalInterpreter`**（`__init__(self, signs_engine_resolver=None)`）

**职责**：作为临床解释层的**首选公共接口**（per `docs/clinical-interpretation-layer.md`），聚合 snapshot/signs/report/phase/summary 五大能力。

**关键接口**：
- `snapshot(engine) -> ClinicalSnapshot` — 调 `build_clinical_snapshot`
- `active_signs(engine) -> Sequence` — 通过 resolver 取 signs engine
- `sign_tags(engine) -> list[str]`
- `report(test_type, engine) -> dict` — 调 `generate_report`
- `phase(snapshot) -> str` — 返回 `"stable" | "worsening" | "critical" | "moribund"`（基于 MAP/SpO2/HR/pH 阈值 + AA 梯度 + DO2 比值 + 乳酸 + 尿量 + 疾病损伤变量多维度评分，取最严重者）
- `summary(snapshot, elapsed_min) -> dict` — 返回 HR/MAP/SpO2/PO2/PCO2/pH/GFR/RR + game_time + is_night
- `_compute_do2(snapshot)` — DO2 = CO(L/min) × Hb(g/dL) × SaO2 × 1.34 / DO2_normal

**辅助类**：`ClinicalInterpreterProtocol`（Protocol 接口，定义上述 6 个方法的契约）。阈值从 `data/game_config.json` 的 `phase_thresholds` 加载。

### 5.4 `clinical_snapshot.py` — 临床快照数据模型

文件：[src/clinical_snapshot.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/clinical_snapshot.py)

**核心类：`@dataclass(frozen=True) ClinicalSnapshot`**

**职责**：从生理内核派生的**稳定只读**临床视图模型，供 interpreter 下游消费。`frozen=True` 保证不可变。

**字段涵盖**：`time_s, species, weight_kg, hr_bpm, map_mmhg, cvp_mmhg, rr_bpm, spo2_pct, pao2_mmhg, paco2_mmhg, ph, gfr_ml_min, urine_ml_min, bun_mg_dl, lactate_mmol_l, temperature_c, co_ml_min, blood_volume_ml, contractility_factor, diffusion_coefficient, sodium_meq_l, potassium_meq_l, glucose_mmol_l, hct_pct, hco3_meq_l, hb_g_dL, disease_name, disease_active, disease_state`。

### 5.5 `clinical_stage.py` — 临床分期

文件：[src/clinical_stage.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/clinical_stage.py)

**核心函数**：`compute_clinical_stage(disease_name, state_vars) -> str`

**职责**：从 ODE 状态变量计算临床分期标签，独立模块，不依赖 `ConfigDrivenDiseaseModule`。

**返回**：`"mild" | "moderate" | "severe" | "unknown"`。Phase 1 仅硬编码 3 个疾病（pneumonia → alveolar_exudate、dilated_cardiomyopathy → cardiac_fibrosis、acute_renal_failure → nephron_damage），其余返回 `"unknown"`。

**辅助函数**：`list_supported_diseases() -> list[str]`

### 5.6 `clinical_state.py` — 状态适配器

文件：[src/clinical_state.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/clinical_state.py)

**核心函数**：
- `extract_clinical_state(creature) -> dict` — 规范适配器，从 creature 提取历史 dict 风格状态（HR/MAP/CVP/CO/RR/SpO2/PaO2/PaCO2/pH/GFR/BUN/Na/K/Glu/Lactate/HCT/HCO3/Temp/BV/contractility/Urine/PT/aPTT/Fibrinogen/pain_level 等）。优先从 `creature.history` 取最新值，回退到器官属性。包含 HH ECG 解读字段（T波/QRS宽度/P波/PR间期/AV传导等）。
- `build_clinical_snapshot(creature) -> ClinicalSnapshot` — 构建稳定快照模型

**辅助函数**：`_hb_from_hct(hct_pct, species)` — 从 HCT 推算 Hb（犬/猫/马不同比率）

### 5.7 `debug_params.py` — 调试参数视图

文件：[src/debug_params.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/debug_params.py)

**核心函数**：`compute_debug_params(species, breed, age_days, weight_kg=None) -> dict`

**职责**：独立于游戏逻辑，用于查看不同年龄/体重/品种的生理参数、验证生命周期系统、调试器官耦合。不创建 GameState，不涉及 AP/疾病/时间管理。

**返回结构**：`{input, lifecycle, organs, summary}`，其中 organs 覆盖 heart/lung/kidney/blood/fluid/liver/gut/endocrine/neuro/immune/coagulation/lymphatic 共 12 个器官系统的全部参数。

**辅助函数**：`get_available_species()` / `get_breed_weight(species, breed)`

### 5.8 `interpretation_refresher.py` — 解释刷新器

文件：[src/interpretation_refresher.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/interpretation_refresher.py)

**核心类**：
- `InterpretationRefresherProtocol`（Protocol，`refresh(engine) -> None`）
- `NoOpInterpretationRefresher` — 默认空实现
- `ClinicalSignsRefresher`（`__init__(self, signs_engine_resolver=None)`）— 通过 resolver 取 signs engine 并调 `signs_engine.compute(engine.current_time_s)`

**职责**：物理时间推进后刷新解释侧状态，被 `GameRuntime.advance_and_refresh` 调用。

### 5.9 `exam_registry.py` — 检查注册表

文件：[src/exam_registry.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/exam_registry.py)

**核心类：`ExamRegistry`**（`__init__(self, raw: dict)`）

**职责**：从 `data/examinations.json` 加载检查类型元数据，替代 `action_system.py` 中的 `_EXAM_CONFIG` 硬编码字典，运行时只读。

**关键接口**：
- `get_meta(test_type) -> Optional[dict]` — 完整元数据
- `get_exam(test_type) -> tuple[int, int, int]` — 返回 `(time_cost_min, tier, latency_min)`，未知默认 `(5, 2, 0)`
- `exam_types` 属性 — 所有检查类型 ID 列表

**工厂函数**：`get_exam_registry(reload=False) -> ExamRegistry`（全局单例，加载前经 `validate_examinations` 校验）

### 5.10 `pharmacology.py` — 药理学（PK/PD）

文件：[src/pharmacology.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/pharmacology.py)

**核心基类：`Drug`**（`__init__(self, name, half_life_s, emax=1.0, ec50=1.0, hill=1.0)`）

**职责**：一室模型 PK（`C(t)=Dose·e^(-k·t)`）+ Hill 方程 PD（`E=Emax·C^n/(EC50^n+C^n)`）。

**关键接口**：
- `administer(dose_mg_kg)` — IV 推注，瞬时增加浓度
- `compute(dt)` — 一阶消除衰减
- `pd_effect()` — Hill 方程返回效应值 [0, Emax]
- `factor_commands(pd_effect) -> list[FactorCommand]` — **子类重写**，将 PD 效应转换为 `FactorCommand` 指令列表

**已注册药物子类**：

| 药物 | 机制 | t½ |
|------|------|----|
| `Pimobendan` | PDE-III 抑制剂 → ↑contractility | 2h |
| `Furosemide` | 袢利尿剂 → ↑urine_output | 1.5h |
| `Epinephrine` | α/β 激动剂 → ↑SVR + ↑HR | 2min |
| `FluidBolus` | 晶体液冲击 → ↑blood_volume | 无衰减 |
| `AmoxicillinClavulanate` | 抗生素 → immune.antibiotic_effect | 1.5h |

**核心类：`PharmacologyState`**（`__init__(self, weight_kg)`）

**职责**：持有一个 creature 的所有活跃药物。每仿真步：①PK 衰减 ②肝 CYP450 首过代谢（`creature.liver.compute_drug_clearance`）③PD 效应转 FactorCommand。

**关键接口**：
- `administer_drug(name, dose_mg_kg=0.0, volume_ml=0.0)` — 工厂创建并给药
- `compute(dt, creature) -> list[FactorCommand]` — 推进所有药物，返回指令列表供引擎 `apply_factor()` 统一应用

**工厂函数**：`create_drug(name, **kwargs)` / `register_drug(name, cls)` / `list_drugs()`

### 5.11 `toxicology.py` — 毒理学

文件：[src/toxicology.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/toxicology.py)

**核心类：`ToxicologyModule`**（`__init__(self, weight_kg)`）

**职责**：基于 Liu et al. (1993) JACC 21:260-268 仿真可卡因两路独立效应。

**关键接口**：
- `administer_cocaine(dose_mg_kg=COCAINE_DOSE_MG_KG)` — 注射，剂量依赖
- `compute(dt) -> dict` — 推进毒理状态，返回 `{contractility_factor, svr_factor, cocaine_active, ...}`
- `summary() -> dict`

**两路效应**：
- ①心脏直接抑制（τ=5min 快衰减，最大抑制 60%）
- ②交感血管收缩（τ=30min 慢衰减，最大 3.5× SVR）

### 5.12 `vitals_config.py` — 生命体征配置

文件：[src/vitals_config.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/vitals_config.py)

**`VitalsConfig` 类**：从 `data/vitals_ranges.json` 加载参数正常范围/危急值/clue_flags 映射。

**接口**：`get_normal / get_unit / get_critical / get_clue_id / classify`。单例工厂 `get_vitals_config()`。

### 5.13 终端监控视图

#### `textual_monitor.py` — Textual 终端 UI

文件：[src/textual_monitor.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/textual_monitor.py)

**核心类：`PatientMonitor(App)`**（Textual App），含 BINDINGS（q=quit, space=pause）。

**Widget 组件**：
- `HeartWidget(Static)` — 参数驱动的 ASCII 心脏跳动动画（4 帧 cycle）
- `VitalWidget(Static)` — 单项体征带颜色编码（绿/黄/红）
- `OrgansWidget(Static)` — 器官状态网格（●◐○✗）
- `SignsWidget(Static)` — 活跃体征列表
- `TrendWidget(Static)` — Sparkline 趋势图

**入口**：`main()` — CLI `--disease / --severity / --steps`，调 `app.run()`

#### `ascii_dashboard.py` — 终端可视化

文件：[src/ascii_dashboard.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/ascii_dashboard.py)

**核心函数**：
- `build_dashboard(creature, width=78, use_color=True) -> list[str]` — 组装完整仪表盘
- `render_gauge(spec, value, width, use_color)` — 渐变条形仪表
- `render_sparkline(values, width, colormap, use_color)` — 火花线
- `render_heatmap_row(values, width, colormap)` — 热力图行
- `snapshot(disease_name, severity, steps, use_color)` — 单次快照
- `run_interactive(disease_name, severity)` — curses 交互模式

**特色**：TrueColor 24-bit ANSI 渲染（检测 `COLORTERM`/`WT_SESSION`）、感知均匀 colormap（thermal/ocean/vital/sepsis）、`@dataclass GaugeSpec` 配置。

---

## 6. 应用 / 游戏层 (Application / Game)

位置：`game/`、`gui_app.py`、`vet-game-frontend/vite-project/`、case/exam/treatment JSON 文件。

**职责**：病例选择与编排、诊断玩法、场景节奏、玩家可见时钟、会话持久化与回放、前端 UX。

### 6.1 `game/runtime.py` — GameRuntime（运行时组合根）

文件：[game/runtime.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/runtime.py)

**核心类：`@dataclass(frozen=True) GameRuntime`**

**字段**：
- `advancer: EngineAdvancerProtocol`
- `interpreter: ClinicalInterpreterProtocol = DefaultClinicalInterpreter()`
- `refresher: InterpretationRefresherProtocol = ClinicalSignsRefresher()`

**关键方法**：`advance_and_refresh(engine, minutes) -> None` — 先推进引擎物理时间，再刷新解释侧状态。

> 注意：此处的 `GameRuntime` 是**轻量组合根**，并不承载 `process_action`。`default_runtime()` 返回单例 `_DEFAULT_RUNTIME`。

### 6.2 `game/runtime_composition.py` — 运行时组合

文件：[game/runtime_composition.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/runtime_composition.py)

**核心函数**：`build_external_interpretation_bundle(engine, *, species=None, symptom_definitions=None, advancer=None) -> ExternalInterpretationBundle`

**职责**：为单个引擎构建外层解释栈。创建 `ClinicalSignsEngine`，用闭包 `_resolve_signs_engine` 绑定到 `DefaultClinicalInterpreter` 和 `ClinicalSignsRefresher`，首次 `compute` 后返回 `ExternalInterpretationBundle(signs_engine, runtime)`。

**数据类**：`@dataclass(frozen) ExternalInterpretationBundle`（字段：`signs_engine, runtime`）

### 6.3 `game/action_system.py` — 动作系统（核心游戏循环）

文件：[game/action_system.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/action_system.py)

**核心类：`@dataclass GameState`** — 游戏状态数据类（v2：时间预算版）

**关键字段**：`engine, disease_name, disease_names (list), phase ("playing"|"won"|"lost"), death_timer, reports, treatment_applied, time_elapsed_min, time_budget_min, species, pending_reports (list[PendingReport]), _original_hr_rest`。`time_remaining_min` 属性计算剩余时间。

**核心函数**：`process_action(state, action_type, params=None, runtime=None) -> dict` — **中央游戏循环**

**处理四种 action_type**：

| action_type | 行为 |
|-------------|------|
| `examine` | 调 `interpreter.report()` 生成报告，按 `latency_min` 入队 `PendingReport` 或直接入 `state.reports` |
| `treat` | 调 `apply_treatment`，正确则 `phase="won"` |
| `administer_drug` | 挂载 `PharmacologyState` 并给药 |
| `wait` | 消耗 10 分钟 |

**流程**：推进 `time_elapsed_min` → `runtime.advance_and_refresh(engine, time_cost)` → `_process_pending_reports` 处理延迟报告到期 → `_apply_night_modifiers` 夜间 HR 修正 → `interpreter.phase(snapshot)` 阶段判定 → `check_death` 死亡检测 → 时间耗尽检测。

**返回结构**：`{success, time_cost_min, time_elapsed_min, time_remaining_min, action_started_at_s, state_time_s, result, new_reports, pending_count, phase, medical_phase, engine_summary}`。

**其他函数**：
- `check_death(state, medical_phase) -> GameState` — 濒死倒计时（`MORIBUND_TURNS_REMAINING`）+ 死亡判定
- `determine_phase(engine) -> str` — **Legacy 兼容**，新代码应用 `runtime.interpreter.phase`
- `_engine_summary(engine, elapsed_min) -> dict` — **Legacy 兼容**
- `_process_pending_reports(state, elapsed_min) -> list[dict]` — 延迟报告到期处理
- `_annotate_report_timing(report, *, observed_at_s, report_basis, available_after_min)` — 报告时序注解
- `_apply_night_modifiers(state)` — 夜间心率修正（22:00-06:00 HR×0.85）
- `compute_DO2(engine)` — 氧输送指数计算

**时间预算常量**：`TIME_BUDGET_EASY=120 / TIME_BUDGET_NORMAL=90 / TIME_BUDGET_HARD=60` 分钟。

### 6.4 `game/case_generator.py` — 病例生成器

文件：[game/case_generator.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/case_generator.py)

**核心函数**：`generate_case(difficulty="normal", seed=None) -> GameState`

**职责**：随机生成完整开局（动物 + 疾病 + 引擎 + 疾病发展期 → GameState）。

**流程**：
1. `_load_animals()`（优先 `data/animals.json`，回退 8 种内建犬类）
2. `_pick_disease(difficulty, rng)`（按 `_SEVERITY_WEIGHTS` 加权选严重度）
3. `_init_engine(weight_kg, disease, rng)`（调 `build_presented_engine` + `PresentationRequest`，疾病发展 5-30 分钟）
4. 构造 `GameState`

### 6.5 `game/diagnosis_engine.py` — 诊断引擎

文件：[game/diagnosis_engine.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/diagnosis_engine.py)

**核心函数**：

- `extract_clues(reports) -> list[str]` — 从多份报告提取去重线索 ID
- `match_diseases(reports, known_clues=None) -> list[dict]` — **加权匹配**：每个线索按特异性加权（`_CLUE_SPECIFICITY = 1/freq`，出现在越少疾病中权重越高），返回按 confidence 降序的 `[{disease, confidence, matched_clues, missed_clues, matched_count, total_clues}]`
- `get_suggested_tests(matches) -> list[str]` — 基于 top 2 疾病的 missed_clues 查 `_CATALOG_SUGGESTED_TESTS` 推荐下一步检查
- `get_disease_references(disease_name) -> dict | None` / `get_disease_references_with_clues(disease_name, matched_clues) -> dict` — 文献引用
- `get_clue_description(clue_id)` / `register_disease_clues(disease_name, clues)`

**数据来源**：
- `data/diseases.json`（clues/clue_descriptions/treatment_protocols/messages）
- `data/clue_catalog.json`（suggested_tests）
- `data/disease_references.json`（guidelines/criteria）

### 6.6 `game/time_manager.py` — 时间管理

文件：[game/time_manager.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/time_manager.py)

**核心函数**：

- `game_time_to_hour(game_time_min) -> float` — 分钟转 24 小时制
- `is_night_time(game_time_min) -> bool` — 22:00-06:00 为夜间
- `get_night_hr_factor(game_time_min) -> float` — 夜间 0.85，白天 1.0
- `get_night_progression_factor(game_time_min) -> float` — **Legacy** 外层策略因子（**非内核生物时间乘数**，明确注释不可用于重标度疾病方程）
- `apply_night_hr_modifier(base_hr, game_time_min)`
- `get_time_of_day_label(game_time_min)` — morning/afternoon/evening/night
- `format_game_time(game_time_min) -> str` — "HH:MM" 格式

**常量**：`GAME_START_HOUR=8`、`NIGHT_START_HOUR=22`、`NIGHT_END_HOUR=6`、`NIGHT_HR_FACTOR=0.85`。

### 6.7 `game/treatment.py` — 治疗判定

文件：[game/treatment.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/treatment.py)

**核心函数**：`apply_treatment(game_state, disease_guess) -> dict` — 治疗判定（Q4 多病支持）

**逻辑**：
- `disease_guess` 支持 `str | list[str]`（Q4.1=C 自动归一化为 list）
- 主诊断必须在 guess list 中才算 win（Q4.2=B）
- 合并症 bonus（不影响 win 判定）
- 按 guess list 顺序依次 admin 单病 protocol（Q4.3=B 运行时合并）
- `supportive_care` 特殊处理：补液 200mL，不结束游戏

**返回**：`{success, correct, actual_disease, chosen_disease, phase, message, drugs_given, comorbidity_correct}`。

**辅助函数**：
- `is_correct_treatment(game_state, disease_guess) -> bool`（向后兼容单病）
- `_administer_protocol(engine, disease_name) -> list[str]`
- `_apply_supportive_care(game_state)`
- `_ensure_pharmacology(engine)`

**数据来源**：`data/diseases.json` 的 `treatment_protocols` + `messages.win/loss`。

### 6.8 `game/test_translator.py` — 测试翻译器（Legacy）

文件：[game/test_translator.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/game/test_translator.py)

**核心函数**：`translate(test_type, creature) -> dict`

**职责**：Legacy 兼容包装器，新代码应优先用 `GameRuntime.interpreter.report(...)`。直接委托 `default_runtime().interpreter.report(test_type, creature)`。

---

## 7. GUI 与入口点

### 7.1 `gui_app.py` — Flask 应用（主游戏 API）

文件：[gui_app.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/gui_app.py)

**Flask app**，默认 `http://127.0.0.1:5000`（可由 `VV_HOST`/`VV_PORT` 环境变量覆盖）。

**会话存储与会话锁机制**：
- `_game_sessions: dict[str, GameState]` — 内存会话存储
- `_session_runtimes: dict[str, object]` — 每 session 绑定的 GameRuntime
- `_session_locks: dict[str, threading.Lock]` — **每 session 一把 threading.Lock**
- `_action_seq: dict[str, int]` — 动作序号
- `_DEFAULT_SESSION_ID = "case_001"`
- 辅助：`_session_lock_or_404(session_id, message)` — 取锁或返回 404

遵循 AGENTS.md 规则：**所有读写 session-owned 状态的端点都用 session lock**；无锁的 session 视为无效（即使 `_game_sessions` 还有 state）。

**主要 API 端点**：

| 端点 | 方法 | 锁 | 说明 |
|------|------|----|------|
| `/api/cases` | GET | 否 | 返回所有病例 |
| `/api/examinations` | GET | 否 | 检查项目定义 |
| `/api/treatments` | GET | 否 | 治疗方案 |
| `/api/drugs` | GET | 否 | 可用药物元信息 |
| `/api/new-game` | POST | 否 | 开始新病例：解析 case → `build_presented_engine` → 创建 GameState + lock + `build_external_interpretation_bundle` → SQLite 持久化 |
| `/api/examine` | POST | **是** | 调 `process_action(state, "examine", ...)` |
| `/api/administer-drug` | POST | **是** | 调 `process_action(state, "administer_drug", ...)` |
| `/api/diagnose` | POST | **是** | 调 `process_action(state, "treat", {"disease_guess": diagnosis})`；diagnosis 支持 str 或 list（Q4 多病） |
| `/api/wait` | POST | **是** | 调 `process_action(state, "wait", {}, runtime=runtime)` |
| `/api/game-state` | GET | **是** | 刷新/轮询游戏状态（snapshot 端点也锁） |
| `/api/hint` | GET | **是** | 调 `match_diseases` 给诊断提示（top N 候选，阈值 0.30） |
| `/api/diagnosis` | GET | **是** | 结构化诊断匹配数据（matches + suggested_tests + references + target_diseases） |
| `/api/disease-references/<name>` | GET | 否 | 完整文献引用 |
| `/api/sessions/<id>/replay` | GET | 否 | 教学回放（SQLite action log） |
| `/api/debug/species` | GET | 否 | 调试器：物种/品种 |
| `/api/debug/params` | POST | 否 | 调试器：生理参数（调 `compute_debug_params`） |
| `/api/debug/diseases` | GET | 否 | 调试器：疾病列表 |
| `/api/debug/disease-params` | POST | 否 | 调试器：健康 vs 疾病对比 |

**辅助函数**：
- `_persist_action(state, session_id, action_type, params, result)` — SQLite 持久化（best-effort，失败不影响游戏）
- `_snapshot_json(vc)` — 序列化引擎快照
- `_clinical_snapshot/_clinical_phase/_clinical_summary(vc, runtime)` — 通过 runtime.interpreter 取解释输出
- `_runtime_for_session(session_id)` — 取 session 绑定的 runtime 或 default
- `_get_vitals(vc, elapsed_min, runtime) -> dict` — 提取生命体征
- `_get_active_signs(vc, runtime) -> list[dict]` — 提取活跃症状
- `_build_game_log(state) -> list[str]` — 诊疗日志
- `_calc_score(state) -> dict` — 评分（S/A/B/C/D 等级，时间惩罚 0.5/min，最大 60）
- `_get_time_budget(difficulty)`、`_parse_age_days(age_str)`、`_lifecycle_mode_for_age(age_days, species)`

**SQLite 持久化层**（位于 `src/db/`）：
- `conn.connect` / `schema.init_db`
- `sessions.create_session` / `sessions.update_session_outcome` / `sessions.update_engine_snapshot`
- `action_log.append_action` / `action_log.get_action_log`

### 7.2 入口点

| 文件 | 作用 |
|------|------|
| [main.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/main.py) | **主入口**：运行仿真 + matplotlib 图表生成。`run_all_scenarios()` 跑正常稳态/失血/失血+输液三场景，`plot_results()` 输出心血管/呼吸肾脏/系统耦合三张图。`interactive_demo()` 交互式菜单。`--auto` 自动模式 |
| [cli_daemon.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/cli_daemon.py) | **CLI 守护进程**：终端自治运行仿真 + 定时输出。`SCENARIOS` 字典定义 7 场景（normal/blood_loss_100/blood_loss_200/blood_loss_resuscitation/dehydration/cocaine/cocaine_high）。`run_daemon(scenario_key, duration_minutes, interval_seconds, ...)` 主循环，支持 SIGINT 优雅停止。带状态颜色编码 + ASCII 趋势图 |
| [vet_monitor.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet_monitor.py) | **vet-monitor 入口**（4 行）：注入 sys.path 后调 `src.ascii_dashboard.main()` |
| [cli_shim.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/cli_shim.py) | **vet-monitor CLI 垫片**：注入 project root + src 到 sys.path（因 simulation.py 用 `from blood import ...`），调 `src.cli.main` |
| [src/cli.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/cli.py) | **统一 vet-monitor CLI**（argparse 子命令）：`dashboard`（实时/快照仪表盘，可 `--live` 切 Textual）、`heart`（心脏动画）、`snapshot`（快照 `--format text|ansi`）、`list-diseases`（疾病与别名列表） |

---

## 8. 前端层 (Frontend)

技术栈：Vue 3（`<script setup lang="ts">`）+ Vite+ 工具链（`vp` CLI）+ TypeScript。入口 `main.ts` → `createApp(App).mount("#app")`。

### 8.1 `src/App.vue` — 主应用

文件：[vet-game-frontend/vite-project/src/App.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/App.vue)

**职责**：顶层布局 + 全局状态管理 + 动作调度。

**三栏布局**：左 `PatientCard` | 中 `CaseSelect`/游戏 Tab | 右 `VitalCard` 列 + 活跃体征。

**状态**：`phase ("select"|"game"|"done")`、`tab ("exam"|"report"|"diag")`、`sessionId`、`caseData`、`reports`、`vitals (reactive)`、`timeElapsedMin/Budget/Remaining`、`medicalPhase`、`deathTimer`、`activeSigns`、`gameLog`、`gameOverData`、`isNight`、`gameTime`。

**关键计算属性**：`phaseClass`/`phaseLabel`、`timePercent`/`timeBarClass`（ok/warn/danger）、`signsBySystem`（按 organ_system 分组）、`SYSTEM_LABELS`/`LOCALIZING_LABELS`（中文化映射）。

**关键动作函数**：`startGame`、`doExam`、`doWait`、`submitDiagnosis`、`doSupportiveCare`、`doAdministerDrug`、`loadHint`、`goBack`/`restart`、`openDebug`/`closeDebug`。`updateFrom(d)` 统一从 API 响应更新 reactive 状态。`watch(isNight)` 切换 body class `night-mode`。`onMounted` 并行加载 cases/examinations/treatments/drugs。

### 8.2 `src/api.ts` — API 客户端

文件：[vet-game-frontend/vite-project/src/api.ts](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/vet-game-frontend/vite-project/src/api.ts)

**`request<T>(method, path, body?)`** — 通用 fetch 封装，BASE 来自 `import.meta.env.VITE_API_BASE_URL || "/api"`，`trimTrailingSlash` 处理末尾斜杠。

**`api` 对象方法**：
- `getCases / getExaminations / getTreatments / newGame / examine / diagnose / wait / getGameState / getHint / getDiagnosis / getDiseaseReferences / getDrugs / administerDrug`
- GET 请求参数走 query string 并 `encodeURIComponent`（遵循 AGENTS.md "Frontend GET calls must pass parameters in the query string"）
- `administerDrug` 自动按 `volume_ml` vs `dose_mg_kg` 分支

**`debugApi` 对象**：`getSpecies / getParams / getDiseases / getDiseaseParams`（调试器专用）

### 8.3 `src/types.ts` — 类型定义

文件：[vet-game-frontend/vite-project/src/types.ts](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/types.ts)

导出接口覆盖全部业务实体：
- 游戏数据：`Animal`、`Case`、`Vitals`、`ResultEntry`、`Report`、`GameState`
- 诊断：`DiagnosisMatch`、`DiagnosisResponse`、`TreatmentResult`、`GameOverData`、`ActiveSign`
- 文献：`ReferenceGuideline`、`CriterionReference`、`DiseaseReference`
- 药物：`DrugEntry`、`AdministerDrugResponse`
- 调试器：`BreedInfo`、`SpeciesBreeds`、`SpeciesData`、`DebugParamEntry`、`DebugOrganParams`、`DebugParamsResponse`
- 通用：`ApiResponse<T>`

### 8.4 `src/components/` — 组件职责

| 组件 | 职责 |
|------|------|
| [CaseSelect.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/CaseSelect.vue) | 病例选择卡片网格，emit `select(caseId)` |
| [PatientCard.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/PatientCard.vue) | 患宠信息展示（头像/品种/年龄/体重/主诉/病史），纯展示组件 |
| [ExamGrid.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/ExamGrid.vue) | 检查项目网格，按 tier (1-5) 分组（基础/快速/核心/影像/金标准），带颜色编码与时间预算检查（`canAfford` 禁用超时项），emit `exam(testType)` |
| [ReportList.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/ReportList.vue) | 可折叠检查报告列表，支持定量表格（参数/结果/参考范围/标记）和叙述性文本两种渲染，`flagText` 中文化标记 |
| [VitalCard.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/VitalCard.vue) | 单项生命体征卡片，warn/danger 阈值颜色分类，夜间 HR 显示"夜间生理性心动过缓"提示 |
| [DiagnosisPanel.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/DiagnosisPanel.vue) | 诊断面板：①置信度面板（调 `api.getDiagnosis` 显示鉴别诊断 + 进度条 + 建议检查）②文献引用面板（可展开，调 `api.getDiseaseReferences` 懒加载完整依据：核心指南 + 诊断依据/阈值/来源/机制）③诊断下拉选择 + 确认/提示/支持治疗按钮。`refreshTrigger` watch 自动刷新 |
| [GameLog.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/GameLog.vue) | 诊疗日志时间线（纯展示） |
| [GameOverOverlay.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/GameOverOverlay.vue) | 结局覆盖层（胜/负图标 + reason + 正确诊断 + 评分 S/A/B/C/D + 再来一局），emit `restart` |
| [DebugParams.vue](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/vet-game-frontend/vite-project/src/components/DebugParams.vue) | 调试器全屏页（物种/品种/年龄/体重选择 + 健康参数计算 + 疾病对比模拟 + 生命周期阶段标签），emit `close` |
| `HelloWorld.vue` | Vite 脚手架遗留（未在 App.vue 引用） |

---

## 9. 数据文件与配置

位置：`data/`。声明式 JSON 配置，多数带 JSON Schema 校验（`data/schemas/`）。

| 文件 | 内容 |
|------|------|
| [data/cases.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/cases.json) | 临床病例（pneumonia/ARF/DCM/phosphorus poisoning/etc.），difficulty 1-3，species/weight |
| [data/examinations.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/examinations.json) | 21 种检查类型，含 tier (1-5)、AP cost、latency、category |
| [data/exam_templates.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/exam_templates.json) | 报告生成模板（vitals、extra_params、findings_rules、tag_rules）— 完全配置驱动 |
| [data/diseases.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/diseases.json) | 疾病名称、线索定义、clue→test 映射、治疗协议、胜负消息 |
| [data/ode_diseases.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/ode_diseases.json) | 所有疾病的声明式 ODE 定义（state_variables、severity_presets、outputs） |
| [data/vitals_ranges.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/vitals_ranges.json) | 生理参数正常范围、危急阈值、clue_flags 映射 |
| [data/game_config.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/game_config.json) | 游戏设计常量：AP 系统、压力、物种修正、组合奖励、phase 阈值 |
| [data/treatments.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/treatments.json) | 治疗选项 |
| [data/clue_catalog.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/clue_catalog.json) | 线索目录（suggested_tests） |
| [data/disease_references.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/disease_references.json) | 文献引用（guidelines/criteria） |
| [data/coupling_rules.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/coupling_rules.json) | 器官耦合规则（Euler 路径用，jsonschema 校验） |
| [data/disease_manifestations.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/disease_manifestations.json) | 疾病表现定义 |
| [data/symptom_definitions.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/symptom_definitions.json) | 症状规则定义（threshold/multi_parameter/sustained） |
| [data/symptom_thresholds.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/symptom_thresholds.json) | 症状阈值 |
| [data/breed_standards.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/breed_standards.json) | 品种标准 |
| [data/lifecycle_profiles.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/lifecycle_profiles.json) | 生命周期物种 profile |
| [data/lifecycle_references.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/lifecycle_references.json) | 生命周期文献引用 |
| [data/parameter_references.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/data/parameter_references.json) | 参数文献引用 |
| `data/schemas/*.schema.json` | JSON Schema 校验文件（diseases/exam_templates/examinations/ode_diseases/parameter_references） |

---

## 10. 依赖关系

### 10.1 Python 运行时依赖（`pyproject.toml`）

| 依赖 | 用途 |
|------|------|
| `numpy>=1.21.0` | ODE 状态向量与数值计算 |
| `scipy>=1.15.3` | `solve_ivp(method="Radau")` 隐式积分 |
| `flask>=2.3.0` | REST API 后端 |
| `matplotlib>=3.5.0` | `main.py` 图表生成 |
| `jsonschema>=4.26.0` | JSON 配置校验（coupling_rules/ode_diseases/...） |
| `textual>=8.2.7` | `src/textual_monitor.py` 终端 UI |
| `windows-curses>=2.4.2` | Windows curses 支持 |

**Python 版本要求**：`>=3.10`（使用 `dict[str, ...]`、`X | Y` 类型语法等）

**开发依赖**：
- `pytest>=7.0` + `pytest-timeout>=2.4.0`
- `ruff>=0.4.0`

**入口脚本**：`vet-monitor = "cli_shim:main"`（`pyproject.toml` 的 `[project.scripts]`）

### 10.2 前端依赖（`package.json`）

| 依赖 | 类型 | 用途 |
|------|------|------|
| `vue@^3.5.32` | dependencies | Vue 3 框架 |
| `@vitejs/plugin-vue@^6.0.6` | dev | Vite Vue 插件 |
| `@vue/tsconfig@^0.9.1` | dev | Vue TS 配置 |
| `typescript@~6.0.2` | dev | TypeScript |
| `vite` (= `@voidzero-dev/vite-plus-core@latest`) | dev | Vite+ 核心包 |
| `vite-plus@latest` | dev | 统一前端工具链 |
| `vue-tsc@^3.2.7` | dev | Vue 类型检查 |

**包管理器**：`npm@11.13.0`

### 10.3 内部依赖方向图

```
                     ┌──────────────────────────┐
                     │  vet-game-frontend (Vue)  │
                     └────────────┬─────────────┘
                                  │ HTTP /api/*
                                  ▼
                     ┌──────────────────────────┐
                     │      gui_app.py (Flask)   │
                     └────────────┬─────────────┘
                                  │
                ┌─────────────────┼──────────────────┐
                ▼                 ▼                  ▼
       ┌─────────────┐   ┌─────────────────┐  ┌──────────────┐
       │ game/       │   │ src/db/ (SQLite) │  │ data/*.json  │
       │ action_sys  │   │ sessions/log     │  │ 配置驱动     │
       │ runtime     │   └─────────────────┘  └──────────────┘
       │ diagnosis   │
       │ treatment   │
       │ case_gen     │
       └──────┬───────┘
              │
              ▼
   ┌──────────────────────────┐
   │  Clinical Interpretation │
   │  clinical_interpreter    │
   │  clinical_signs_engine   │
   │  report_engine           │
   │  clinical_snapshot       │
   │  exam_registry           │
   │  pharmacology/toxicology │
   └──────────────┬───────────┘
                  │
                  ▼
   ┌──────────────────────────┐
   │  Physiology Kernel       │
   │  simulation.py           │
   │  engine/ (solvers/...)   │
   │  organs/                │
   │  diseases/              │
   │  heart/lung/kidney/...   │
   │  parameters/common_types │
   └──────────────────────────┘
```

### 10.4 数据持久化

- **SQLite**（`src/db/`）：会话存储 + 动作日志（教学回放）
- **内存**（`gui_app.py`）：`_game_sessions` / `_session_runtimes` / `_session_locks`（Flask 重启后丢失）
- **静态构建产物**：前端构建到 `static/`，由 Flask `send_from_directory` 直接服务

---

## 11. 项目运行方式

### 11.1 环境准备

**Python 依赖隔离**：项目使用 `uv`（per `pyproject.toml` + `uv.lock`），所有 Python 命令应通过 `uv run` 执行以保持 `.venv/` 隔离。

```bash
# 首次：安装依赖（创建 .venv/）
uv sync
```

### 11.2 启动主应用（Flask + 前端）

```bash
# 方式 1：直接 Python（依赖已安装）
python gui_app.py
```

```bash
# 方式 2：通过 uv run（推荐）
uv run python gui_app.py
```

然后打开 `http://127.0.0.1:5000`。

**环境变量**：
- `VV_HOST` — 覆盖默认 host
- `VV_PORT` — 覆盖默认端口 5000

**Windows 一键启动**：双击 `打开 virtual-vet.bat`

### 11.3 前端开发

```bash
cd vet-game-frontend/vite-project

# 安装前端依赖
vp install        # 或 npm install

# 开发模式（热重载，http://127.0.0.1:5173）
vp dev

# 构建（输出到 ../../static/，Flask 服务该目录）
vp build

# 格式化 + lint + 类型检查
vp check
```

> **关键约定**：每次前端代码改动后必须运行 `vp build` 更新 `static/`。Flask 直接服务构建产物，不代理到 Vite dev server。

### 11.4 CLI 工具

```bash
# vet-monitor 统一 CLI（dashboard/heart/snapshot/list-diseases）
uv run vet-monitor dashboard --disease pneumonia --severity moderate --live
uv run vet-monitor snapshot --disease arf --severity severe --format ansi
uv run vet-monitor list-diseases

# CLI 守护进程（自治运行仿真）
uv run python cli_daemon.py --scenario blood_loss_100 --duration 30 --interval 1

# 主入口（matplotlib 图表生成）
uv run python main.py --auto
```

### 11.5 快捷启动脚本

位于 `tools/dev/`：

| 脚本 | 作用 |
|------|------|
| `start_backend.ps1` | 启动 Flask 后端 |
| `start_frontend.ps1` | 启动 Vite 前端 dev server |
| `start_static_app.ps1` | 启动构建后的静态应用 |
| `show_runtime.ps1` | 显示运行时状态 |

---

## 12. 测试体系

### 12.1 测试通道（`--channel`）

项目按意图分离测试通道，避免所有应用测试都变成重仿真测试。

| 通道 | 用途 | 命令 | 规模 |
|------|------|------|------|
| `fast` | 日常开发（公式/不变量/轻量契约） | `python -m pytest --channel fast -q` | ~441 测试，8-15s |
| `core` | 核心 app/runtime/API 回归 | `python -m pytest --channel core -q` | ~750 测试，25-45s |
| `heavy` | 重集成/验证（求解器/疾病耐久/长程数值） | `python -m pytest --channel heavy -q` | 按目标文件运行 |
| `benchmark` | 长运行耐久/基准（独立于常规循环） | `python -m pytest --channel benchmark -q` | 按目标文件运行 |

**细粒度 bundle**：通道内支持 `--bundle` 切片，如 `core-runtime`、`core-solver`、`benchmark-solver-parity`、`benchmark-performance`。

### 12.2 测试层级

| 层级 | 标记 | 目标 | 例子 |
|------|------|------|------|
| Tier 0 | `tier0` | 纯单元测试（无引擎，<1s） | 配置校验、因子路由、线索提取、报告字段结构 |
| Tier 1 | `tier1` | 引擎契约测试（单 VirtualCreature，<5s） | 单步/短程状态更新、疾病变量方向性、有限输出 |
| Tier 2 | `tier2` | 场景集成（多器官耦合，<30s） | `process_action()` 时间推进、报告延迟、warmup |
| Tier 3 | `tier3` | 验证/耐久（>30s，可能数分钟） | 6000+ 步稳定性、求解器一致性、疾病耐久、长程 NaN/Inf 检测 |

### 12.3 测试约定

- 应用层 `process_action()` 测试使用 `GameRuntime` / `FakeAdvancer` 缝合点（验证记账/路由/阶段流/报告延迟策略）
- 真实引擎推进保留给疾病进展、完整报告演化、端到端集成测试
- 真实长程应用测试用显式 `@pytest.mark.slow` / `@pytest.mark.slower`
- 应用层集成测试允许更粗的测试专用 `dt`（当断言是定性的而非求解器精度敏感时）
- 全局 per-test 超时：60s（heavy 测试需要更长用 `--timeout=N`）

### 12.4 常用命令

```bash
# 快速门检（提交前 / CI）
python tools/dev/gate_check.py --quick     # API + 数据一致性 (<5s)
python tools/dev/gate_check.py --full      # + 类型一致性 (<10s)
python tools/dev/gate_check.py --fix       # 自动修复数据 + 类型同步

# 核心 app/runtime/API 信心
uv run python -m pytest --channel core -q

# 前端类型检查
.\node_modules\.bin\vue-tsc.cmd -b    # 从 vet-game-frontend/vite-project

# 窄范围 API 工作
uv run python -m pytest tests/test_interface.py -q
```

### 12.5 测试文件分布

`tests/` 目录按关注点组织，主要类别：

- **器官单元测试**：`test_heart.py`、`test_lung.py`、`test_kidney.py`、`test_liver.py`、`test_blood.py`、`test_fluid.py`、`test_gut.py`、`test_endocrine.py`、`test_neuro.py`、`test_immune.py`、`test_lymphatic.py`、`test_coagulation.py`
- **引擎/求解器测试**：`test_simulation.py`、`test_solver_drift.py`、`test_solver_endurance.py`、`test_solver_fallback.py`、`test_solver_numerics.py`、`test_solver_parity.py`、`test_solver_radau_endurance.py`、`test_radau_factor_command.py`、`test_twin_run.py`
- **疾病测试**：`test_diseases.py`、`test_disease_endurance.py`、`test_multi_disease.py`、`test_multi_disease_diagnosis.py`、`test_multi_disease_treatment.py`、`test_phosphorus_endurance.py`、`test_untreated_deterioration.py`
- **应用层测试**：`test_game.py`、`test_action_runtime_seam.py`、`test_interface.py`、`test_time_management.py`、`test_session_persistence.py`、`test_warmup_check.py`、`test_scenarios.py`、`test_comorbidity_cases.py`
- **临床解释测试**：`test_clinical_stage.py`、`test_debug_params.py`、`test_presentation_state.py`
- **耦合测试**：`test_coupling.py`、`test_coupling_lag_state.py`、`test_cross_module_coupling.py`
- **架构/契约测试**：`test_gate_contract.py`、`test_boundary.py`、`test_config_validation.py`、`test_history_schema.py`
- **生命周期测试**：`test_lifecycle.py`、`test_lifecycle_literature.py`、`test_lifecycle_v2.py`、`test_organ_health.py`、`test_organ_health_signature.py`
- **药理测试**：`test_pharmacology.py`、`test_pharmacology_factor_commands.py`
- **性能测试**：`test_performance.py`、`test_performance_observational.py`

### 12.6 开发工具（`tools/dev/`）

| 工具 | 作用 |
|------|------|
| [gate_check.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/tools/dev/gate_check.py) | 统一入口：`--quick` / `--full` / `--fix` / `--install-hook` |
| [check_api_consistency.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/tools/dev/check_api_consistency.py) | AST 校验 Flask 路由 vs `api.ts` 调用；`--fix` 同步缺失字段到 `types.ts` |
| [check_data_consistency.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/tools/dev/check_data_consistency.py) | 跨校验 7 个 JSON 数据文件（cases→diseases→clues→exams→vitals→ODE 路径）；`--fix` 自动生成缺失 `clue_descriptions` |
| [validate_baseline.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/tools/dev/validate_baseline.py) | 基线验证 |
| [sensitivity.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/tools/dev/sensitivity.py) | 敏感度分析 |
| [enrich_disease_meta.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/tools/dev/enrich_disease_meta.py) | 疾病元数据丰富 |
| [generate_param_report.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/tools/dev/generate_param_report.py) | 参数报告生成 |
| [clue_catalog_check.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/tools/dev/clue_catalog_check.py) | 线索目录校验 |
| [harness_check.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/tools/dev/harness_check.py) | 测试 harness 检查 |

---

## 13. 关键设计模式与约定

### 13.1 FactorCommand 统一写入协议

**所有外部扰动（疾病/药物/事件/耦合规则）的唯一写入入口**。

```python
@dataclass(frozen=True)
class FactorCommand:
    target: str                    # "module.attr" 如 "heart.heart_rate"
    op: Literal["multiply", "add", "set"]
    value: float
```

由 `_PARAM_PATHS` 白名单保证安全，未知 target 静默警告（fail-safe）。C7 特殊保护：`heart.blood_volume` 不允许变负。

### 13.2 双求解器路径

- **Euler**（生产，O(dt) 显式）— 当前游戏默认
- **Radau**（验证，O(dt^5) 隐式）— 研究路径
- 通过 `SolverPlugin` 抽象注入，`SolverRegistry.get(name)` 工厂获取
- Radau 失败自动退化到 Euler，计数 `_solver_fallback_count`
- `twin_run.py` 安全网：每求解器重构前先建立 dt-refinement 基线，保证数值行为不退化

### 13.3 半隐式 Gauss-Seidel 耦合

**两套耦合机制并存**：

| 机制 | 路径 | 数据源 |
|------|------|--------|
| `CONNECTIONS` 表 | Radau intra-step | `engine/topology.py` 静态表，路由 outputs→cached_inputs |
| `CouplingEngine` | Euler post-step | `data/coupling_rules.json`，jsonschema 校验 |

Radau 路径在 `unified_rhs` 中各模块的 `derivatives()` 只读 `_cached_inputs`（上一次调用的 outputs），模块按固定顺序求导，Newton 迭代自动收敛到耦合不动点。

### 13.4 声明式模块契约

每个器官声明 `INPUTS / OUTPUTS / READS_BLOOD / WRITES_BLOOD / STATE_VARS` 类属性：
- 纯声明性，不改变运行时行为
- Phase 5+ 用于自动派生 CONNECTIONS 表、拓扑验证、模块文档生成、测试桩

### 13.5 BloodShim 可观察代理

透明包装 `BloodCompartment`：
- `__getattr__` / `__setattr__` 拦截所有读写，记录到 `SignalBus`
- 9 个器官模块代码不变（`self.blood.X = value` 仍工作）
- 为 Phase 6 迁移到真实 blood 字段做准备

### 13.6 organ_guard 写保护

强制器官模块通过 FactorCommand 写入：
- 替换器官模块的 `__setattr__`
- 拦截 `blood.*` 赋值并抛出 `AttributeError`
- `_blood_escape(cls)` 上下文管理器仅在 `__init__` 时合法注入 blood 引用

### 13.7 配置驱动扩展

- **疾病**：编辑 `data/ode_diseases.json` 即可新增，无需写 Python 类
- **检查**：编辑 `data/examinations.json` + `data/exam_templates.json`，无需 Python 代码
- **耦合规则**：编辑 `data/coupling_rules.json`，jsonschema 校验
- **生命体征范围**：编辑 `data/vitals_ranges.json`

### 13.8 多病叠加 chained-rebase 语义

| op | 链式行为 |
|----|----------|
| `multiply` | 复合效应（DCM 0.7 × 肺炎 0.8 = 0.56） |
| `add` | 累加 |
| `set` | 后写者赢 |

排序 = `attach_disease` 调用顺序。

### 13.9 会话锁强制

- 所有读写 session-owned 状态的端点都用 `with lock:` 包裹
- 状态变更端点：`examine` / `administer-drug` / `diagnose` / `wait`
- 快照端点也应锁：`game-state` / `hint` / `diagnosis`
- 无锁的 session 视为无效（即使 `_game_sessions` 还有 state）

### 13.10 前端 GET 参数规范

- GET 请求参数必须走 query string，不能放 request body
- 值用 `encodeURIComponent` 编码
- `tools/dev/check_api_consistency.py` 维护端点模式一致性

### 13.11 代码风格约定

- **Frozen dataclasses**：值对象用 `@dataclass(frozen=True)`
- **禁止 `print()`**：用 `logging` 模块
- **注释**：解释 "why" 而非 "what"；hack workaround 必须有 `# TODO(YYYY-MM-DD):`
- **数据外置**：疾病 ODE / 线索 / 治疗协议 / 检查定义放在 `data/*.json`，不硬编码 Python
- **uv run**：所有 Python 命令通过 `uv run` 保持隔离
- **不创建文档文件**：除非用户明确请求

### 13.12 已知灰区（边界不完美）

按 `docs/architecture.md` 描述，这些是已知边界不完美，非期望终态：

1. ~~**`attach_disease()` 初始化 `ClinicalSignsEngine`** — 内核生命周期耦合下游解释关注。期望：移到外层组合层。~~
   **已修复 (R6 Layer A, 2026-06-28)**：删除内核对 `ClinicalSignsEngine` 的 import；`_ensure_legacy_clinical_signs_engine` / `_refresh_legacy_clinical_signs` 转为 no-op stub；`legacy_clinical_signs_enabled` 默认 False；解释层初始化完全移至 `build_external_interpretation_bundle`（game/runtime_composition.py）。
2. **`to_persistence_snapshot()` 描述会话持久化语义** — 会话持久化是应用关注而非内核关注。期望：移到 adapter 或 persistence 层。
   **部分缓解 (R6 Layer B, 2026-06-28)**：新增 `game/persistence_adapter.py::build_persistence_snapshot(engine)` thin wrapper；`gui_app.py::_snapshot_json` 委托 adapter 而非直调内核方法。完整迁移（将 snapshot shaping 移出 kernel）待测试访问模式重构后进行。
3. **游戏层夜间修正直接改 cardiac baseline** — 若昼夜效应是生理学，应成为环境输入；若仅游戏节奏，不应伪装为内核生理。
4. **历史文档仍描述被取代的时间模型** — 以 `README.md` 和 `docs/architecture.md` 为权威，旧叙事文档为历史记录。

---

## 附录：扩展指南

### 新增疾病

1. 在 [data/ode_diseases.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/ode_diseases.json) 添加条目：
   - `severity_presets`（`mild`/`moderate`/`severe` 的 ODE 率常数）
   - `state_variables`（每个含 `ode_type`、`params`、`clamp`、表达式字符串）
   - `outputs`（每个含 `target`、`op`、`fn`、可选 `condition`）
2. 在 [data/diseases.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/diseases.json) 添加线索、治疗协议、胜负消息
3. 在 [data/cases.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/cases.json) 添加可选病例
4. 无需写 Python — `ConfigDrivenDiseaseModule` 自动处理

**自定义 ODE 类型**：若内置类型不足，注册自定义求解器：

```python
from src.diseases import register_ode_type
register_ode_type("my_ode", lambda value, params, state_vars, engine_state, dt: new_value)
```

### 新增检查类型

1. 在 [data/examinations.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/examinations.json) 添加条目（`tier` 1-5、`cost` AP、`latency_turns`、`category`）
2. 在 [data/exam_templates.json](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/data/exam_templates.json) 添加报告模板（`vitals`、`extra_params`、`findings_rules`、`tag_rules`）
3. 前端改动后运行 `vp build` 更新 `static/`
4. 无需 Python 代码 — `report_engine.py` 和 `exam_registry.py` 完全配置驱动

### 新增药物

1. 在 [src/pharmacology.py](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%AA%8C/virtual-vet/src/pharmacology.py) 继承 `Drug` 基类并重写 `factor_commands(pd_effect)`
2. 调用 `register_drug(name, cls)` 注册
3. 在 `data/treatments.json` 添加治疗选项（若作为治疗方案）

---

## 参考文档索引

权威文档（按优先级）：

1. [README.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/README.md) — 项目整体定位
2. [docs/architecture.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/docs/architecture.md) — 架构权威规则
3. [docs/kernel-first-design.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/docs/kernel-first-design.md) — 综合设计叙事
4. [docs/kernel-time-architecture-sketch.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/docs/kernel-time-architecture-sketch.md) — 时间系统设计
5. [docs/testing.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/docs/testing.md) — 测试策略
6. [AGENTS.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/AGENTS.md) — Agent 工作指南
7. [CLAUDE.md](file:///c:/Users/ZhuanZ%E5%95%E1%BF%AF%E5%AF%86%E7%A0%81/Desktop/Claudecode/01_%E4%BB%A3%E7%A0%81%E5%AE%9E%E9%BA%8C/virtual-vet/CLAUDE.md) — 贡献者指南

---

*本文档生成自项目源码分析，作为代码导览。遇到语义冲突以权威文档为准。*