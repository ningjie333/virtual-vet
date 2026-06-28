# Architecture Improvement Plan

基于 2026-06-27 的 xfail 清零工程中发现的架构问题。

## P0 — 影响正确性，尽快修复

### 1. 统一一阶滞后实现

**现状**：同一类问题四种实现，只有一种是正确的。

| 位置 | 实现 | 正确性 |
|------|------|--------|
| `heart._first_order_relax` | `1 - exp(-dt/τ)` | ✅ |
| `kidney._apply_RAAS` | `min(dt/τ, 1.0)` | ❌ Euler 近似 |
| `organs/coupling.py` | `dt/τ` | ❌ Euler 近似 |
| `diseases/config_driven.py` | `dt/τ` | ❌ Euler 近似 |

**后果**：Euler 离散化导致 dt 敏感性，本轮已修复 kidney 和 coupling，但 disease 模块仍有 4 处。

**修复**：提取 `src/engine/numerics.py::first_order_lag(value, target, dt, tau)` 公共函数，使用精确指数解。所有模块统一调用。

**风险**：低。指数解对所有参数都优于 Euler 近似（Taylor: `1-exp(-x) ≈ x - x²/2`）。

---

### 2. FactorPipeline 幂等性

**现状**：`apply_factor` 的 `multiply`/`add` 操作每步都执行，导致复合。

```
疾病模块每步都返回同一个 FactorCommand("heart.SVR", "multiply", 0.912)
→ apply_factor 每步执行 SVR *= 0.912
→ 60 步后 SVR = 0.004（归零）
```

**根因**：命令系统不知道 "multiply by 0.912" 是"基准值应该是 0.912×"还是"每步递减 8.8%"。

**修复方案**（二选一）：

**方案 A（推荐）：命令加幂等标记**
```python
FactorCommand("heart.SVR", "multiply", 0.912, idempotent=True)
# apply_factor 对幂等命令：记录上次目标值，只在值变化时重新应用
```

**方案 B：疾病模块跟踪已应用值**
```python
# 疾病模块的 compute() 返回 delta，不是绝对值
# 需要状态追踪，复杂度高
```

**风险**：方案 A 中等。需要仔细处理 "上次目标值" 的存储和失效。方案 B 高。

---

## P1 — 影响可维护性，可排期修复

### 3. 统一 engine_state 构建

**现状**：Euler 和 Radau 路径各自构建 `engine_state` dict，键名不一致。

```
Euler: {"heart": {"heart_rate_bpm": ...}}  # 用 heart_rate_bpm
Radau: {"heart": {"HR": ...}}              # 用 HR
```

**后果**：本轮发现 Radau 路径的疾病模块因键名不匹配而直接报错（`KeyError: 'heart_rate_bpm'`），说明 Radau 路径长期未与疾病模块一起测试。

**修复**：提取 `src/engine/step_common.py::build_engine_state(engine)` 统一函数，Euler 和 Radau 都调用。

**风险**：低。纯重构，不改变行为。

---

### 4. 统一 step 流程

**现状**：`_step_euler` 和 `_step_radau` 各自 ~200 行，包含大量重复的模块调用顺序。

**修复**：提取 `_step_physiology(engine, dt, solver)` 模板方法，Euler 和 Radau 的差异仅在于 `compute()` vs `derivatives()` 的调用方式。

**风险**：中等。需要仔细设计模板模式，确保不改变 step 顺序。

---

## P2 — 改善一致性，按需修复

### 5. 统一命名规范

**现状**：同一物理量在不同上下文中有不同名字。

| 量 | 出现形式 |
|----|----------|
| 心率 | `heart_rate_bpm`, `HR`, `heart_rate`, `hr_bpm` |
| 心输出量 | `cardiac_output_ml_min`, `CO`, `cardiac_output` |
| 平均动脉压 | `MAP_mmHg`, `MAP`, `mean_arterial_pressure` |

**修复**：选定一种规范（建议 `snake_case_with_units`），在 `engine_state` 构建时统一映射，内部模块保持不变。

**风险**：低。但需要在 `_PARAM_PATHS` 中增加别名映射。

---

### 6. 生理参数集中管理

**现状**：`SVR_BAROREFLEX_TAU_SEC=10`, `TAU_RAAS=120` 等常量散落在各模块中。

**修复**：创建 `src/parameters.py::PhysiologyParams` dataclass 或 `data/physiology_params.json`，集中管理所有可调参数。改参数不需要找文件。

**风险**：低。纯重构。

---

## 执行顺序

```
P0.1: 统一一阶滞后（1 天）
  → 跑全量回归，确认无 regression

P0.2: FactorPipeline 幂等性（2-3 天）
  → 跑全量回归 + 专门测试幂等行为

P1.1: 统一 engine_state（1 天）
  → 跑全量回归

P1.2: 统一 step 流程（2-3 天）
  → 跑全量回归 + Euler/Radau 对比验证

P2.1: 命名规范（1 天）
P2.2: 参数集中（1 天）
```

先做 P0.1 和 P0.2，它们直接影响正确性。P1 和 P2 是技术债务清理，不影响功能。

---

## 根因层修复（R1–R6）

P0–P2 完成后，进一步审视发现 6 条结构性根因。本节记录已完成项。

### R3 — 顺序无契约

**现状**：10+ 处顺序约束只存在于代码物理行序，无接口契约。Euler 和 Radau 路径之间存在结构性不对称（disease/immune 顺序相反、organ_health 写入机制不同、Radau 路径完全缺失 `snapshot_baselines` / `clear_baselines` / `refresh_state_dicts` 调用）。`empty_state` 未定义导致 `immune.compute()` 在 Radau 路径从未实际执行（NameError 被 try/except 静默吞掉）。

**修复**：

- 新增 [src/engine/step_contract.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/step_contract.py)：
  - `StepGuard` 类：跟踪 phase 进展（有序列表）+ state invariants（布尔标志）+ intentional divergences（记录不抛异常）
  - 18 个 phase 常量、2 个 invariant 常量、5 个 divergence 常量
  - `StepContractError` 异常类型
- 修改 [src/engine/step_common.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/step_common.py)：`run_organ_compute_chain` / `refresh_state_dicts` / `run_pre_dispatch` / `run_physiology_post` / `run_coupling` / `run_post_dispatch` 全部添加 `guard` 参数与契约断言
- 修改 [src/engine/factor_pipeline.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/factor_pipeline.py)：`snapshot_baselines` / `clear_baselines` 添加 `guard` 参数（lazy import 避免循环依赖）
- 修改 [src/engine/__init__.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/__init__.py)：导出 `StepGuard`, `StepContractError`
- 修改 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py) `_step_euler`：创建 `StepGuard(label="euler")`，记录 5 条 intentional divergences，每个 phase 后 `guard.mark(...)`
- 修改 [src/engine/solvers/radau.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/solvers/radau.py) `run_radau_step`：
  - 全部 phase 标记 + 5 条 divergence 文档化
  - **修复 1**：补回缺失的 `snapshot_baselines(engine, guard=guard)`（disease/organ_health multiply op 之前）
  - **修复 2**：补回缺失的 `refresh_state_dicts(..., guard=guard)`（organ_health 应用之后）
  - **修复 3**：补回缺失的 `clear_baselines(guard=guard)`（step 结尾）
  - **修复 4**：定义 `empty_state: dict = {}`（之前 NameError 让 `immune.compute()` 在 Radau 路径从未执行）
- 新增 [tests/test_step_contract.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/tests/test_step_contract.py)：
  - `TestStepGuardBasic`：mark/has、require、require_not、completed_phases、reset
  - `TestStepGuardInvariants`：invariant tracking + snapshot-after-clear 拒绝
  - `TestStepGuardDivergences`：divergence 记录（不抛异常）
  - `TestStepGuardDisabled`：disabled 模式跳过所有检查
  - `TestStepFunctionContracts`：集成测试 run_organ_compute_chain / run_coupling / refresh_state_dicts
  - `TestStepGuardNoneBackwardCompat`：`guard=None` 向后兼容
  - `TestEulerStepCompletesAllPhases`：Euler 单步/多步无契约违反
  - `TestRadauStepCompletesAllPhases`：Radau 单步/多步（含 sepsis disease）无契约违反

**5 条有意分歧**（Euler vs Radau，由 `guard.divergence_ok()` 文档化）：

| 分歧 | Euler | Radau |
|------|-------|-------|
| immune 顺序 | 在 coupling 之前（Step 4.9） | 在 coupling 之后（Step 7b），ODE 部分由 solve_ivp 积分 |
| disease 顺序 | 在 organ compute 之前（Step 2.5） | 在 coupling 之后（Step 7），ODE 部分由 solve_ivp 积分 |
| coupling resolve 次数 | 2 次（4.95 + 8） | 1 次（不需要 Gauss-Seidel 松弛） |
| chemoreceptor 延迟 | 1 步滞后（Gauss-Seidel） | 无延迟（隐式积分） |
| organ_health 写入机制 | 直接 `setattr` | 通过 `apply_factor('multiply')`（baseline-protected） |

**验证**：986 个 core channel 测试全部通过，30 个新增契约测试全部通过，18 个 twin-run 测试全部通过。

**风险**：低。`guard` 参数默认 `None`，向后兼容；StepGuard 是检测器而非调度器，不改变运行时行为。

### R4 — 两套耦合机制（深度统一）

**现状**：项目存在 3 套耦合机制：
- **Mechanism A**：`SignalBus` + `BloodShim`（半完成脚手架，行为中性，仅 liver 接入）
- **Mechanism B**：`CouplingEngine`（Euler 路径，post-step 规则引擎，`data/coupling_rules.json`，16 规则 5 启用）
- **Mechanism C**：`CONNECTIONS`（Radau 路径，intra-step 半隐式耦合，`src/engine/topology.py`）

存在 4 类问题：Mechanism A 死代码、`_CouplingFactorCommand` 类型漂移、CONNECTIONS 死路由（28 条）、Euler 双 resolve 隐式化不足。B/C 覆盖漂移需评估是否折叠 RAAS 规则。

**修复（5 个阶段）**：

**Stage 1 — Mechanism A 死代码清理**：
- 删除 [src/engine/signal_bus.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/signal_bus.py)（`SignalBus` + `BloodShim`）
- 删除 [src/organs/contracts.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/organs/contracts.py)（`ModuleContract` 脚手架）
- 修改 [src/engine/__init__.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/__init__.py)：移除 `SignalBus`/`BloodShim` 导出
- 修改 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py)：`self.blood = BloodCompartment(...)` 直连，移除 10 个 `signal_bus.register_module(...)` 调用
- 修改 [src/organs/__init__.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/organs/__init__.py)：移除 `contracts` 导入
- 修改 [src/liver.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/liver.py)：移除 `signal_bus` 参数，简化 `_blood_read`/`_blood_write`

**Stage 2 — `_CouplingFactorCommand` 类型漂移消除**：
- 修改 [src/common_types.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/common_types.py)：`FactorCommand` 添加 `source: str = ""` 字段
- 修改 [src/organs/coupling.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/organs/coupling.py)：`resolve()` 返回 `FactorCommand`（带 `source="coupling:<rule_name>"`），删除 `_CouplingFactorCommand` 类
- 修改 [tests/test_coupling.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/tests/test_coupling.py)：`c._source` → `c.source`

**Stage 3 — CONNECTIONS 死路由清理**：
- 修改 [src/engine/topology.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/topology.py)：CONNECTIONS 从 48 条路由缩减到 20 条活跃路由（移除 28 条死路由）
  - 移除所有 `blood` 目标路由（blood 不在 `UNIFIED_MODULES`）
  - 移除所有 `blood` 源路由（blood 从不产生 derivatives 输出）
  - 移除 7 条 `src_var` 命名不匹配的死路由
- 修改 [src/engine/state_vector.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/state_vector.py)：更新 `unified_rhs` docstring（`if val is not None` 现为防御性回退）

**Stage 4 — Euler 双 resolve 显式化为 substep 松弛循环**：
- 修改 [src/engine/step_contract.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/step_contract.py)：新增 `PHASE_COUPLING_RESOLVE_2` phase 常量
- 修改 [src/engine/step_common.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/step_common.py) `run_coupling`：在 resolve+apply 后标记 `PHASE_COUPLING_RESOLVE_2`，更新 docstring 标注 "substep 2 (fresh)"
- 修改 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py) `_step_euler`：更新 Step 4.95 注释为 "substep 1 (lagged)"，更新 `DIVERGENCE_COUPLING_RESOLVE_COUNT` 注释引用显式 substep 结构

**Stage 5 — B/C 覆盖漂移评估**：
- **结论：不折叠 RAAS 规则**。两套机制在不同抽象层级运作，非冗余：
  - Mechanism C（CONNECTIONS）= 被动值传递（`derivatives()` outputs → `_cached_inputs`）
  - Mechanism B（CouplingEngine）= 主动状态突变（`FactorCommand` multiply/set 写入实例属性）
- RAAS 规则（`kidney.renin → heart.SVR multiply`）无法折叠到 CONNECTIONS：`heart.SVR` 是状态变量，不是 `heart.derivatives()` 的输入；需要 post-step factor 应用
- 详见 [docs/coupling_inventory.md](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/docs/coupling_inventory.md) "R4 Stage 5 Evaluation" 章节

**验证**：986 个 core channel 测试 + 28 个 twin-run/Radau 测试 + 30 个契约测试全部通过。

**风险**：中。Stage 1 删除死代码可能影响未覆盖的代码路径；Stage 3 移除死路由改变了 Radau 路径的 `_cached_inputs` 写入（虽然死路由从不被消费，但理论上可能影响内存布局）。Stage 4 纯为可读性改进，无行为变化。twin-run 测试作为回归门禁。

### R5 — 疾病生命周期（深度统一）

**现状**：疾病模块存在 4 个结构性缺陷：
1. **单数/复数分裂**：Euler/IVP 路径用 `self.diseases`（列表，正确处理多病）；Radau Step 7 + state_vector pack/unpack 用 `engine.disease`（单数，仅第一个）→ 多病叠加在 Radau 路径完全失效
2. **生命周期状态机缺失**：只有 `active` bool + `activated_at_s`；无 resolved/cured/dead 状态；`deactivate()` 不清状态、不移除、不通知
3. **不可变性假设**：severity 构造时写入永不变更；`_state_vars` 单调演化；无恶化/好转/治愈/复发路径
4. **持久化不完整**：`to_persistence_snapshot` 只存四舍五入摘要；无 `from_snapshot`；跨 session 疾病进度丢失

**修复（4 个阶段）**：

**Stage 1 — 修复单数/复数分裂（Radau 多病支持）**：
- 修改 [src/engine/state_vector.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/state_vector.py)：`build_state_map` / `pack_state` / `unpack_state` / `unified_rhs` 全部从 `engine.disease`（单数）改为遍历 `engine.diseases`（列表），用 `disease.{name}` 命名空间隔离多病 state_var
- 修改 [src/engine/solvers/radau.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/engine/solvers/radau.py) Step 7：从 `engine.disease`（单数）改为遍历 `engine.diseases`（active 列表）

**Stage 2 — 生命周期状态机**：
- 修改 [src/diseases/__init__.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/diseases/__init__.py)：新增 `DiseaseState` 枚举（INCUBATING/ACTIVE/RESOLVED/DEAD）+ `state` 属性 + `mark_dead()` 方法；`activate()`/`deactivate()` 使用状态转换；`active` 改为 property（`state == ACTIVE`）保持向后兼容
- 新增 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py) `detach_disease()` 方法：仅在 RESOLVED/DEAD 状态可从 `self.diseases` 列表移除（之前无 detach 机制，列表单调增长）
- 修改 [src/diseases/config_driven.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/diseases/config_driven.py) `compute()`：新增 `resolve_when` 配置支持自动治愈（条件满足时 ACTIVE → RESOLVED）
- 更新 `summary()` 方法：新增 `state` 和 `severity` 字段

**Stage 3 — 动态 severity（恶化/好转）**：
- 修改 [src/diseases/config_driven.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/diseases/config_driven.py)：重构 `_build_params()` + `_init_state_vars_and_meta()` 为独立方法；新增 `set_severity(new_severity)` 方法（重建 `_params` + `_var_meta`，保留 `_state_vars` 疾病进展历史）；新增 `severity` property
- 新增 `worsen_when` / `improve_when` 配置：在 `compute()` 中检查条件，自动升级/降级 severity（需配置 `severity_order`，默认 `["mild", "moderate", "severe"]`）
- 重构 `_check_resolve_conditions()` 为通用 `_check_conditions(conditions)` 辅助方法（供 resolve_when/worsen_when/improve_when 复用）

**Stage 4 — 持久化恢复**：
- 修改 [src/diseases/config_driven.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/diseases/config_driven.py)：新增 `full_state()` 方法（返回完整精度状态 + activated_at_s，区别于 `summary()` 的四舍五入摘要）；新增 `restore_state(state_dict)` 方法（恢复 _state_vars/severity/state/activated_at_s）
- 修改 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py) `to_persistence_snapshot()`：新增 `disease_state_full` 字段（完整精度，含所有疾病不止 active 的）
- 新增 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py) `restore_diseases(disease_state_full)` 方法：从快照重建疾病实例并恢复状态

**验证**：986 个 core channel 测试 + 274 个 twin-run/Radau/multi-disease/contract/diseases/game 测试全部通过。full_state/restore_state round-trip 验证通过（完整精度保留）。

**风险**：中。Stage 1 改变了 Radau 路径的 y-vector 布局（从单疾病 `("disease", vname)` 改为多疾病 `("disease.{name}", vname)`），但 y-vector 仅用于内部积分不持久化，twin-run 测试验证无回归。Stage 2 的 `active` property 改动通过向后兼容 setter 保持现有 API 不变。Stage 3 的 `set_severity` 不重置 `_state_vars`（保留进展历史）。Stage 4 的 `disease_state_full` 是新增字段，不影响现有 `disease_state` 字段。

**未涉及（留给 R6）**：架构耦合问题（`_ClinicalSignsEngine` 内嵌内核 — `attach_disease` 触发解释层初始化），CODE_WIKI 已标记，需跨层重构。

### R6 — 接口碎片化（三层清理）

**现状**：跨层架构耦合、状态暴露/持久化碎片化、Flask/session/契约碎片化三层问题，CODE_WIKI "已知灰区" #1/#2/#3 标记。

**修复（三层）**：

**Layer A — 跨层架构耦合（删除内核 `_ClinicalSignsEngine` 内嵌）**：
- 修改 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py)：
  - 删除 `from src.clinical_signs_engine import ClinicalSignsEngine as _ClinicalSignsEngine` import
  - 删除未使用的 `import json` 和 `from pathlib import Path`
  - `legacy_clinical_signs_enabled` 默认值从 `True` 改为 `False`
  - `_ensure_legacy_clinical_signs_engine` 转为 no-op stub
  - `_refresh_legacy_clinical_signs` 转为 no-op stub
- 修改 [gui_app.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/gui_app.py) `_get_active_signs`：从直读 `vc.clinical_signs_engine` 改为走 `runtime.interpreter.active_signs(vc)` 走外层组合层

**Layer B — 状态暴露/持久化碎片化清理**：
- 新增 [game/persistence_adapter.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/game/persistence_adapter.py)：外层 adapter `build_persistence_snapshot(engine)` 包装内核 `to_persistence_snapshot()`，使会话持久化关注点离开内核
- 修改 [gui_app.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/gui_app.py) `_snapshot_json`：委托给 adapter 而非直接调用 `vc.to_persistence_snapshot()`
- 修改 [src/simulation.py](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/src/simulation.py) `to_minimal_snapshot`：docstring 标记为 deprecated legacy alias，指向新 adapter

**Layer C — Flask/session/契约碎片化清理（7 项）**：

| 编号 | 问题 | 处理 |
|------|------|------|
| C1 | `api_examine` 不用 `_session_lock_or_404` helper，直接读 `_session_locks` 字典 | 改用 helper，与 administer_drug/diagnose/wait 等其余 6 端点统一 |
| C2 | `api_session_replay` 不锁 | **不锁是正确设计** — 此端点只读 SQLite（已结案会话回放），不触碰内存态；服务器重启后内存丢失但 DB 仍在，强行加锁会 404。加 docstring 说明原因 |
| C3 | `api_new_game` 3 个字典分别写入（`_session_locks` / `_game_sessions` / `_session_runtimes`），并发请求可能见到部分状态 | 改为先创建并获取锁，所有字典写入（含 `_action_seq` 初始化）在锁内原子完成 |
| C4 | 4 个 session 字典（`_game_sessions` / `_session_runtimes` / `_session_locks` / `_action_seq`）应聚合为 `SessionContext` 类 | **DEFERRED** — `tests/test_interface.py` / `test_multi_disease_diagnosis.py` / `test_pharmacology.py` 直接访问这 4 个字典共 28+ 行，重构超出 R6 范围，留为已知债务 |
| C5 | `api.ts` 5 个端点的响应类型内联声明，与 `AdministerDrugResponse` 漂移 | 在 [types.ts](file:///c:/Users/ZhuanZ（无密码）/Desktop/Claudecode/01_代码实验/virtual-vet/vet-game-frontend/vite-project/src/types.ts) 新增 `ExamineResponse` / `DiagnoseResponse` / `WaitResponse` / `GameStateResponse` / `NewGameResponse` 5 个具名接口；api.ts 引用而非内联 |
| C6 | `BACKEND_RESPONSE_FIELDS` 手抄字典含 6 个幽灵字段（`ap` / `max_ap` / `stress` / `ap_cost` / `combo_bonus` / `time_used`）+ 漏 5+ 真实字段 | **已在前序工作解决** — `check_api_consistency.py` 的 AST 提取（`extract_response_schemas()`）是真理之源；手抄字典保留为 `--dry-run` 对照组（用户决策），不再使用 |
| C7 | 7 个端点用 2 种文案（"游戏会话不存在，请先开始新游戏" vs "游戏会话不存在"） | 新增 `_SESSION_NOT_FOUND_MSG` 常量，13 处错误消息统一引用 |

**验证**：
- 986 个 core channel 测试通过
- 64 个 twin-run/Radau/multi-disease 测试通过
- 65 个 step-contract/diseases 测试通过
- 122 个 interface 测试通过
- 44 个 snapshot 相关测试通过
- `vue-tsc -b` 通过（前端类型干净）
- `check_api_consistency.py` 通过：18 后端路由 / 17 前端调用，无 dead route / GET body 违规

**复查修订（2026-06-28）**：首轮验证后发现 3 处遗漏，全部修复：
1. **C5 字段缺失**：首轮提取 5 个具名 interface 时遗漏了 `ExamineResponse.action_started_at_s` / `state_time_s`（examine 端点独有字段）和 `GameStateResponse.active_signs`（game-state 端点的核心字段）。通过 `check_api_consistency.py --dry-run` 的 AST 提取对照发现并补齐
2. **C7 replace_all 假阳性**：首轮报告 "All occurrences replaced" 但实际仍有 2 处字符串字面量未替换（`api_administer_drug` 和 `api_diagnose` 的 `if not state` 分支）。手动再替换一次确认全部统一
3. **C3 竞态窗口仍在**：首轮实现 "先创建锁再写入字典" 仍有竞态——并发请求在 `_session_locks[sid] = new_lock` 之前查不到锁，会创建新锁实例导致互不阻塞。改为用模块级 `_registry_lock` 短临界区保护 "create_lock + populate 4 dicts" 原子完成；`_registry_lock` 与 session 锁不嵌套，无死锁风险

**其他复查结论**：
- Layer A 残留的 `getattr(engine, "clinical_signs_engine", None)` fallback（clinical_interpreter / interpretation_refresher / report_engine / ascii_dashboard / textual_monitor）在 `legacy_clinical_signs_enabled=False` 下都返回 None，安全降级，不影响生产
- Layer B `persistence_adapter` 是 thin wrapper（仅 1 行委托），方向正确（app → kernel）无循环依赖；5 条状态暴露路径仍在（P2.5 已知债务）
- C1 7 个端点的锁模式完全一致：`_session_lock_or_404(session_id, _SESSION_NOT_FOUND_MSG)` + `with lock:` + `_game_sessions.get()` None 检查（防 TOCTOU）
- `_get_active_signs` 唯一调用点（`api_game_state:751`）已正确传 `runtime=runtime`

**风险**：低-中。
- Layer A 风险中：删除内核 `_ClinicalSignsEngine` 内嵌可能影响未覆盖的旧调用路径，但 `legacy_clinical_signs_enabled=False` 默认值使旧路径失效，stub 保证不报错。`_get_active_signs` 改走 runtime 是已验证的路径（`build_external_interpretation_bundle` 在 R5 已是目标模式）
- Layer B 风险低：adapter 仅是包装，行为不变；`to_minimal_snapshot` deprecated alias 保持向后兼容
- Layer C 风险低：C1/C3/C7 是局部统一化；C2 仅文档；C5 是结构化重构无行为变化；C6 已是既成事实
- C4 DEFERRED 风险低：4 个字典继续以并行 dict 维护，行为正确只是结构不优雅

**未涉及（留给后续）**：
- C4 `SessionContext` 聚合类（需要先重构测试访问模式）
- CODE_WIKI "已知灰区" #4（前端 `BACKEND_RESPONSE_FIELDS` 类似手抄模式已在 check_api_consistency.py 解决，但其他类似模式可能存在）
