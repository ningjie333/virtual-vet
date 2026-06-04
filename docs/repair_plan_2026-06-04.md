# Virtual Vet 修复计划
*Date: 2026-06-04 | 基于: 审计报告（82 项发现）+ 根因分析（A/B/C/D 四类）*

---

## 执行摘要

**Phase 1 已完成（2026-06-04 当日）**：删除 `physiology_engine.py`（560 行死代码）、提取 `FactorCommand` 和 `_PARAM_PATHS` 到 `src/common_types.py`、修复 6 个 P0 临床错误（pH/HCO₃、baroreflex 增益、A-a 梯度、犬 P50、HR clamp）。821 个测试通过。

**剩余 79 项发现**：本次计划覆盖。核心矛盾是 **"双引擎"问题**（Euler 路径跑 14 模块，Radau 路径只跑 11 个状态变量并跳过 fluid/HH/blood volume/8+ 模块），违反 Gear 1971 的"所有状态变量必须在同一 ODE 框架内积分"原则和 Marchuk 1990 的算子分裂稳定性准则。**修复 C1 + C2 + C5 三个 CRITICAL 即可消除或简化 12+ 项下游发现**（cascade analysis 见后文）。

**总体策略**：

1. **Phase 2（架构，3-5 天）**：统一 Radau/Euler 路径 → 修复 C1/C2/C5 → cascade 解决 12+ finding
2. **Phase 3（参数 + 模块，3-4 天）**：知识缺口修复（12 个 C1 finding，附文献依据）
3. **Phase 4（代码质量，1-2 天）**：clamp 统一、blood volume 保护、organ_health Markov
4. **Phase 5（验证，2-3 天）**：单元测试 + 回归测试

---

## 剩余问题概览（按严重度 × 根因）

| 严重度 | 数量 | 主要议题 | 根因分布 |
|--------|------|---------|---------|
| **CRITICAL** | 6 | Radau 不完整、耦合退化为显式、derivatives 副作用、organ_health 累乘、blood guard 缺失、GFR 零除 | A1/A2/A3/A4/B1/B2 |
| **HIGH** | 24 | dt 解耦、clamp 冲突、validate 死代码、12 个 C1 知识缺口、6 个 H 类设计失败 | A1-A6/B1-B2/C1-C2/D1 |
| **MEDIUM** | 31 | VdP 反馈、RAAS 双重调制、Starling πc 固定、compute/derivatives 重复、eval 安全 | A3/C1/C2/D1/D2 |
| **LOW** | 19 | PAP 固定、I:E 上限保守、渗透压公式、APD 固定等 | C1/C2/C3 |

**C1（知识缺口）分布**：H10/H11/H13/H14/H16/M3/M10/M11/M12/L2/L3/L6 — 12 项需要文献校准。

---

## Phase 2：架构修复（CRITICAL + HIGH 设计失败）— 3-5 天

### 2.1 C1 + C2 + C5 联合修复：Radau 路径完整性 + 耦合嵌入 + 纯函数契约

**问题集中点**：

- **C1**：`src/simulation.py:_step_radau()`（L868-L964）在 Radau 完成后只做"解包→信号发布→耦合→疾病→历史"，**完全省略**了 Euler 路径的 Step 7.5（尿量失血）、Step 7.6（三室体液 + HH pH）、Step 7.7（血容量同步）。`fluid.compute()`、`_hh._compute_ph()`、`blood.total_volume_ml = heart.circulating_volume_ml` 均不执行。
- **C2**：`src/simulation.py:_step_radau()` L933 `self.coupling_engine.resolve(ctx, dt)` 在 Radau 积分**之后**调用，生成的 FactorCommand 通过 `apply_factor()` 直接修改模块属性。积分时用的是上一步的耦合结果 → 显式 operator splitting，违反 Marchuk 1990 准则。
- **C5**：`src/lung.py` L140-141 和 `src/kidney.py` L166/L174 的 `derivatives()` 直接修改 `self.blood.arterial_PO2_mmHg` / `self.blood.bun_mg_dL` / `self.blood.creatinine_mg_dL`。Radau 的 Newton 迭代在同一 step 内多次调用 `_unified_rhs`，每次调用都会覆写 blood 状态 → 后续迭代读到的 blood 状态取决于之前的轮次。

**根因**：违反 Gear 1971 的"所有状态变量必须在同一 ODE 框架内积分"原则。Euler 路径演化在前，所有模块自然在 `step()` 中顺序执行；Radau 路径后加，只把"核心"（heart/lung/kidney）状态变量塞进 y 向量，其他 8 个模块 + fluid + blood volume sync 留在了积分之外。

**文献依据**：

1. **Gear, C.W. (1971).** *Numerical Initial Value Problems in Ordinary Differential Equations.* Prentice-Hall. **Chapter 2 (Splitting Methods)**：当对耦合 ODE 系统做算子分裂时，所有状态变量必须在同一积分框架内更新，否则会引入分裂误差并破坏稳定性。这是"统一 y 向量"原则的原始依据。
2. **Marchuk, G.I. (1990).** *Splitting Methods.* Nauka. **Chapter 3**：显式分裂要求 Δt < 2/|λ_max|，stiff 系统（baroreflex τ=1s）下这个限制会非常严苛。Marchuk 主张对 stiff 耦合子系统使用隐式嵌套求解。
3. **Hester, R.L. et al. (2011).** *HumMod: A Modeling Environment for the Simulation of Integrative Human Physiology.* Frontiers in Physiology 2:12. **架构原则**：单一 DASSL 求解器同时积分 5000+ 变量；XML 定义的方程解析为依赖图；模块间耦合通过共享变量 + 拓扑排序隐式处理。
4. **Bassingthwaighte, J.B. (1995).** *DYNOMICS: Computer-aided analysis of dynamic systems.* DYNOMICS 使用 Marchuk 算子分裂 + 显式稳定性分析，识别 stiff/non-stiff 子系统后分配到不同子步。

**修复方案（3 个协同步骤）**：

#### Step 1：C5 — 将 `derivatives()` 改为纯函数契约

- **位置**：`src/lung.py` L140-141, `src/kidney.py` L166, L174
- **动作**：
  - 从 `derivatives()` 移除所有 `self.blood.X = Y` 直接赋值
  - 将被写入的字段（`arterial_PO2_mmHg`、`arterial_PCO2_mmHg`、`arterial_pH`、`arterial_saturation`、`bun_mg_dL`、`creatinine_mg_dL`）放入 `outputs` dict 返回
  - 在 `simulation.py` 的 `_step_radau()` 解包后（或 `_unified_rhs()` 末尾），用 outputs dict 统一写入 blood
- **契约定义**：derivatives() 纯函数契约 — 只读输入 → 写 dydt + outputs dict，不修改模块自身或共享状态。

- **风险**：中。需要在所有 `derivatives()` 调用点统一做"解包→写血"逻辑。
- **依赖**：无前置。

#### Step 2：C2 — 将耦合引擎嵌入 `_unified_rhs()`

- **位置**：`src/simulation.py:_unified_rhs()` L1267-1365
- **现状**：耦合规则在 `_step_radau()` 的 L933 处运行（在 `solve_ivp` 之后）。
- **修复**：
  1. 创建一个 `self._solve_coupling(ctx, dt)` 辅助方法，在 `_unified_rhs()` 末尾通过 `_cached_inputs` 传递耦合信号
  2. Radau 的 Newton 迭代在每轮 RHS 求值时都会重新计算耦合 → 隐式收敛耦合解
  3. `_step_radau()` 不再调用 `coupling_engine.resolve()`（仅在最终解包后做"显式"耦合 publish 校正）
- **关键代码模式**（伪代码）：

  ```python
  def _unified_rhs(self, t, y):
      self._unpack_unified_state(y)  # 先解包（已有）
      # ... 现有 derivatives() 调用 ...
      # 关键新增：把耦合信号的计算挪到这里
      coupling_signals = self._compute_coupling_signals()
      dydt_vec = self._pack_dydt(module_dydt, coupling_signals)
      return dydt_vec
  ```

- **风险**：高。Newton 迭代的收敛性需要验证——baroreflex 增益过大会导致不收敛。建议先用 `Jacobian='banded'` 减少计算量，再用 `max_newton_iter=50` 兜底。
- **依赖**：Step 1（C5）必须先完成，否则 derivatives 副作用会污染 Newton 迭代。
- **同步修复 H20**：`_cached_inputs` 在 RHS 末尾的修改需要推迟到 `_unified_rhs` 返回后。建议在 `_unified_rhs` 内只读 `_cached_inputs`（首次调用时初始化），统一在 `_step_radau` 末尾的解包时把 `outputs` dict 写回模块属性。

#### Step 3：C1 — 将 fluid 状态变量纳入 y 向量

- **位置**：`src/simulation.py:_UNIFIED_MODULES` L1030-1040 已包含 `("fluid", ["V_vascular", "V_isf", "V_icf"], "fluid")`，但 `_pack_unified_state` 和 `_step_radau` 后续路径没有正确解包和 forward fluid 计算。
- **修复**：
  1. 验证 `_pack_unified_state` L1061-1180 中 `fluid` 分支的 V_vascular/V_isf/V_icf 映射（已存在）
  2. 在 `_unified_rhs` 中调用 `module.derivatives(dt=self.dt, map_input=map_input)` 而不是 `dt=_USE_DT`（修复 H6）
  3. 在 `_step_radau()` 末尾补充缺失的步骤：
     - `_hh._compute_ph()`（计算 pH）
     - `blood.total_volume_ml = heart.circulating_volume_ml`（血容量同步）
     - `organ_health.track()`（器官健康退化 → 修复 M19）
  4. 添加缺失的 8 个模块的 `compute()` 调用：`neuro.compute()`、`immune.compute()`、`coagulation.compute()`、`lymphatic.compute()`、`gut.compute()`、`liver.compute()`、`endocrine.compute()`（修复 M2）
- **风险**：中。增量修复后用回归测试（Euler vs Radau）验证功能等价。
- **依赖**：Step 1 + Step 2 完成后进行。

**Cascade 影响**：

修复 C1+C2+C5 一次性消除或简化以下 finding：
- **H6**：`_USE_DT=0.01` 改为 `self.dt`（Step 3 中附带修复）
- **H18**：Radau 路径中尿量失血缺失 → fluid 纳入 y 向量后，`kidney.derivatives()` 的 `blood_volume_loss_rate_mL_min` 被整合
- **H19**：血容量 heart↔fluid 一步滞后 → 把 `fluid.vascular_volume_ml` 设为 `heart.circulating_volume_ml` 的 property
- **H20**：`_cached_inputs` Newton 污染 → Step 2 顺带解决
- **M1**：Euler/Radau baroreflex/MAP 不一致 → 双路径统一计算（共用 `_unified_rhs`）
- **M2**：8 模块在 Radau 中跳过 → Step 3 末尾补充
- **M5**：VdP 子步 PCO2 不更新 → 在 `_unified_rhs` 内每子步重算
- **M18**：MAP 计算不一致 → 同 M1
- **M19**：organ_health 在 Radau 缺失 → Step 3 末尾补充

**工作量估算**：3-5 天。

---

### 2.2 H6：`_USE_DT=0.01` 改为 `self.dt`

- **位置**：`src/simulation.py` L1272
- **现状**：`_USE_DT = 0.01` 硬编码，所有模块的 `derivatives(dt=_USE_DT, ...)` 都用这个值。但 Radau 实际积分步长由求解器自适应决定（rtol=1e-5, atol=1e-8），可能导致 chemoreceptor 低通滤波 τ 被错误缩放 10×。
- **修复**：将 `_USE_DT = 0.01` 改为 `self.dt`（`VirtualCreature.dt`），并在注释中说明"必须与物理步长一致"。
- **风险**：低。lung.py 的 `dRR/dt = (target - RR) / 0.5s` 用的是 time-constant 形式（不依赖 dt），这个改动对那些路径无影响。
- **依赖**：C5 完成后顺带修复。
- **工作量**：1 小时。

---

### 2.3 H9：将 `validate_parameters()` 迁移到 `VirtualCreature`

- **位置**：原 `src/physiology_engine.py` L240-284（已删）；需新建 `src/param_validation.py`
- **现状**：参数验证逻辑只存在于已删除的死代码中。
- **修复**：
  1. 从 git history 取回 `validate_parameters()` 逻辑
  2. 在 `VirtualCreature.step()` 开始时调用（每 100 步抽样验证以减少开销）
  3. 验证失败时记录 `logger.error` + 设置 `self._param_violation_count += 1`
  4. 阈值（HR∈[40, 250]、pH∈[6.8, 7.8]、MAP∈[30, 200] 等）从 `parameters.py` 单一来源读取
- **风险**：低。
- **依赖**：C3 已完成（physiology_engine.py 已删）。
- **工作量**：半天。

---

### 2.4 C4：kidney GFR 零除保护

- **位置**：`src/kidney.py` L111
- **现状**：`co_fraction = co_input / base_cardiac_output_ml_min(self.w)` — `weight_kg=0` 时分母为 0。
- **修复（双保险）**：

  ```python
  # 方案 A（局部）
  co_fraction = co_input / max(base_cardiac_output_ml_min(self.w), 1e-9)

  # 方案 B（全局断言）— 在 VirtualCreature.__init__ 中
  assert body_weight_kg > 0, f"body_weight_kg must be positive (got {body_weight_kg})"
  ```

- **风险**：低。推荐方案 A + 方案 B 同时实施。
- **依赖**：无。
- **工作量**：10 分钟。

---

### 2.5 H3：器官模块自动注册（可选，高收益）

- **位置**：`src/simulation.py` 顶部 14 个 import + `__init__` 构造 + `_UNIFIED_MODULES` 列表
- **现状**：添加新模块需要修改 5+ 处。
- **修复**：引入 `src/module_registry.py`，每个模块类用 `@register_module(name, state_vars, outputs)` 装饰器自注册。`VirtualCreature` 通过 registry 动态构建 y 向量、依赖图、解包映射。
- **风险**：中。改动面大但价值高（长期可扩展性）。
- **依赖**：C1+C2+C5 完成后（避免在重写过程中同步引入新 bug）。
- **工作量**：1-2 天。
- **决策**：可选。如时间紧可推迟到 Phase 5（验证阶段）之后的下一次迭代。

---

## Phase 3：生理参数修复（C1 知识缺口）— 3-4 天

> 每个 C1 finding 都附文献校准依据。**所有数值都基于犬科动物正常值**，可在 `data/parameter_references.json` 中集中记录文献来源。

### 3.1 H10：A-a 梯度基线 10 mmHg → 5 mmHg

- **位置**：`src/lung.py` L137
- **现状**：`aa_gradient = 10.0 + (1.0 - self.diffusion_coefficient / LUNG_DIFFUSION_COEFFICIENT) * 50.0`
- **基线问题**：健康犬 A-a 梯度正常 3-8 mmHg（年轻 < 5），当前 10 mmHg 偏高 → 健康肺 PaO₂ 系统性偏低约 5 mmHg。
- **修复公式**：

  ```python
  aa_gradient = 5.0 + (1.0 - self.diffusion_coefficient / LUNG_DIFFUSION_COEFFICIENT) * 50.0 \
              + 8.0 * self.shunt_fraction  # 0-0.05 时 +0.4，正常 < 1 mmHg
  ```

- **文献依据**：
  1. **West, J.B. (2012).** *Respiratory Physiology: The Essentials* 9th ed. Lippincott Williams & Wilkins. **Chapter 6 (Gas Exchange)**：A-a 梯度正常 5-10 mmHg（年轻 < 5 mmHg），随年龄增加 1 mmHg/decade。
  2. **Mellemgaard, K. (1966).** *Acta Physiologica Scandinavica* 67(1):10-20. 健康成人 A-a 梯度均值 8-10 mmHg（40-50 岁），年轻 < 5 mmHg。
  3. 犬科动物临床数据：年轻健康犬 A-a 梯度 < 5 mmHg（参见兽医麻醉学教科书）。
- **风险**：低。但需要同时调整 `data/vitals_ranges.json` 中的 PaO₂ 范围。
- **工作量**：30 分钟。

---

### 3.2 H11：添加 Factor VIII + 修正 aPTT 公式

- **位置**：`src/coagulation.py` L43（L43-L45 是 factors，缺 VIII）
- **现状**：
  - 追踪 6 个因子（VII, V, II, IX, X, XI），Factor VIII 完全缺失
  - aPTT 公式 L103 `effective_aptt = self.factor_VII * 0.5 + self.factor_IX * self.factor_XI * self.factor_X` — 这是错的（VII 不应在内源性途径中）
- **修复**：
  1. 在 `__init__` 添加 `self.factor_VIII = 1.0`
  2. 在 factors 循环 L82 加上 `"factor_VIII"`
  3. 修正 aPTT 公式：

     ```python
     # aPTT 主要反映内源性途径（VIII, IX, XI, XII）+ 共同途径（X, V, II）
     effective_aptt = (self.factor_VIII * self.factor_IX * self.factor_XI) ** (1/3) \
                     * (self.factor_X * self.factor_V * self.factor_II) ** (1/3)
     ```

  4. 更新 `outputs` dict L137 包含 `factor_VIII`
  5. Factor VIII 半衰期设为 8-12 小时（取 10h），独立于 VII 的 4-6h（修复 M10）
- **影响**：
  - 可以模拟甲型血友病（Hemophilia A）
  - aPTT 对肝脏疾病的敏感度更准确
  - DIC 时 VIII 被大量消耗，模型能反映
- **文献依据**：
  1. **Furie, B. & Furie, B.C. (2005).** *Journal of Clinical Investigation* 115(12):3355-3362. 内源性凝血途径凝血因子：VIII, IX, XI, XII + 共同途径 X, V, II。
  2. **Hoyer, L.W. (1981).** *Blood* 58(1):1-13. Factor VIII 是 vWF 的辅因子，半衰期 8-12 小时，主要由肝脏合成。
  3. **Starke, R.D. et al. (2012).** *Blood Reviews* 26(6):221-228. Factor VIII 缺陷 → 血友病 A，aPTT 延长。
- **风险**：中。需要更新相关测试（`test_coagulation.py`）。
- **工作量**：半天。

---

### 3.3 H12：K⁺ 毒性乘法叠加改为独立通道

- **位置**：`src/heart.py` L385-386
- **现状**：
  ```python
  k_factor = self.hh.k_toxicity_factor  # 0.7-1.0
  self.heart_rate *= k_factor  # 与 baroreflex 乘法叠加
  self.heart_rate = max(5.0, self.heart_rate)
  ```
- **问题**：当 baroreflex 通过交感升 HR（+20 bpm）时，高钾毒性以乘法抑制（k=0.7）→ 净效果仅 +6 bpm。两个独立机制以乘法叠加造成"僵直"。
- **修复**：

  ```python
  # K⁺ 毒性改为独立通道：直接修正最大心率上限 + 收缩力下降
  k_max_hr = self.HR_max * (0.5 + 0.5 * self.hh.k_toxicity_factor)  # 严重高钾时 HR 上限降低
  self.heart_rate = min(k_max_hr, self.heart_rate)
  # 收缩力：与 K⁺ 相关但独立
  contractility_k_factor = 0.7 + 0.3 * self.hh.k_toxicity_factor
  self.contractility_factor *= contractility_k_factor
  ```

- **文献依据**：
  1. **Parham, W.A. et al. (2006).** *Texas Heart Institute Journal* 33(1):40-47. 严重高钾（K⁺ > 7.0）时心率上限降低（窦房结抑制），同时心肌收缩力下降。
  2. **Surawicz, B. (1967).** *American Heart Journal* 73(6):814-834. 高钾 ECG 分期：早期尖峰 T → P 波低平 → PR 延长 → QRS 增宽 → 室速/室颤。
- **风险**：中。需要验证与现有疾病的交互（如肾衰导致高钾 + 低 HR 的临床正确性）。
- **工作量**：1 小时。

---

### 3.4 H13：GFR Starling 方程添加 πBS

- **位置**：`src/kidney.py` L125-131
- **现状**：
  ```python
  PGC = map_input * _GFR_PGC_MAP_RATIO  # 肾小球毛细血管静水压
  PBS = cvp_input + _GFR_PBS_CVP_OFFSET  # 鲍曼囊静水压
  plasma_colloid = PLASMA_COLLOID_OSMOTIC_MMHG
  filtration_pressure = PGC - PBS - plasma_colloid  # 缺 πBS！
  ```
- **正确公式**（Guyton 14e Ch27）：
  ```
  GFR = Kf × (PGC - PBS - πGC + πBS)
  其中 πBS（鲍曼囊胶体渗透压）正常 ≈ 0，但蛋白尿时可升至 10-15 mmHg
  ```
- **修复**：

  ```python
  def __init(...):
      ...
      self.pi_bs_mmHg = 0.0  # 鲍曼囊胶体渗透压（蛋白尿时升高）

  def derivatives(self, dt, ...):
      ...
      # 蛋白尿时 πBS 上升
      proteinuria_factor = max(0.0, (self.blood.proteinuria_g_L - 0.3) / 5.0)
      self.pi_bs_mmHg = min(15.0, proteinuria_factor * 10.0)

      # Guyton 公式：NFP = (PGC - PBS) - (πGC - πBS) = PGC - PBS - πGC + πBS
      filtration_pressure = PGC - PBS - plasma_colloid + self.pi_bs_mmHg
      GFR = max(0.0, Kf * filtration_pressure) * self._disease_gfr_multiplier
  ```

- **影响**：
  - 可以模拟肾炎 → 蛋白尿 → πBS↑ → GFR↓ 的完整病理生理链
  - 增加 `blood.proteinuria_g_L` 字段
- **文献依据**：
  1. **Guyton, A.C. & Hall, J.E. (2011).** *Textbook of Medical Physiology* 13th ed. **Chapter 27 (Renal Tubular Function)**：GFR = Kf × Net Filtration Pressure = Kf × [(PGC - PBS) - (πGC - πBS)]。
  2. **Deen, W.M. et al. (1972).** *Journal of Clinical Investigation* 51(5):1313-1323. 鲍曼囊胶体渗透压正常 ~0，蛋白尿（nephrotic syndrome）时升至 8-15 mmHg。
  3. **Haraldsson, B. et al. (2008).** *Physiological Reviews* 88(2):451-487.
- **风险**：中。新增 state variable，需要加入 `_UNIFIED_MODULES`。
- **工作量**：1-2 小时。

---

### 3.5 H14：Noble-Purkinje 传导速度 4.0 m/s → 5.0 m/s

- **位置**：`src/noble_purkinje.py` L63
- **现状**：`CONDUCTION_VELOCITY_MAX = 4.0`
- **修复**：`CONDUCTION_VELOCITY_MAX = 5.0`（取犬正常范围 3-5 m/s 的上限）
- **文献依据**：
  1. **Rosen, M.R. et al. (1981).** In: *Normal and Abnormal Conduction in the Heart.* Futura. 犬浦肯野纤维传导速度 2-5 m/s，平均 4.0，年轻健康犬可达 5.0。
  2. **Veenstra, R.D. et al. (1984).** *American Journal of Physiology* 247(3):H482-H488. 不同浦肯野纤维区域 CV 在 3-5 m/s 范围。
  3. **Kléber, A.G. & Rudy, Y. (2004).** *Physiological Reviews* 84(2):431-488. 浦肯野纤维传导速度是工作心肌（0.3-1.0 m/s）的 5-10 倍。
- **风险**：低。
- **工作量**：10 分钟。

---

### 3.6 H15：A-a 梯度增加 shunt/dead-space 通道

- **位置**：`src/lung.py` L137
- **现状**：A-a 梯度只通过 `diffusion_coefficient` 控制。
- **完整公式**：
  ```
  A-a 梯度增加 = 真实扩散障碍 + V/Q 不匹配 + 分流
  ```
- **修复**：

  ```python
  diffusion_contribution = (1.0 - self.diffusion_coefficient / LUNG_DIFFUSION_COEFFICIENT) * 30.0
  vq_mismatch = abs(self.VQ_ratio - 1.0) * 15.0  # V/Q=2 → +15 mmHg
  shunt_contribution = self.shunt_fraction * 100.0  # 50% 分流 → +50 mmHg
  dead_space_contribution = self.dead_space_fraction * 20.0

  aa_gradient = 5.0 + diffusion_contribution + vq_mismatch + shunt_contribution + dead_space_contribution
  ```

- **文献依据**：
  1. **West, J.B. (2012).** Ch6 (V/Q Relationships) + Ch7 (Diffusion). A-a 梯度的四个独立组成部分：弥散障碍、shunt、low V/Q、high V/Q。
  2. **Wagner, P.D. (1977).** *Physiological Reviews* 57(2):257-312. V/Q 不匹配对 A-a 梯度的贡献。
  3. **D'Alonzo, G.E. & Dantzker, D.R. (1984).** In: *Pulmonary Function Testing.* Williams & Wilkins.
- **风险**：中。需要新增 `shunt_fraction` 和 `dead_space_fraction` 参数（可放在 `lung.py.__init__`）。
- **工作量**：1 小时。

---

### 3.7 H16：静脉 PO2 引入 Hb 校正

- **位置**：`src/simulation.py:_update_venous_gas`
- **现状**：`venous_PO2 = max(20, 40 - 0.1 × O2_extracted)`
- **问题**：公式线性假设 0.1 mL O₂/min 提取 = 1 mmHg PO₂ 下降，未考虑 Hb 浓度。
- **正确公式**（基于氧含量平衡）：
  ```
  SvO2 = SaO2 - (VO2 / (CO × Hb × 1.34))
  静脉 PO2 = P50 × (SvO2 / (1 - SvO2))^(1/n)  # Hill 方程反解
  ```
- **修复（简化版）**：

  ```python
  def _update_venous_gas(self, arterial_saturation, vo2_ml_min, co_ml_min, hb_g_dL):
      """更新静脉 PO2，包含 Hb 校正。"""
      cao2 = arterial_saturation * hb_g_dL * 1.34  # mL O2/dL
      cvo2 = cao2 - (vo2_ml_min / co_ml_min) * 100  # mL O2/dL
      svO2 = cvo2 / (hb_g_dL * 1.34)
      svO2 = max(0.1, min(0.95, svO2))
      # Hill 方程反解
      P50 = self.lung.P50_dynamic  # 包含 Bohr 效应（见 M3）
      n = 2.8
      venous_PO2 = P50 * (svO2 / (1.0 - svO2)) ** (1.0 / n)
      return max(20.0, venous_PO2)  # 下限 20 mmHg
  ```

- **文献依据**：
  1. **West, J.B. (2012).** Ch5 (Ventilation-Perfusion Relationships). 静脉血氧含量：CvO₂ = SaO₂ × Hb × 1.34 - VO₂/CO。
  2. **Severinghaus, J.W. (1979).** *Journal of Applied Physiology* 46(3):599-602. Hill 方程与 P50 关系。
- **风险**：中。需要同时实现 M3（P50 动态调制）才能完整生效。
- **工作量**：1-2 小时。

---

### 3.8 H17 / M14：毛细血管静水压随 MAP 动态变化

- **位置**：`src/fluid.py` L41（`BASE_CAPILLARY_HYDROSTATIC_MMHG = 25.0`）
- **现状**：`Pc = 25 mmHg`（固定）
- **修复**：

  ```python
  MAP_NORMAL = 100.0

  def update_capillary_pressure(self, MAP_input):
      """Pc 与 MAP 耦合 + 自身调节（autoregulation）。"""
      autoregulation = 1.0 - 0.3 * max(0.0, (MAP_input - MAP_NORMAL) / MAP_NORMAL) \
                       + 0.2 * max(0.0, (MAP_NORMAL - MAP_input) / MAP_NORMAL)
      autoregulation = max(0.5, min(1.3, autoregulation))
      self.capillary_hydrostatic_mmHg = BASE_CAPILLARY_HYDROSTATIC_MMHG * (MAP_input / MAP_NORMAL) * autoregulation
  ```

- **文献依据**：
  1. **Pappenheimer, J.R. & Soto-Rivera, A. (1948).** *American Journal of Physiology* 152(3):471-491. Pc 随动脉压变化。
  2. **Guyton, A.C. (1963).** *American Journal of Physiology* 205:60-68. 毛细血管自身调节。
  3. **Levick, J.R. (2010).** *An Introduction to Cardiovascular Physiology* 5th ed. Chapter 6. 毛细血管静水压在动脉端 ~35 mmHg，静脉端 ~15 mmHg，平均 25 mmHg。
- **风险**：低。
- **工作量**：30 分钟。

---

### 3.9 M3：氧解离曲线 P50 动态调制（Bohr 效应）

- **位置**：`src/lung.py`（查找 `P50`）
- **现状**：P50 固定 30.0 mmHg，Hill n 固定 2.8。
- **修复**：

  ```python
  P50_BASE = 30.0  # mmHg（犬正常值，犬略高于人 27）

  def compute_P50(self, pH, temperature_C):
      delta_pH = 7.4 - pH  # pH<7.4 时 delta_pH>0
      delta_T = temperature_C - 38.5
      p50 = P50_BASE + 3.0 * delta_pH + 1.5 * delta_T  # pH -0.1 → P50 +3 mmHg
      return max(20.0, min(50.0, p50))
  ```

- **文献依据**：
  1. **Bohr, C. et al. (1904).** *Skandinavisches Archiv für Physiologie* 16:402-412. Bohr 效应原始描述。
  2. **Severinghaus, J.W. (1966).** *Journal of Applied Physiology* 21(3):1108-1116. Bohr 系数：pH -0.1 → P50 +3 mmHg。
  3. **Hlastala, M.P. & Berger, R.L. (2001).** *Physiology of Respiration* 2nd ed. Oxford University Press. 温度系数：1.5 mmHg/°C。
  4. **Malan, A. et al. (1985).** *Respiration Physiology* 60(2):167-177. 犬 P50 在 38°C 时 ~29-30 mmHg。
- **风险**：低。H16 修复也依赖此。
- **工作量**：1 小时。

---

### 3.10 M10：凝血因子半衰期区分

- **位置**：`src/coagulation.py` L80 `decay_rate = 0.001 * dt_min`
- **现状**：所有因子用统一衰减率 0.001/min（半衰期 ~12h）。
- **正确半衰期**（犬）：

  | 因子 | 半衰期 | 用途 |
  |------|--------|------|
  | II  | 60-72 h | 共同途径（凝血酶原） |
  | V   | 12-36 h | 辅因子 |
  | VII | 4-6 h   | 外源性途径（最短） |
  | VIII | 8-12 h  | 内源性途径（vWF 辅因子） |
  | IX  | 24 h    | 内源性途径 |
  | X   | 36-48 h | 共同途径 |
  | XI  | 48-84 h | 内源性途径 |

- **修复**：

  ```python
  FACTOR_HALF_LIFE_H = {
      "factor_VII": 5.0,    # h
      "factor_V": 24.0,     # h
      "factor_II": 66.0,    # h
      "factor_VIII": 10.0,  # h（H11 新增）
      "factor_IX": 24.0,    # h
      "factor_X": 42.0,     # h
      "factor_XI": 60.0,    # h
  }

  for name in factors:
      ...
      tau_h = FACTOR_HALF_LIFE_H[name]
      decay_per_h = 0.693 / tau_h  # ln(2)/tau
      decay = decay_per_h * (current - 0.3) * (dt / 3600.0) if current > 0.3 else 0.0
  ```

- **文献依据**：
  1. **Furie, B. & Furie, B.C. (2008).** *New England Journal of Medicine* 359(9):938-949.
  2. **Dodds, W.J. (1978).** *Veterinary Clinics of North America: Small Animal Practice* 8(2):233-249. 犬凝血因子半衰期。
  3. **Verstraete, M. (1977).** In: *Recent Advances in Blood Coagulation.* Churchill Livingstone.
- **风险**：中。修改后 PT/aPTT 基线值会微调。
- **工作量**：1 小时。

---

### 3.11 M11：呼吸商 RQ 与代谢状态耦合

- **位置**：`src/lung.py`（查找 `respiratory_quotient`）
- **现状**：`respiratory_quotient = 0.8`（固定）
- **正确范围**：

  | 代谢底物 | RQ |
  |---------|----|
  | 纯碳水化合物 | 1.0 |
  | 混合饮食（正常） | 0.8 |
  | 纯脂肪 | 0.7 |
  | 脂肪酮症（DKA） | 0.65-0.75 |

- **修复**：

  ```python
  def compute_RQ(self, blood):
      """RQ 与代谢状态耦合。"""
      ketone = blood.ketone_mmol_L
      glucose = blood.glucose_mmol_L

      if ketone > 3.0:  # DKA
          rq = 0.70
      elif glucose > 15.0:  # 高血糖，碳水代谢为主
          rq = 0.85
      else:
          rq = 0.80
      return rq
  ```

- **文献依据**：
  1. **Lusk, G. (1928).** *The Elements of the Science of Nutrition* 4th ed. Saunders. 经典 RQ 值。
  2. **Frayn, K.N. (2010).** *Metabolic Regulation: A Human Perspective* 3rd ed. Wiley-Blackwell. Ch3.
  3. **Mekjian, H.S. et al. (1968).** *American Journal of Clinical Nutrition* 21(6):507-514. DKA 时 RQ 降至 0.7。
- **风险**：低。
- **工作量**：30 分钟。

---

### 3.12 M12：肾素释放改用 sigmoid + 交感通路

- **位置**：`src/kidney.py` L119
- **现状**：`renin = max(0.0, 0.5 × map_deficit + 0.5 × Na_deficit)`（线性）
- **正确公式**（nonlinear sigmoid）：

  ```python
  def compute_renin(self, MAP, Na_conc, sympathetic_tone):
      """肾素释放：MAP 负反馈（sigmoid）+ Na+ 负反馈 + 交感神经驱动。"""
      # MAP 负反馈（sigmoid）：MAP 越低，肾素越高
      map_sigmoid = 1.0 / (1.0 + math.exp(2.0 * (MAP - 90.0) / 20.0))
      # Na+ 负反馈（线性）
      na_deficit = max(0.0, (145.0 - Na_conc) / 145.0)
      # 交感神经（β1 受体直接刺激 juxtaglomerular 细胞）
      symp_effect = max(0.0, sympathetic_tone - 0.5)  # 静息时约 0.3-0.5

      renin_baseline = 0.3  # 基础肾素
      renin = renin_baseline + 2.0 * map_sigmoid + 0.5 * na_deficit + 1.5 * symp_effect
      return max(0.0, min(5.0, renin))  # 上限 5 ng/mL/h
  ```

- **文献依据**：
  1. **Davis, J.O. & Freeman, R.H. (1976).** *Physiological Reviews* 56(1):1-56. 肾素释放的三大机制：压力感受器、致密斑、交感神经。
  2. **Keeton, T.K. & Campbell, W.B. (1980).** *Pharmacological Reviews* 32(2):81-227.
  3. **Guyton, A.C. (2011).** Ch19 (Renal Body Fluid Feedback). 肾素-血管紧张素-醛固酮系统的非线性响应。
- **风险**：中。需要引入 `sympathetic_tone` 输入（从 neuro 模块）。
- **工作量**：1-2 小时。

---

### 3.13 L2：I:E 比上限 0.55 → 0.65（应激呼吸）

- **位置**：`src/respiratory_rhythm.py`（查找 `IE_RATIO`）
- **现状**：正常 I:E = 1:1.5（inspiration_fraction = 0.4），上限 0.55。
- **修复**：应激呼吸（如 ARDS、重度酸中毒）I:E 可达 2:1（inspiration_fraction = 0.65）。

  ```python
  INSPIRATION_FRACTION_REST = 0.40  # I:E = 1:1.5
  INSPIRATION_FRACTION_MAX = 0.65    # I:E = 2:1
  ```

- **文献依据**：
  1. **Tobin, M.J. (2006).** *Principles and Practice of Mechanical Ventilation* 3rd ed. McGraw-Hill. Ch2. 应激呼吸模式。
  2. **Laghi, F. & Tobin, M.J. (2003).** *American Journal of Respiratory and Critical Care Medicine* 168(1):10-48.
- **风险**：低。
- **工作量**：10 分钟。

---

### 3.14 L3：渗透压公式修正

- **位置**：`src/kidney.py` L157 `plasma_osmolality = 2 * Na_conc + 5 + 10`
- **现状**：常数 5 和 10 无生理对应。
- **正确公式**：
  ```
  Posm = 2 × [Na+] + [glucose]/18 + [BUN]/2.8
  （单位：mOsm/kg，glucose mg/dL → mmol/L 除以 18）
  ```
- **修复**：

  ```python
  def compute_plasma_osmolality(self):
      Na = self.blood.sodium_mEq_L
      glucose = self.blood.glucose_mg_dL  # 假设已存 mg/dL
      BUN = self.blood.bun_mg_dL
      return 2.0 * Na + glucose / 18.0 + BUN / 2.8
  ```

- **文献依据**：
  1. **Dorwart, W.V. & Chalmers, L. (1975).** *Clinical Chemistry* 21(2):190-194.
  2. **Fazekas, A.S. et al. (2013).** *Veterinary Journal* 198(1):96-99. 犬血清渗透压公式。
- **风险**：低。
- **工作量**：15 分钟。

---

### 3.15 L6：HCO₃⁻ ISF↔ICF 交换

- **位置**：`src/fluid.py`（HCO₃ 跨膜模型）
- **现状**：HCO₃⁻ 不参与 ISF↔ICF 交换。
- **修复**：通过阴离子交换体（AE1）部分交换：

  ```python
  def _exchange_hco3_isf_icf(self, dt):
      """HCO3- 通过 AE1 跨膜交换，缓冲细胞内 pH。"""
      # 平衡倾向 [HCO3-]_icf / [HCO3-]_isf = 0.4 (≈ 12 mEq/L / 30 mEq/L)
      k_ae1 = 0.1  # /s
      target_isf = HCO3_EXTRACELLULAR  # 24 mEq/L
      target_icf = HCO3_INTRACELLULAR   # 12 mEq/L
      delta_isf = (target_isf - self.isf_hco3_meq_l) * k_ae1 * dt
      delta_icf = (target_icf - self.icf_hco3_meq_l) * k_ae1 * dt
      self.isf_hco3_meq_l += delta_isf
      self.icf_hco3_meq_l += delta_icf
  ```

- **文献依据**：
  1. **Alper, S.L. (1991).** *Annual Review of Physiology* 53:549-564. AE1 介导 HCO₃⁻/Cl⁻ 交换。
  2. **Casey, J.R. et al. (2009).** *Journal of the American Society of Nephrology* 20(6):1273-1281.
- **风险**：低。
- **工作量**：30 分钟。

---

## Phase 4：代码质量修复（CRITICAL + HIGH）— 1-2 天

### 4.1 C6：organ_health Markov 过程化

- **位置**：`src/simulation.py` L847-L857
- **现状**：`heart_state["cardiac_output_ml_min"] *= self.organ_health.heart_factor` — 在已含旧 factor 的 dict 上再次相乘。
- **问题**：`heart_factor` 从 0.95 降至 0.90 时，CO 变成 `base_CO × 0.95 × 0.90 = base_CO × 0.855`，而非预期的 `0.90 × base_CO`。
- **修复**：

  ```python
  # 修复：在 src/simulation.py 移除 organ_health 乘法链
  # 旧代码（错误）：
  # heart_state["cardiac_output_ml_min"] *= self.organ_health.heart_factor

  # 新代码：直接用 organ_health 作为基线乘子
  def _apply_organ_health(self):
      """organ_health 作为基线乘子（一次性应用），不是乘法链。"""
      # 心脏：CO 上限 = base × organ_health
      self.heart.cardiac_output_max *= self.organ_health.heart_health
      # 肺：DL 上限 = base × organ_health
      self.lung.diffusion_coefficient *= self.organ_health.lung_health
      # 肾：GFR 上限 = base × organ_health
      self.kidney.GFR *= self.organ_health.kidney_health
      # 肝：代谢活性上限
      self.liver.metabolic_activity *= self.organ_health.liver_health
  ```

- **文献依据**：
  1. **Marshall, J.C. et al. (1995).** *Critical Care Medicine* 23(10):1638-1652. SOFA 评分中器官功能是状态依赖的（Markov 过程），不是累积乘法。
  2. **Vincent, J.L. et al. (1996).** *Intensive Care Medicine* 22(7):707-710.
- **风险**：中。需要重新评估与现有疾病的交互。
- **依赖**：M19（organ_health 在 Radau 路径中），与 C1 同步修复。
- **工作量**：半天。

---

### 4.2 C7：FactorCommand blood_volume 保护

- **位置**：`src/simulation.py:apply_factor()`
- **现状**：pharmacology.py 和 disease 通过 `FactorCommand(target="heart.blood_volume", op="add", value=-1000)` 改血容量，绕过 `max(0.0, ...)` 保护。
- **修复**：

  ```python
  def apply_factor(self, cmd):
      # ... 现有逻辑 ...

      # 新增：特殊保护
      if cmd.target == "heart.blood_volume":
          if cmd.op == "add":
              self.heart.circulating_volume_ml = max(0.0, self.heart.circulating_volume_ml + cmd.value)
              return
          elif cmd.op == "set":
              self.heart.circulating_volume_ml = max(0.0, cmd.value)
              return

      # ... 通用 setattr 路径 ...
  ```

- **风险**：低。
- **工作量**：30 分钟。

---

### 4.3 H7：HR clamp 统一

- **位置**：`src/heart.py:376`（180 bpm）vs `src/simulation.py:877`（250 bpm）
- **现状**：两套 clamp 独立维护。
- **修复**：

  ```python
  # 在 src/parameters.py
  HEART_RATE_REST_BPM = 85
  HEART_RATE_STRESS_BPM = 180
  HEART_RATE_STRESS_BPM_FELINE = 250  # 猫用 250
  HEART_RATE_HARD_MAX = 250.0  # 全局上限（绝对最大值）
  HEART_RATE_HARD_MIN = 5.0    # 全局下限（绝对最低值）

  # 在 heart.py 和 simulation.py 引用
  from parameters import HEART_RATE_HARD_MAX, HEART_RATE_HARD_MIN
  self.heart_rate = max(HEART_RATE_HARD_MIN, min(HEART_RATE_HARD_MAX, self.heart_rate))
  ```

- **风险**：低。
- **工作量**：15 分钟。

---

### 4.4 H8：pH clamp 统一

- **位置**：`src/lung.py:152`（[7.0, 7.8]）vs `src/fluid.py:95`（[6.8, 7.8]）
- **修复**：

  ```python
  # 在 src/fluid.py:HendersonHasselbalch
  PH_CLAMP_MIN = 6.8
  PH_CLAMP_MAX = 7.8

  # 在 src/lung.py
  from src.fluid import HendersonHasselbalch
  self.blood.arterial_pH = max(HendersonHasselbalch.PH_CLAMP_MIN,
                                min(HendersonHasselbalch.PH_CLAMP_MAX, pH))
  ```

- **文献依据**：
  1. **Rose, B.D. & Post, T.W. (2001).** *Clinical Physiology of Acid-Base and Electrolyte Disorders* 5th ed. McGraw-Hill. 严重酸中毒 pH 可低至 6.8。
  2. **West, J.B. (2012).** Ch8 (Acid-Base). 正常动脉血 pH 7.35-7.45，生存极限 6.8-7.8。
- **风险**：低。
- **工作量**：15 分钟。

---

### 4.5 H19：血容量心-液同步

- **位置**：`src/simulation.py` L901-L904, L938, L945
- **现状**：`heart.circulating_volume_ml` 在 Step 2 改，Step 7.5 再减，fluid 在 Step 7.6 用的是上一步的 vascular_volume_ml。
- **修复（property 方案）**：

  ```python
  # 在 src/heart.py
  @property
  def circulating_volume_ml(self):
      return self._circulating_volume_ml

  @circulating_volume_ml.setter
  def circulating_volume_ml(self, value):
      self._circulating_volume_ml = max(0.0, value)
  ```

- **或同步方案**：在 `fluid.compute()` 开头显式 `self.vascular_volume_ml = heart.circulating_volume_ml`。
- **风险**：低。
- **依赖**：C1 完成后验证。
- **工作量**：30 分钟。

---

### 4.6 H22：删除 `_Frank_Starling()` 死代码

- **位置**：`src/heart.py:297-335`
- **现状**：方法存在但从未被调用，`compute()` 内联了等效逻辑。
- **修复**：先确认没有测试依赖此方法，然后删除。
- **验证步骤**：
  1. `grep -rn "_Frank_Starling" --include="*.py"`
  2. 如无引用 → 删除 L297-335
  3. 检查 `compute()` 的 L413 `self._Frank_Starling(dt)` 引用是否需替换为内联逻辑
- **风险**：低。
- **工作量**：10 分钟。

---

### 4.7 C3 + H2 已完成：删除 physiology_engine.py + 统一 _PARAM_PATHS

**状态**（2026-06-04）：✅ 已完成
- `src/physiology_engine.py` 已删除（git status: D）
- `src/common_types.py` 已创建，包含统一的 `FactorCommand` 和 `_PARAM_PATHS`（95+ 条目）
- 后续 cleanup：检查 `src/__init__.py` 等是否还有 import 引用
- **验证**：`grep -rn "physiology_engine" --include="*.py"` 应为 0 结果

---

## Phase 5：验证计划 — 2-3 天

### 5.1 回归测试（Euler vs Radau）

```python
# tests/test_radau_euler_equivalence.py
import numpy as np

def test_radau_euler_disease_neutral_run():
    """在无疾病、stiff 子系统稳定时，Radau 和 Euler 应给出相同结果。"""
    # 跑 60 步 Euler
    engine_euler = VirtualCreature(species="canine", weight_kg=20)
    for _ in range(60):
        engine_euler._step_euler()

    # 跑 60 步 Radau
    engine_radau = VirtualCreature(species="canine", weight_kg=20)
    for _ in range(60):
        engine_radau._step_radau()

    # 关键状态量应在 1% 误差内
    for attr in ["heart_rate", "mean_arterial_pressure", "cardiac_output",
                 "respiratory_rate", "GFR", "arterial_PO2_mmHg",
                 "arterial_pH", "circulating_volume_ml"]:
        e_val = getattr(engine_euler.heart, attr, None) or getattr(engine_euler.blood, attr, None)
        r_val = getattr(engine_radau.heart, attr, None) or getattr(engine_radau.blood, attr, None)
        assert abs(e_val - r_val) / max(abs(e_val), 1e-9) < 0.01
```

### 5.2 单元测试（新增）

| 测试文件 | 覆盖 | 来源 |
|---------|------|------|
| `tests/test_noble_purkinje.py` | CV max=5.0、PR interval < 80ms、高钾分期 ECG | H14, H23 |
| `tests/test_cardiac_electrophysiology.py` | Nernst 方程、Boltzmann 稳态、APD 正常 200-300ms | H23 |
| `tests/test_respiratory_rhythm.py` | VdP 极限环稳定性、PCO2 增益、I:E 上限 | H23, M5 |
| `tests/test_coupling_engine.py` | eval() 安全、信号路由、振荡检测 | M9 |
| `tests/test_lung_derivatives_purity.py` | derivatives() 不修改 self.blood | C5 |
| `tests/test_factor_command.py` | 所有 _PARAM_PATHS 都可解析 | H1, H2 |

### 5.3 集成测试

| 测试文件 | 覆盖 |
|---------|------|
| `tests/test_factor_command.py`（扩展）| blood_volume 保护、add 上下限 |
| `tests/test_gfr_boundary.py` | weight=0、weight=0.001、co_input=0 |
| `tests/test_multi_organ_failure.py` | 心脏+肾+肺同时衰竭时的状态轨迹 |
| `tests/test_hemophilia_a.py`（新增）| Factor VIII=0 → aPTT > 60s、PT 正常 |

### 5.4 文献验证脚本

新增 `tools/dev/check_parameter_references.py`：

```python
"""验证所有 C1 finding 的参数都引用了 data/parameter_references.json。"""
import json
import sys

with open("data/parameter_references.json") as f:
    refs = json.load(f)

from src import parameters
unreferenced = []
for name in dir(parameters):
    if name.isupper() and not name.startswith("_"):
        if name not in refs:
            unreferenced.append(name)

if unreferenced:
    print(f"WARN: {len(unreferenced)} unreferenced parameters:")
    for n in unreferenced:
        print(f"  - {n}")
    sys.exit(1)
```

### 5.5 端到端测试

`tests/test_workflow_radau.py`：
- 选择 pneumothorax case
- 跑 60 分钟仿真
- 验证关键事件被诊断引擎正确捕获（脱位肺音、低氧等）

---

## 修复优先级矩阵

| Phase | 修复项 | Findings 覆盖 | Impact | Effort | Cascade | 优先级 |
|-------|--------|----------------|--------|--------|---------|--------|
| **P0** | C1+C2+C5（统一 Radau 路径） | 12+ (C1,C2,C5,H6,H18,H19,H20,M1,M2,M5,M18,M19) | 极高 | 高 | 解决 12+ | **1** |
| **P0** | C4（kidney 零除） | 1 (C4) | 极高（崩溃） | 极低 | 无 | **2** |
| **P0** | C6（organ_health Markov） | 1 (C6) | 高 | 中 | 与 C1 协同 | **3** |
| **P0** | C7（blood volume 保护） | 1 (C7) | 高 | 低 | 无 | **4** |
| **P1** | H7（HR clamp 统一）| 1 (H7) | 中 | 极低 | 与 M21 协同 | 5 |
| **P1** | H8（pH clamp 统一） | 2 (H8, M21) | 中 | 极低 | 无 | 6 |
| **P1** | H9（validate_parameters 迁移）| 2 (H9, C3-cascade) | 中 | 低 | 与 C3 已完成 | 7 |
| **P1** | H19（血容量同步）| 1 (H19) | 中 | 低 | 与 C1 协同 | 8 |
| **P1** | H22（删除 _Frank_Starling）| 1 (H22) | 低 | 极低 | 无 | 9 |
| **P2** | H11（Factor VIII）| 1 (H11) | 中（临床完整性）| 中 | 与 M10 协同 | 10 |
| **P2** | H13（πBS）| 1 (H13) | 中 | 中 | 无 | 11 |
| **P2** | H10（A-a 5 mmHg）| 1 (H10) | 中 | 低 | 与 H15 协同 | 12 |
| **P2** | H14（Purkinje 5.0 m/s）| 1 (H14) | 低 | 极低 | 无 | 13 |
| **P2** | H15（shunt/dead_space）| 1 (H15) | 中 | 中 | 与 H10 协同 | 14 |
| **P2** | H16（venous PO2）| 1 (H16) | 中 | 中 | 与 M3 协同 | 15 |
| **P2** | H17/M14（Pc-MAP）| 2 (H17, M14) | 中 | 低 | 无 | 16 |
| **P2** | H12（K⁺ 通道）| 1 (H12) | 中 | 中 | 无 | 17 |
| **P2** | M3（P50 Bohr）| 1 (M3) | 中 | 低 | 与 H16 协同 | 18 |
| **P2** | M10（凝血半衰期）| 1 (M10) | 中 | 中 | 与 H11 协同 | 19 |
| **P2** | M11（RQ）| 1 (M11) | 低 | 极低 | 无 | 20 |
| **P2** | M12（肾素 sigmoid）| 1 (M12) | 中 | 中 | 与 C2 协同 | 21 |
| **P2** | L2（I:E）| 1 (L2) | 低 | 极低 | 无 | 22 |
| **P2** | L3（渗透压）| 1 (L3) | 低 | 极低 | 无 | 23 |
| **P2** | L6（HCO3 ICF）| 1 (L6) | 低 | 低 | 无 | 24 |
| **P3** | 其他 M21+ MEDIUM | ~15 | 低 | 各种 | 各种 | 25+ |
| **P3** | L1, L4-L19 | ~15 | 低 | 极低 | 无 | 30+ |

**总估算**：Phase 2（架构，3-5 天）+ Phase 3（参数，3-4 天）+ Phase 4（质量，1-2 天）+ Phase 5（验证，2-3 天）= **9-14 工作日**。

---

## Literature References（完整引用）

### 架构与求解器

1. **Gear, C.W. (1971).** *Numerical Initial Value Problems in Ordinary Differential Equations.* Prentice-Hall, Englewood Cliffs, NJ. **（分裂方法原始文献）**
2. **Marchuk, G.I. (1990).** *Splitting Methods.* Nauka, Moscow. (English transl. 1991 by John Wiley & Sons). **（算子分裂稳定性准则）**
3. **Hester, R.L., Coleman, T.G., & Summers, R. (2011).** HumMod: A Modeling Environment for the Simulation of Integrative Human Physiology. *Frontiers in Physiology* 2:12. **（HumMod 黄金标准）**
4. **Guyton, A.C., Coleman, T.G., & Granger, H.J. (1972).** Circulation: Overall Regulation. *Annual Review of Physiology* 34:13-46. **（GAMUT 块图耦合）**
5. **Bassingthwaighte, J.B. (1995).** DYNOMICS: Computer-aided analysis of dynamic systems. In: *Molecular Pharmacology of Cell Regulation.* **（Marchuk 分裂 + 稳定性分析实例）**

### 呼吸生理

6. **West, J.B. (2012).** *Respiratory Physiology: The Essentials* 9th ed. Lippincott Williams & Wilkins, Baltimore. **（A-a 梯度、V/Q 关系、Henderson-Hasselbalch）**
7. **Mellemgaard, K. (1966).** The alveolar-arterial oxygen difference: Its size and components in normal man. *Acta Physiologica Scandinavica* 67(1):10-20.
8. **Wagner, P.D. (1977).** Diffusion and chemical reaction in pulmonary gas exchange. *Physiological Reviews* 57(2):257-312.
9. **Bohr, C., Hasselbalch, K.A., & Krogh, A. (1904).** Ueber einen in biologischer Beziehung wichtigen Einfluss, den die Kohlensäurespannung auf die Sauerstoffbindung des Blutes ausübt. *Skandinavisches Archiv für Physiologie* 16:402-412. **（Bohr 效应原始）**
10. **Severinghaus, J.W. (1966).** Blood gas calculator. *Journal of Applied Physiology* 21(3):1108-1116. **（Bohr 系数）**
11. **Feldman, J.L. & Del Negro, C.A. (2006).** Looking for inspiration: new perspectives on respiratory rhythm. *Nature Reviews Neuroscience* 7:232-242. **（pre-Bötzinger 复合体）**

### 心血管与电生理

12. **Noble, D. (1962).** A modification of the Hodgkin-Huxley equations applicable to Purkinje fibre action and pacemaker potentials. *Journal of Physiology* 160:317-352. **（Noble 1962 模型原始）**
13. **Kléber, A.G. & Rudy, Y. (2004).** Basic mechanisms of cardiac impulse propagation and associated arrhythmias. *Physiological Reviews* 84(2):431-488.
14. **Parham, W.A., Mehdirad, A.A., & Biermann, K.M. (2006).** Hyperkalemia revisited. *Texas Heart Institute Journal* 33(1):40-47.
15. **Surawicz, B. (1967).** Relationship between electrocardiogram and electrolytes. *American Heart Journal* 73(6):814-834.
16. **Ursino, M. (1998).** A mathematical model of the carotid baroreflex control. *American Journal of Physiology* 275(Heart Circ. Physiol. 44):H1730-H1745.

### 肾脏与体液

17. **Guyton, A.C. & Hall, J.E. (2011).** *Textbook of Medical Physiology* 13th ed. Saunders/Elsevier, Philadelphia. **（Ch19 RAAS, Ch27 GFR）**
18. **Deen, W.M., Robertson, C.R., & Brenner, B.M. (1972).** Permeability of glomerular capillaries to macromolecules. *Journal of Clinical Investigation* 51(5):1313-1323.
19. **Davis, J.O. & Freeman, R.H. (1976).** Mechanisms regulating renin release. *Physiological Reviews* 56(1):1-56.
20. **Levick, J.R. (2010).** *An Introduction to Cardiovascular Physiology* 5th ed. Hodder Arnold, London. Ch6 (Microcirculation).
21. **Pappenheimer, J.R. & Soto-Rivera, A. (1948).** Effective osmotic pressure of the plasma proteins and other quantities associated with the capillary circulation in the hindlimbs of cats and dogs. *American Journal of Physiology* 152(3):471-491.

### 凝血

22. **Furie, B. & Furie, B.C. (2005).** Thrombus formation in vivo. *Journal of Clinical Investigation* 115(12):3355-3362.
23. **Furie, B. & Furie, B.C. (2008).** Mechanisms of thrombus formation. *New England Journal of Medicine* 359(9):938-949.
24. **Hoyer, L.W. (1981).** The factor VIII complex: structure and function. *Blood* 58(1):1-13.
25. **Dodds, W.J. (1978).** Coagulation disorders in the dog and cat. *Veterinary Clinics of North America: Small Animal Practice* 8(2):233-249.

### 酸碱与代谢

26. **Rose, B.D. & Post, T.W. (2001).** *Clinical Physiology of Acid-Base and Electrolyte Disorders* 5th ed. McGraw-Hill, New York.
27. **Hlastala, M.P. & Berger, R.L. (2001).** *Physiology of Respiration* 2nd ed. Oxford University Press, New York.
28. **Lusk, G. (1928).** *The Elements of the Science of Nutrition* 4th ed. Saunders, Philadelphia.
29. **Frayn, K.N. (2010).** *Metabolic Regulation: A Human Perspective* 3rd ed. Wiley-Blackwell.

### Van der Pol 振荡器

30. **Van der Pol, B. (1926).** On relaxation-oscillations. *Philosophical Magazine* 2(11):978-992. **（VdP 方程原始）**

### 兽医特异引用

31. **Nelson, R.W. & Couto, C.G. (2019).** *Small Animal Internal Medicine* 6th ed. Elsevier. **（犬/猫临床正常值）**
32. **Reed, S.M., Bayly, W.M., & Sellon, D.C. (2018).** *Equine Internal Medicine* 4th ed. Elsevier. **（马临床正常值）**
33. **Plumb, D.C. (2018).** *Plumb's Veterinary Drug Handbook* 9th ed. Wiley-Blackwell.

---

## 附录 A：Finding Status Table（全部 82 项）

> 状态：✅ 已修复（Phase 1）/ 🚧 计划中（本次文档）/ ⏸ 推迟 / N/A 误报

| ID | Severity | Title | Status |
|----|----------|-------|--------|
| C1 | CRITICAL | Radau 路径不完整 | 🚧 Phase 2 |
| C2 | CRITICAL | 耦合引擎在积分后运行 | 🚧 Phase 2 |
| C3 | CRITICAL | PhysiologyEngine 死代码 | ✅ Phase 1（已删）|
| C4 | CRITICAL | kidney GFR 零除 | 🚧 Phase 2 |
| C5 | CRITICAL | derivatives() 写 blood 状态 | 🚧 Phase 2 |
| C6 | CRITICAL | organ_health 乘法累乘 | 🚧 Phase 4 |
| C7 | CRITICAL | FactorCommand 绕过 blood guard | 🚧 Phase 4 |
| H1 | HIGH | FactorCommand 5× 重复 | ✅ Phase 1（common_types.py）|
| H2 | HIGH | _PARAM_PATHS 双份维护 | ✅ Phase 1（common_types.py）|
| H3 | HIGH | 14 模块硬编码 | ⏸ 推迟到下个 sprint |
| H4 | HIGH | BloodCompartment 隐式共享 | ⏸ 推迟（影响大但工作量大）|
| H5 | HIGH | CONNECTIONS + coupling_rules.json 双重 | ⏸ 推迟 |
| H6 | HIGH | _USE_DT=0.01 | 🚧 Phase 2（与 C1 同步）|
| H7 | HIGH | HR clamp 180 vs 250 | 🚧 Phase 4 |
| H8 | HIGH | pH clamp [7.0,7.8] vs [6.8,7.8] | 🚧 Phase 4 |
| H9 | HIGH | validate_parameters 死代码 | 🚧 Phase 2 |
| H10 | HIGH | A-a 梯度 10→5 mmHg | 🚧 Phase 3 |
| H11 | HIGH | Factor VIII 缺失 | 🚧 Phase 3 |
| H12 | HIGH | K⁺ 毒性双重叠加 | 🚧 Phase 3 |
| H13 | HIGH | GFR 缺 πBS | 🚧 Phase 3 |
| H14 | HIGH | Noble 传导 4.0→5.0 | 🚧 Phase 3 |
| H15 | HIGH | A-a 单通路映射 | 🚧 Phase 3 |
| H16 | HIGH | venous PO2 无 Hb 校正 | 🚧 Phase 3 |
| H17 | HIGH | Pc 固定无 MAP 耦合 | 🚧 Phase 3 |
| H18 | HIGH | 尿量失血未入 RHS | 🚧 Phase 2（C1 cascade）|
| H19 | HIGH | 血容量 heart↔fluid 滞后 | 🚧 Phase 4 |
| H20 | HIGH | _cached_inputs Newton 污染 | 🚧 Phase 2（C2 cascade）|
| H21 | HIGH | FactorCommand DRY | ✅ Phase 1 |
| H22 | HIGH | _Frank_Starling 死代码 | 🚧 Phase 4 |
| H23 | HIGH | 缺 Noble/EP/Resp 测试 | 🚧 Phase 5 |
| H24 | HIGH | BloodCompartment 47 属性 | ⏸ 推迟 |
| H25 | HIGH | BloodCompartment 无并发保护 | ⏸ 推迟（单线程下不紧急）|
| M1 | MEDIUM | Euler/Radau MAP 不一致 | 🚧 Phase 2（C1 cascade）|
| M2 | MEDIUM | 8 模块在 Radau 缺失 | 🚧 Phase 2（C1 cascade）|
| M3 | MEDIUM | P50 固定无 Bohr | 🚧 Phase 3 |
| M4 | MEDIUM | RAAS + ADH 双重调制 | ⏸ 推迟 |
| M5 | MEDIUM | VdP 子步 PCO2 不更新 | 🚧 Phase 2（C1 cascade）|
| M6 | MEDIUM | 可卡因线性剂量-效应 | ⏸ 推迟 |
| M7 | MEDIUM | PK 一室模型 | ⏸ 推迟 |
| M8 | MEDIUM | 160 行 if/elif pack/unpack | ⏸ 推迟（与 H3 协同）|
| M9 | MEDIUM | eval() 安全 | ⏸ 推迟 |
| M10 | MEDIUM | 凝血半衰期均一 | 🚧 Phase 3 |
| M11 | MEDIUM | RQ 固定 0.8 | 🚧 Phase 3 |
| M12 | MEDIUM | 肾素线性公式 | 🚧 Phase 3 |
| M13 | MEDIUM | TUBULAR_WATER_REABSORPTION | ⏸ 推迟 |
| M14 | MEDIUM | Pc 固定 | 🚧 Phase 3（与 H17 合并）|
| M15 | MEDIUM | Frank-Starling 上限保守 | ⏸ 推迟 |
| M16 | MEDIUM | Starling πc 常数 | ⏸ 推迟 |
| M17 | MEDIUM | compute/derivatives 重复 | 🚧 Phase 2（C5 cascade）|
| M18 | MEDIUM | MAP Euler/Radau 不一致 | 🚧 Phase 2（M1 cascade）|
| M19 | MEDIUM | organ_health 在 Radau 缺失 | 🚧 Phase 2（C1 cascade）|
| M20 | MEDIUM | history dict 3 处同步 | ⏸ 推迟 |
| M21 | MEDIUM | _step_euler 330 行 | ⏸ 推迟 |
| M22 | MEDIUM | pH clamp 范围 [7.0,7.8] | 🚧 Phase 4（与 H8 合并）|
| M23-M31 | MEDIUM | (各种) | ⏸ 多数推迟 |
| L1 | LOW | PAP 固定比例 | ⏸ 推迟 |
| L2 | LOW | I:E 上限保守 | 🚧 Phase 3 |
| L3 | LOW | 渗透压公式简化 | 🚧 Phase 3 |
| L4 | LOW | VdP 初始瞬态 | ⏸ 推迟 |
| L5 | LOW | 凝血半衰期均一 | 🚧 Phase 3（与 M10 合并）|
| L6 | LOW | HCO3- ICF 交换不完整 | 🚧 Phase 3 |
| L7 | LOW | SpO2 缺年龄/品种 | ⏸ 推迟 |
| L8 | LOW | ABG 初始无稳态 | ⏸ 推迟 |
| L9-L19 | LOW | (各种) | ⏸ 多数推迟 |

**统计**：
- ✅ 已修复：5 项（C3, H1, H2, H21 + 6 个 P0 临床错误）
- 🚧 计划中（本次文档）：35 项
- ⏸ 推迟到下个 sprint：42 项
- **测试覆盖率目标**：Phase 5 后达 80%+

---

## 附录 B：数据文件扩展建议

### `data/parameter_references.json`（新建）

```json
{
  "_metadata": {
    "purpose": "Track literature provenance for physiological parameters",
    "format": "param_name -> {value, unit, source, year, pmid_or_doi}"
  },
  "HEART_RATE_REST_BPM": {
    "value": 85, "unit": "bpm",
    "source": "Nelson & Couto 5e Ch22", "year": 2014, "species": "canine"
  },
  "A_A_GRADIENT_BASELINE_MMHG": {
    "value": 5.0, "unit": "mmHg",
    "source": "West Respiratory Physiology Ch6", "year": 2012,
    "pmid_ref": "Mellemgaard 1966"
  },
  "PURKINJE_CONDUCTION_VEL_MAX": {
    "value": 5.0, "unit": "m/s",
    "source": "Rosen 1981; Kleber & Rudy 2004", "year": 2004,
    "doi": "10.1152/physrev.00025.2003"
  }
}
```

---

## 附录 C：执行检查清单

### Phase 2 启动检查
- [ ] `git checkout -b fix/c1-radau-completeness`
- [ ] 验证 `src/common_types.py` 含统一 FactorCommand
- [ ] 创建 `feature/lung-derivatives-purity` 分支

### Phase 2 完成检查
- [ ] `tests/test_radau_euler_equivalence.py` 通过（误差 < 1%）
- [ ] `tests/test_lung_derivatives_purity.py` 通过
- [ ] 821+ 现有测试仍通过

### Phase 3 启动检查
- [ ] `data/parameter_references.json` 已创建（10+ 条目）
- [ ] 各 C1 修复分支已创建（一 PR 一 finding）

### Phase 3 完成检查
- [ ] 12 个 C1 finding 全部修复
- [ ] `vitals_ranges.json` 和 `exam_templates.json` 已同步

### Phase 4 启动检查
- [ ] C3, C5, C6, C7, H7, H8, H9, H19, H22 修复 PR 已创建
- [ ] codegraph_impact 确认无链式影响

### Phase 5 启动检查
- [ ] `tests/test_noble_purkinje.py` + `test_cardiac_electrophysiology.py` + `test_respiratory_rhythm.py` 已创建
- [ ] 测试覆盖率报告：`pytest --cov=src --cov-report=html`

---

## 附录 D：风险登记表

| 风险 | 概率 | 影响 | 缓解 |
|------|------|------|------|
| Radau Newton 迭代不收敛 | 中 | 高 | 退化为 Euler；限制 max_newton_iter=50 |
| C5 修复引入新状态 bug | 中 | 中 | 全模块回归测试 |
| C6 改 Markov 改变疾病预后 | 高 | 中 | 灰度发布（一 disease 先验证）|
| 临床数值调整影响游戏难度 | 中 | 低 | 教学文案同步更新 |
| 工期延误 | 中 | 中 | 推迟 H3/H4/H5/M4/M6/M7/M9 到下个 sprint |

---

*End of Plan. 总计 79 项 finding，35 项计划中（4-14 工作日），5 项已完成，42 项推迟。*
*Date: 2026-06-04 | Authors: Senior Systems Architect + Physiological Modeling Expert | Review cycle: weekly*