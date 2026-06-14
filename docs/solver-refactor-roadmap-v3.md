# Solver Refactor Roadmap v3

> 稳定优雅为主。基于 3-agent（Architect + Code Reviewer + Healthcare Reviewer）多视角审计。
> Created: 2026-06-13

## 设计原则

- **Euler 是生产路径**，Radau 是**验证路径**（不是另一种 production 模式）
- 新增 solver 只需关心"如何积分"，不碰耦合/器官/历史
- 任何改耦合/打包的步骤必须先有 twin-run 验证兜底

## 序列：1→4→5→2→3

（Architect 推荐：先 Radau 拆分再 auto-derive，先 validation harness 再耦合统一）

| 步 | 行动 | 状态 | Commit | 估时 |
|---|------|------|--------|------|
| **0a** | Radau fallback return dict + fallback_count 检测 | ✅ | d9afcd5 | 30min |
| **0b** | History schema 统一（Euler/Radau 同 45 键） | ✅ | 0c95400, 3884d29 | 2hr |
| **0c** | organ_health.track 签名对齐（pre-state） | ✅ | 469eb8d | 1hr |
| **0d** | Radau 5a blood 写走 apply_factor | ✅ | 14d6a51 | 3hr |
| **1** | 公共化 `pack_state/unpack_state/unified_rhs` | ✅ | 79b244b | 2hr |
| **2** | 加 `STATE_VARS` 类属性（替代硬编码 _UNIFIED_MODULES） | ✅ | 5cd27a4 | 4hr |
| **3** | Radau 拆到 `src/engine/solvers/radau.py` | ✅ | 4375e1c | 3hr |
| **4** | Twin-run validation harness（10 场景 + 收敛率） | ✅ | 467b5b7 | 6hr |
| **5** | Gauss-Seidel docstring + 耦合统一 | ✅ (docstring + 清册; 真正统一留后续) | 569889f | 6hr |

## 关键设计决策

### D1: STATE_VARS（不是 OUTPUTS）用于 state packing

OUTPUTS 是计算接口（如 cardiac_output, MAP），不是 ODE 积分变量。
需要新声明 `STATE_VARS = (("HR", "heart_rate"), ...)` 元组。

### D2: Twin-run 容忍矩阵

per-vital 绝对+相对容忍，严重度乘数只放宽不收紧。详见 healthcare reviewer 报告。

### D3: Radau fallback 必须可检测

twin-run 断言 `_solver_fallback_count == 0`，防止"Radau 失败→fallback Euler→自比较通过"。

### D4: 耦合统一放最后

`_unified_rhs` 的 CONNECTIONS 路由 vs CouplingEngine.resolve() 是两种机制。
先用 twin-run 验证当前行为，再动耦合。

## 测试结果

- **初始状态**（refactor 前）：940 passed, 4 failed（全部 pre-existing），3 xpassed
- **最终状态**（refactor + bug-fix 后）：core **789 passed / 0 failed**，heavy **946 passed / 1 failed**，5 xfailed
- **全程零新增回归**
- 4 个 pre-existing 的最终状态：
  - ✅ **manifest 摘要** — Step 4 顺手修复（重生成 test-manifest-summary.md）
  - ✅ **mechanism B `fever_state` ValueError** — sepsis 漏声明 fever_state 状态变量，补上（commit `08e1d32`）
  - ✅ **WBC=0.0** — 公式用了被安全加固移除的 getattr/hasattr + 未定义 thresholds；改 `source: state.WBC` + fixture 改 severe（commit `08e1d32`）
  - ❌ **耦合振荡 moribund 误判** — RAAS 耦合振荡（MAP/GFR/urine 每步 50-97% swing），需真正的耦合统一工程（见 `docs/coupling_inventory.md` 后续方向）

### Step 1 验证（2026-06-14）

- `pack_state` / `unpack_state` / `unified_rhs` / `UNIFIED_MODULES` 抽到
  `src/engine/state_vector.py`（模块级函数，仿 `step_common.py` 风格）。
- `simulation.py` 保留同名实例方法作瘦转发，`_UNIFIED_MODULES = UNIFIED_MODULES`
  保向后兼容（experiments/tools 70+ 引用零修改）。
- 验证：gate_check --quick 通过；core channel **781 passed, 2 failed**，
  两个失败（manifest 摘要 + mechanism B ValueError）均为 pre-existing
  （已用 `git stash` 在 baseline 上复现确认）。
- 真 Radau 单步测试因本机 Python 3.14 + scipy 的 LU 分解性能问题超时
  （pre-existing 环境问题，非行为回归）；faked-solve_ivp 的 fallback 测试
  完整跑过 `_step_radau` → 新 `_pack/_unified_rhs/_unpack` 路径，全通过。

### Step 4 验证（2026-06-14）

- 新增 `src/engine/twin_run.py`（harness 核心）+ `tests/test_twin_run.py`
  （10 场景 + 5 个 harness 自测 + 1 个 opt-in Radau 测试）。
- **策略调整**：路线图原写 Euler-vs-Radau，但本机 Python 3.14 + scipy 1.17
  下真 `solve_ivp(Radau)` 单步 >5min 硬阻塞（baseline 同样，非代码 bug）。
  改用 **Euler(dt_prod=0.1) vs Euler(dt_ref=0.01)** dt 加细（Richardson 风格
  收敛验证），保留 opt-in 真 Radau 模式（`TWIN_RUN_REFERENCE=radau` 环境变量，
  CI/他机可启用，本机 skipif）。
- **容忍矩阵（D2）**：per-vital 相对容忍（HR/MAP 2%、CO 3%、PO2/PCO2 3%、
  saturation 1%、pH 0.5%、GFR 5%、urine 20%、blood_volume 1%）× 场景乘数
  （healthy 1.0 → disease_severe 3.0，只放宽不收紧）。
- **fallback 检测（D3）**：每个 twin-run 断言 `reference._solver_fallback_count == 0`。
- **10 场景基线**：5 PASS（healthy / blood_loss_mild / blood_loss_severe /
  arf_severe / exercise），5 xfail（fluid_resuscitation / arf_moderate /
  dcm_moderate / hypoadrenocorticism_moderate / cocaine）—— xfail 集记录
  pre-existing 数值/耦合噪声地板，**Step 5 改耦合时不得让 PASS 的变 FAIL，
  也不得让 xfail 的发散更严重**。hypoadrenocorticism 的 xfail 根因是
  angiotensin_II 277% 耦合振荡（roadmap 4 个 pre-existing 之一）。
- 验证：gate_check --quick 通过；core channel **788 passed, 5 xfailed,
  1 failed**（唯一失败是 pre-existing 的 mechanism B `fever_state` ValueError，
  baseline 上已复现）。顺带修复了一个 pre-existing：运行
  `generate_test_manifest_report.py` 重新生成 `docs/test-manifest-summary.md`
  （新增 test_twin_run.py 注册到 core-solver/core lane）。

### Step 5 验证（2026-06-14）

- **范围收缩（诚实说明）**：roadmap 标题"耦合统一"在本次**不完整实现**。
  探索揭示两套机制（CONNECTIONS 积分环内数据流 vs CouplingEngine 步后规则
  引擎）是**不同语义**，一次性合并会破坏隐式积分语义，且 D4 自己说了
  "先用 twin-run 验证当前行为，再动耦合"。本次交付的是**统一的前置条件**：
  文档化 + 漂移清册 + 一个被证伪的假设的记录。
- **交付物**：
  - `src/engine/state_vector.py` unified_rhs docstring 扩充：明确 Gauss-Seidel
    半隐式语义、Newton 收敛原理、与 Euler CouplingEngine 的语义差异、H20 限制。
  - `src/engine/topology.py` CONNECTIONS 注释纠正（原误称 Euler 也用）：明确
    仅 Radau 路径用；列出 6+ 已知 dead routes（src_var 命名不匹配）。
  - `docs/coupling_inventory.md`（新）：两机制语义/触发/覆盖对比表；CONNECTIONS
    dead routes 清单（每条标 `file:line`）；覆盖差异矩阵（RAAS→SVR 只在
    CouplingEngine、heart.cardiac_output→kidney 只在 CONNECTIONS 等）；已知限制；
    未来真正统一的 3 个方向建议。
- **被证伪的假设（有价值）**：原计划删 Euler 的 Step 4.95 double-resolve
  （以为是 stale-signal bug）。**twin-run harness 实证否决**：删除后
  blood_loss_severe 从 PASS 翻 FAIL（GFR 误差 0.066 → 0.142）。两次 resolve
  实为**故意的 2-substep Gauss-Seidel 松弛**，Euler 数值依赖它。已回退删除，
  改为在 `simulation.py:629` 写注释记录该语义 + 实证证据。这正是 twin-run
  作为安全网的价值——防止基于错误假设改耦合。
- **CONNECTIONS dead routes 不删**：它们目前被 `if val is not None` 静默跳过 =
  无行为影响；删除会改 Radau 路径但本机 Radau 跑不了无法验证。只记录进清册，
  删除留作未来"真正统一"的工作（届时需能跑 Radau 的环境）。
- 验证：gate_check --quick 通过；**twin-run 10 场景结果与 baseline 逐字节相同**
  （IDENTICAL_TO_BASELINE，证明纯文档改动零行为影响）；core channel 仍是
  **788 passed, 5 xfailed, 1 failed**（与 Step 4 完全一致，零回归）。
- **后续**：真正的耦合统一需要 (a) 能跑 Radau 的环境、(b) 统一方向决策
  （3 个候选方向见 coupling_inventory.md）。本次的文档 + 清册是那个工程的
  前置条件。

### Step 2 验证（2026-06-14）

- 每个器官模块声明自己的 `STATE_VARS = (("ode_name", "attr_name"), ...)`
  类属性（与现有 `INPUTS`/`OUTPUTS` 契约同胞，见 `src/organs/contracts.py`）。
  11 个模块共 47 个状态变量，与原中心表完全一致。
- `src/engine/state_vector.py` 重写：`UNIFIED_MODULES` 从 3-tuple 瘦身为
  2-tuple（只剩模块名↔engine 属性映射）；`build_state_map`/`pack_state`/
  `unpack_state` 改为声明驱动（getattr/setattr 遍历 STATE_VARS），删除 ~150 行
  if/elif 链。新增 `_iter_state_modules` helper。
- heart 的 MAP 同步副作用提取为 `HeartModule._post_unpack_state()` hook，
  由 `unpack_state` 在写完该模块所有 STATE_VARS 后通过可选 hook 协议调用
  （目前仅 heart 有此 hook）。逻辑逐字搬迁，行为不变。
- **位级相同性证明**：用 `git stash` 抓 OLD pack 输出，与 NEW 做
  `np.array_equal` → **True**；state_map（47 keys）也完全相等。twin-run
  10 场景结果与 Step 5 baseline **逐字节相同**（5 PASS / 5 xfail，每个
  scenario 的 worst vital + 误差值到 6 位小数全一致）。
- 验证：gate_check --quick 通过；core channel **788 passed, 5 xfailed,
  1 failed**（与 Step 5 完全一致，零回归；唯一失败仍是 pre-existing 的
  mechanism B `fever_state`）。
- **去中心化收益**：加一个 ODE 状态变量从改 3 处（中心表 + pack if/elif +
  unpack if/elif）降为改 1 处（模块自己的 STATE_VARS）。CONNECTIONS 的 dead
  routes（跨模块耦合漂移）仍待 Phase 5 INPUTS/OUTPUTS 自动派生解决
  （见 coupling_inventory.md），本次不涉及。

### Step 3 验证（2026-06-14）

- `_step_radau` 的 ~232 行体从 `simulation.py` 抽到
  `src/engine/solvers/radau.py::run_radau_step(engine)`（模块级函数，与
  Step 1 的 state_vector / step_common 同模式）。`simulation._step_radau`
  降为瘦转发（`return _run_radau_step_fn(self)`）。
- 为容纳 `solvers/radau.py`，`src/engine/solvers.py` → `src/engine/solvers/`
  包（原文件变 `solvers/__init__.py`，零内容改动）。`SolverRegistry` 等
  公共 API 从 `__init__.py` re-export，2 个 importer
  （`simulation.py`、`test_solver_parity.py`）零改动。
- **位级相同性证明（faked-success solve_ivp）**：因本机真 Radau 跑不了
  （Python 3.14 + scipy 硬阻塞），用 monkeypatch 让 `solve_ivp` 返回确定性
  成功结果（y0 不变），驱动 `_step_radau` 的**成功路径**完整跑过
  （unpack → 5a blood factors → run_physiology_post → 8-module compute →
  coupling → disease → organ_health → history → time advance）。对比抽取
  前后 engine 关键状态（HR/MAP/CO/GFR/PO2/PCO2/sat/pH/BV/RR/fallback/
  method/hist_len）→ **identical: True**。
- 失败路径（faked-solve_ivp 失败 → fallback Euler）由 `test_solver_fallback.py`
  覆盖，全通过。`RadauSolver.step` → `engine._step_radau()` → 瘦转发链路
  经这些测试端到端验证。
- 验证：gate_check --quick 通过；core channel **788 passed, 5 xfailed,
  1 failed**（与 Step 2 完全一致，零回归；唯一失败仍是 pre-existing 的
  mechanism B `fever_state`）。
- **roadmap 全部 5 步完成**（0a-0d + 1 + 4 + 5 + 2 + 3）。剩余的"真正耦合
  统一"（Step 5 的 follow-up）与 Radau 真实验证依赖能跑 Radau 的环境，
  见 coupling_inventory.md 的后续方向。
