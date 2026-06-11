# Virtual Vet 全面架构审查报告

> **审查日期**: 2026-06-04
> **审查方法**: 4 个并行专家 agent（生理引擎架构 / 生理准确性 / 代码架构 / 代码质量与边界条件）
> **总发现数**: 82（CRITICAL ×7 / HIGH ×25 / MEDIUM ×31 / LOW ×19）

---

## 目录

- [一、CRITICAL — 必须立即修复](#一critical--必须立即修复)
- [二、HIGH — 本轮迭代必须修复](#二high--本轮迭代必须修复)
- [三、MEDIUM — 近期迭代改进](#三medium--近期迭代改进)
- [四、LOW — 持续改进](#四low--持续改进)
- [五、按来源分布](#五按来源分布)
- [六、优先修复路线图](#六优先修复路线图)

---

## 一、CRITICAL — 必须立即修复

### C1. Radau 路径功能残缺

| 字段 | 内容 |
|------|------|
| **来源** | 生理引擎专家 |
| **文件** | `src/simulation.py` — `_step_radau()` |
| **严重度** | CRITICAL |
| **分类** | ODE求解器 / 架构 |

**问题描述**：`_step_radau()` 在 Radau 积分完成后只做了解包状态→发布信号→耦合规则→疾病模块→记录历史。完全省略了 Euler 路径中的 Step 7.5（尿量失血）、Step 7.6（三室体液交换 + HH pH）、Step 7.7（血容量同步）。`fluid.compute()`、`_hh._compute_ph()`、`blood.total_volume_ml = heart.circulating_volume_ml` 均未执行。

**根因**：Radau 路径仅积分器官状态变量（heart/lung/kidney），其他 8 个模块的状态在 Radau 路径中冻结不变。Euler 和 Radau 路径本质上是两套不同的物理系统。

**影响**：使用 Radau 求解器时，pH、血容量、内分泌、免疫、凝血、淋巴、神经、肝脏、肠道完全不更新。Radau 路径模拟的是一个简化的子系统。

**修复方案**：
1. 将 fluid 状态变量（V_vascular, V_isf, V_icf）纳入统一 y 向量，使 Radau 统一积分它们
2. 或在 `_step_radau()` 中补充 fluid 计算、HH pH 计算和 blood volume sync，与 Euler 路径保持相同计算顺序

**文献依据**：多器官耦合 ODE 求解的基本要求是所有状态变量在同一积分框架内更新（Gear 1971, "Numerical Initial Value Problems in ODE"）。

---

### C2. 耦合引擎在积分后运行，隐式求解退化为显式

| 字段 | 内容 |
|------|------|
| **来源** | 生理引擎专家 |
| **文件** | `src/simulation.py` — `_step_radau()` L1065 |
| **严重度** | CRITICAL |
| **分类** | ODE求解器 / 耦合架构 |

**问题描述**：`_step_radau()` 在 Radau 积分完成后调用 `self.coupling_engine.resolve(ctx, dt)`，生成的 FactorCommands 通过 `apply_factor()` 直接修改模块属性。这意味着耦合反馈不在 Radau 的 Newton 迭代框架内——积分时使用的是上一步的耦合结果，积分完成后再叠加新耦合。

**根因**：这是显式 operator splitting，不是隐式耦合。对于 stiff 耦合系统（如 baroreflex τ=1s），显式 splitting 的稳定性限制为 Δt < 2/|λ_max|。

**影响**：耦合紧密时 Newton 迭代可能发散，baroreflex 等 stiff 系统的数值行为与 Euler 路径不一致。

**修复方案**：将耦合规则嵌入 `_unified_rhs()` 中，在每次 RHS 求值时通过 `_cached_inputs` 传递耦合信号，使 Radau 的 Newton 迭代能收敛耦合解。

**文献依据**：Marchuk 1990, "Splitting Methods" — 显式 splitting 对 stiff 系统的稳定性限制。

---

### C3. PhysiologyEngine 是死代码（560+ 行）

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `src/physiology_engine.py`（563 行） |
| **严重度** | CRITICAL |
| **分类** | 架构 / 代码质量 |

**问题描述**：`PhysiologyEngine` 在整个项目中**零引用**。所有入口点（`gui_app.py`, `cli_daemon.py`, `main.py`, 所有实验脚本, 所有测试）都使用 `from simulation import VirtualCreature`。

**根因**：项目演进过程中 PhysiologyEngine 是早期版本，VirtualCreature 是当前主力。两者功能高度重叠但实现不同。

**影响**：
- 560+ 行代码增加维护负担但不产生任何价值
- `_PARAM_PATHS` 和 `FactorCommand` 在 `physiology_engine.py` 中独立定义，与 `simulation.py` 版本存在静默漂移风险
- 开发者可能误以为 PhysiologyEngine 是可用的替代引擎而浪费时间
- `validate_parameters()` 在真实运行路径上从未执行

**修复方案**：
1. 删除 `physiology_engine.py`
2. 将 `validate_parameters()` 逻辑集成到 `VirtualCreature.step()` 中（每 N 步调用一次）
3. 将 `_PARAM_PATHS` 提取为独立模块（如 `src/param_registry.py`）

---

### C4. kidney.py: GFR 计算在 CO=0 时零除崩溃

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/kidney.py` L111 |
| **严重度** | CRITICAL |
| **分类** | 边界条件 / 数值稳定性 |

**问题描述**：`co_fraction = co_input / base_cardiac_output_ml_min(self.w)` — 当 `weight_kg=0` 时 `base_cardiac_output_ml_min(0) = 0`，ZeroDivisionError。

**根因**：无 `weight_kg > 0` 的初始化断言。

**修复方案**：
```python
co_fraction = co_input / max(base_cardiac_output_ml_min(self.w), 1e-9)
# 或在 VirtualCreature.__init__ 加：
assert body_weight_kg > 0, "body_weight_kg must be positive"
```

---

### C5. Radau 路径中 derivatives() 直接写 blood 状态

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/lung.py` L140-141, `src/kidney.py` L166, L174 |
| **严重度** | CRITICAL |
| **分类** | ODE求解器 / 数据流 |

**问题描述**：`derivatives()` 约定为纯函数（只读输入、只写 dydt/outputs dict），但 `lung.derivatives()` 直接修改 `self.blood.arterial_PO2_mmHg` 等属性，`kidney.derivatives()` 直接修改 `self.blood.bun_mg_dL` 和 `self.blood.creatinine_mg_dL`。

**根因**：在 Radau 求解中，Newton 迭代在同一 step 内多次调用 `_unified_rhs`，每次调用都会覆写 blood 状态，导致迭代过程中 blood 处于中间不一致状态。后续模块读到的 blood 状态取决于 Newton 迭代的当前轮次。

**修复方案**：将 `arterial_PO2_mmHg`/`arterial_PCO2_mmHg`/`arterial_pH`/`arterial_saturation`/`bun_mg_dL`/`creatinine_mg_dL` 放入 `outputs` dict 返回，在 `_unpack_unified_state` 或 simulation step 末尾统一写入 blood。

---

### C6. 器官健康退化乘法叠加产生非线性加速

| 字段 | 内容 |
|------|------|
| **来源** | 生理引擎专家 |
| **文件** | `src/simulation.py` L847-L857 |
| **严重度** | CRITICAL |
| **分类** | 生理准确性 / 架构 |

**问题描述**：`heart_state["cardiac_output_ml_min"] *= self.organ_health.heart_factor` 在已经包含旧 factor 的 dict 上再次相乘。如果 `heart_factor` 从 0.95 降至 0.90，CO 变为 `base_CO × 0.95 × 0.90 = base_CO × 0.855`，而非预期的 `base_CO × 0.90`。

**根因**：器官衰竭模型应为马尔可夫过程（当前帧的退化速率仅取决于当前健康状态），而非路径依赖的乘法链。

**修复方案**：将 health_factor 作为器官基线的乘数（`CO = base_CO × health_factor × contractility_factor × ...`），而非对已经包含旧 factor 的 heart_state dict 再次相乘。

**文献依据**：器官衰竭的马尔可夫过程假设 — 当前帧的退化速率仅取决于当前健康状态。

---

### C7. 事件驱动失血通过 FactorCommand 绕过保护

| 字段 | 内容 |
|------|------|
| **来源** | 生理引擎专家 |
| **文件** | `src/simulation.py` + `src/pharmacology.py` |
| **严重度** | CRITICAL |
| **分类** | 数据流 / 安全 |

**问题描述**：pharmacology.py 和 disease 模块通过 `FactorCommand(target="heart.blood_volume", op="add", value=...)` 修改血容量。但 `apply_factor()` 直接 `setattr(module, attr_name, new_value)`，绕过了 `blood_volume_change()` 中的 `max(0.0, ...)` 保护。

**根因**：FactorCommand 的 `apply_factor()` 是通用属性写入器，不区分血容量等需要特殊保护的目标。

**修复方案**：为 `heart.blood_volume` 的 FactorCommand 应用增加下限保护，或在 `apply_factor()` 中对血容量相关 target 做特殊处理。

---

## 二、HIGH — 本轮迭代必须修复

### 架构类

#### H1. FactorCommand 在 5 处重复定义，类型不等价

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `simulation.py:46`, `physiology_engine.py:50`（死代码）, `immune.py:24`, `neuro.py:18`, `coagulation.py:20`, `coupling.py:282` |
| **严重度** | HIGH |

每个模块的 `FactorCommand` 是不同类，`isinstance` 检查跨模块不工作。修改签名需要改 5+ 文件。

**修复**：在 `src/diseases/__init__.py` 或新建 `src/common_types.py` 中定义单一 `FactorCommand`，所有模块从同一位置 import。`_CouplingFactorCommand` 改为直接使用统一类（或加一个 `source` 可选字段）。

#### H2. _PARAM_PATHS 双份维护，静默漂移

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `simulation.py` (95 条目) vs `physiology_engine.py` (~87 条目) |
| **严重度** | HIGH |

两套映射表部分重叠但有不同的条目。由于 `physiology_engine.py` 是死代码，实际有效的是 `simulation.py` 版本。

**修复**：删除 `physiology_engine.py` 的 `_PARAM_PATHS`，统一使用 `simulation.py` 的版本。考虑将其提取为独立模块 `src/param_registry.py`。

#### H3. 14 模块硬编码 import，god-class 反模式

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `src/simulation.py` 顶部 import 14 个模块 |
| **严重度** | HIGH |

`VirtualCreature.__init__()` 硬编码了每个模块的创建顺序和构造参数。添加新器官模块需要修改 5 处：import 语句、`__init__()` 构造、`step()` 计算顺序、`_UNIFIED_MODULES` 列表、`_pack_unified_state()` / `_unpack_unified_state()` 的 elif 链。

**修复**：引入器官注册机制。每个模块实现标准接口，在模块的 `__init__.py` 中自注册。`VirtualCreature` 通过注册表动态创建和调度。

#### H4. BloodCompartment 是隐式共享可变状态

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `src/blood.py` + 11 个模块 |
| **严重度** | HIGH |

`BloodCompartment` 被 14 个模块引用为同一实例。模块按固定顺序执行，每个模块直接读写 `self.blood.*` 属性。没有快照、没有拷贝、没有事务边界。

**修复**：每个模块的 `compute()` 应接收输入快照、返回输出 dict，而不是直接读写共享的 blood 对象。

#### H5. CONNECTIONS 表与 coupling_rules.json 双重耦合源

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `simulation.py:181-257` + `data/coupling_rules.json` |
| **严重度** | HIGH |

模块间数据路由在两个地方定义，格式不同、维护者不同、验证方式不同。修改耦合关系时需要同时更新两个文件。

**修复**：统一为单一数据源。推荐以 `coupling_rules.json` 为唯一来源，CONNECTIONS 表从 JSON 自动生成。

### 求解器类

#### H6. _USE_DT=0.01 导致 Radau 路径时间常数偏差 10x

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/simulation.py` L1404 |
| **严重度** | HIGH |

`_unified_rhs()` 硬编码 `_USE_DT = 0.01`，所有模块的 `derivatives(dt=_USE_DT, ...)` 均使用此值。但 Radau 的实际积分步长由求解器自适应决定（rtol=1e-5, atol=1e-8）。化学感受器低通滤波的时间常数被人为加速 10 倍。

**修复**：将 `_USE_DT` 改为 `self.dt`（实际仿真步长），或明确注释说明该常量仅用于 alpha/dt 缩放且必须与物理步长一致。

#### H7. HR clamp 不一致（180 vs 250）

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/heart.py:376` vs `src/simulation.py:877` |
| **严重度** | HIGH |

baroreflex 路径使用 `self.HR_max`（180 bpm），但疾病路径 clamp 到 250 bpm。两套 clamp 逻辑独立维护。

**修复**：统一为单一常量 `HEART_RATE_CLAMP_MAX = 250.0`，两个路径都引用。

#### H8. pH clamp 范围冲突（[7.0,7.8] vs [6.8,7.8]）

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/lung.py:152` vs `src/fluid.py:95` |
| **严重度** | HIGH |

lung.py 的 pH clamp 下限 7.0 比 HH 模块的 6.8 高 0.2。当严重代谢性酸中毒使 pH<7.0 时，lung 侧会 clamp 到 7.0 但 HH 侧允许低至 6.8。

**修复**：统一为同一个常量（建议用 `HendersonHasselbalch.PH_CLAMP_MIN = 6.8`），所有模块引用同一常量。

#### H9. validate_parameters() 死代码

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/physiology_engine.py:240-284` |
| **严重度** | HIGH |

`validate_parameters()` 定义在 `PhysiologyEngine`（死代码）中，只在 `PhysiologyEngine.compute()` 内被调用。`VirtualCreature.step()` 中没有任何参数验证。

**影响**：疾病模块通过 `apply_factor()` 可能将参数推到非生理范围（如 HR=-10, pH=6.5），而 `step()` 不会检测到。

**修复**：将 `validate_parameters()` 迁移到 `VirtualCreature`，在 `step()` 开始时调用（或每 100 步调用一次以减少开销）。

### 生理准确性类

#### H10. A-a 梯度基线 10 mmHg 偏高

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/lung.py` — `_alveolar_gas_equation` |
| **严重度** | HIGH |

健康犬 A-a 梯度正常值 3-8 mmHg（West 呼吸生理学 Ch6）。当前基线 10 mmHg 导致健康肺 PaO2 系统性偏低约 5 mmHg。

**修复**：基线 A-a 梯度设为 5 mmHg（年轻健康犬），仅在高海拔/老年时升至 8-10。

#### H11. Factor VIII 缺失，aPTT 公式不完整

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/coagulation.py` L47-53, L91, L215 |
| **严重度** | HIGH |

追踪 6 个因子（VII, V, II, IX, X, XI），Factor VIII 完全缺失。aPTT 应反映内源性途径：VIII + IX + XI + XII + 共同途径。

**影响**：① 无法模拟甲型血友病（最常见凝血因子缺乏）；② aPTT 对肝脏疾病的敏感度被低估；③ DIC 时 VIII 被大量消耗，模型无法反映。

**修复**：添加 factor_VIII 追踪（半衰期 8-12h），修正 aPTT 公式。

**文献依据**：Factor VIII 由肝脏合成（血管内皮储存），半衰期 8-12 小时。

#### H12. K+ 毒性在 compute() 路径双重叠加

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/heart.py` L385, L376 |
| **严重度** | HIGH |

K+ 毒性通过 `self.hh.k_toxicity_factor` 以乘法形式叠加到 HR 上。当 baroreflex 试图通过交感兴奋升高 HR 时，高钾毒性同时以乘法抑制 HR。两个独立生理机制在模型中形成对抗。

**影响**：非生理的"僵直"行为——当 k_factor = 0.7 且交感驱动 HR+20 时，净效果仅为 HR+6。

**修复**：将 k_factor 效应改为独立通道（类似 chemoreceptor_drive），而非乘法叠加。

#### H13. GFR Starling 方程省略 πBS

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/kidney.py` — `_update_GFR` |
| **严重度** | HIGH |

当前公式：`GFR = Kf × (PGC - PBS - πGC)`，πBS（鲍曼囊胶体渗透压）= 0（未建模）。

**影响**：无法模拟肾炎 → 蛋白尿 → πBS↑ → GFR↓ 的完整病理生理链。

**修复**：添加 πBS 变量（默认 0，可由疾病/蛋白尿上调）。

**文献依据**：Guyton 肾脏生理 Ch27: GFR = Kf × (PGC - PBS - πGC + πBS)。

#### H14. Noble 浦肯野传导速度偏保守

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/noble_purkinje.py` |
| **严重度** | HIGH |

`CONDUCTION_VELOCITY_MAX = 4.0 m/s`。犬浦肯野纤维传导速度 3-5 m/s。正常值取 4.0 而非 5.0 使 PR 间期偏长（80ms vs 正常 60-80ms 的上限）。

**修复**：将 `CONDUCTION_VELOCITY_MAX` 提升至 5.0 m/s。

#### H15. A-a 梯度映射方式不准确

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/lung.py` L302 |
| **严重度** | HIGH |

`aa_gradient = 10 + (1 - DL/DL_normal) × 50`。A-a 梯度增高的原因包括 V/Q 不匹配、死腔增加、真正扩散障碍，而代码只通过 diffusion_coefficient 控制。

**修复**：增加 `shunt_fraction` 和 `dead_space_fraction` 参数，分别控制 A-a 梯度的不同组分。

#### H16. 静脉 PO2 更新公式量纲不完整

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/simulation.py` — `_update_venous_gas` |
| **严重度** | HIGH |

`venous_PO2 = max(20, 40 - 0.1 × O2_extracted)`。公式线性假设 0.1 mL O2/min 提取 = 1 mmHg PO2 下降。贫血时同样的 O2_extracted 对应更大的 SVO2 变化，公式无法反映。

**修复**：改用基于氧含量平衡的迭代求解，或至少引入 Hb 浓度校正因子。

#### H17. 毛细血管静水压未随 MAP 动态变化

| 字段 | 内容 |
|------|------|
| **来源** | 生理专家 |
| **文件** | `src/fluid.py` |
| **严重度** | HIGH |

`Pc = 25 mmHg`（固定常数）。当 MAP 因休克降至 50 mmHg 时，模型仍使用 Pc=25 mmHg，导致 NFP 不变甚至偏高。

**修复**：Pc 应与 MAP 耦合：`Pc = BASE_PC × (MAP / MAP_normal)` 或通过 autoregulation 机制调节。

#### H18. Radau 路径中尿液失血未纳入 RHS

| 字段 | 内容 |
|------|------|
| **来源** | 生理引擎专家 |
| **文件** | `src/simulation.py` — `_unified_rhs()` |
| **严重度** | HIGH |

`heart.derivatives()` 返回 `blood_volume` 导数只来自 sigmoid 连续失血模型，不包含尿量导致的失血（kidney 输出的 `blood_volume_loss_rate_mL_min`）。

**修复**：在 `_unified_rhs()` 中从 kidney outputs 读取 `blood_volume_loss_rate_mL_min`，转换为 mL/s 后叠加到 heart.derivatives 的 blood_volume 导数上。

#### H19. 血容量在 heart 和 fluid 模块间一步滞后

| 字段 | 内容 |
|------|------|
| **来源** | 生理引擎专家 |
| **文件** | `src/simulation.py` L901-L904, L938, L945 |
| **严重度** | HIGH |

heart.circulating_volume_ml 在 Step 2 被修改、Step 7.5 被进一步减少，但 `fluid.compute()` 在 Step 7.6 执行时使用的是上一步同步的 vascular_volume_ml。Step 7.7 才同步 blood.total_volume_ml。

**修复**：将 `fluid.vascular_volume_ml` 设为 `heart.circulating_volume_ml` 的直接引用（property），或在 fluid.compute() 开头同步。

#### H20. _cached_inputs 在 Newton 迭代中被隐式修改

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/simulation.py` L1516-1523 |
| **严重度** | HIGH |

每次 `_unified_rhs` 调用末尾都会 `self._cached_inputs[tgt_mod][tgt_var] = val`。Radau 求解器的 Newton 迭代在单步内多次调用 `_unified_rhs`，每次调用都会修改 `_cached_inputs`，导致后续迭代的"初始缓存"取决于之前的迭代结果。

**修复**：将 `_cached_inputs` 的修改推迟到 `_unified_rhs` 返回后（在 `_step_radau` 中处理）。

### 代码质量类

#### H21. 5 个 FactorCommand 定义违反 DRY

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | 5 个文件（见 H1） |
| **严重度** | HIGH |

详见 H1。

#### H22. _Frank_Starling() 死代码

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/heart.py:297-335` |
| **严重度** | HIGH |

`_Frank_Starling()` 方法从未被任何路径调用。`compute()` 直接内联了等效逻辑，`derivatives()` 使用独立实现。两个实现存在细微差异。

**修复**：删除 `_Frank_Starling()` 方法，或确保 compute() 调用它而非内联重复逻辑。

#### H23. 无 Noble-Purkinje / CardiacEP / Respiratory Rhythm 直接单元测试

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `tests/` 目录 |
| **严重度** | HIGH |

- 无 `test_noble_purkinje.py` — K⁺ 毒性 ECG 分期的正确性完全依赖手动验证
- 无 `test_cardiac_electrophysiology.py` — Nernst 方程、Boltzmann 稳态计算无直接验证
- 无 `test_respiratory_rhythm.py` — VdP 极限环稳定性和化学感受器响应曲线未被验证

**修复**：分别添加上述测试文件。

#### H24. BloodCompartment 承担过多职责

| 字段 | 内容 |
|------|------|
| **来源** | 架构师 |
| **文件** | `src/blood.py` |
| **严重度** | HIGH |

47 个属性中约 33 个属于其他器官系统的领域（内分泌激素 14 个、神经状态 4 个、免疫状态 6 个、凝血指标 5 个、淋巴/脾脏 3 个、药物浓度 1 个）。`BloodCompartment` 从"血液隔室"变成了"全局状态桶"。

**修复**：将非血液专属的状态迁移到对应模块。endocrine 激素存在 `EndocrineModule`，神经状态存在 `NeuroModule`，凝血状态存在 `CoagulationModule`。

#### H25. BloodCompartment 无并发保护

| 字段 | 内容 |
|------|------|
| **来源** | 程序员 |
| **文件** | `src/blood.py` |
| **严重度** | HIGH |

被 11 个模块共享读写，没有任何保护机制（如读写锁、版本快照）。当前代码在单线程下正确运行，但架构脆弱。

**修复**：在 simulation step 开始时创建 blood 快照（或使用 copy-on-write）。

---

## 三、MEDIUM — 近期迭代改进

### M1. Euler/Radau 双路径 baroreflex/MAP 计算方式不一致

**来源**：生理引擎专家

Euler 路径中 `heart.compute()` 对 MAP 使用低通滤波：`self.mean_arterial_pressure = alpha × self.mean_arterial_pressure + (1 - alpha) × raw_MAP`（alpha=0.1）。Radau 路径的 `_unpack_unified_state()` 直接赋值：`module.mean_arterial_pressure = raw_MAP`（无滤波）。

### M2. 神经/免疫/凝血/淋巴模块在 Radau 路径中完全跳过

**来源**：生理引擎专家

`_step_radau()` 不调用 `neuro.compute()`、`immune.compute()`、`coagulation.compute()`、`lymphatic.compute()`、`gut.compute()`、`liver.compute()`、`endocrine.compute()`。这些模块的状态在 Radau 路径中冻结不变。

### M3. 氧解离曲线固定参数

**来源**：生理专家

P50 = 30.0 mmHg（固定），Hill n = 2.8（固定）。酸中毒（pH 7.2）可使 P50 升至 ~34 mmHg，促进组织氧释放（Bohr 效应），但模型未体现。

**修复**：添加 P50 动态调制：`P50 = 30 + 3×(7.4-pH) + 1.5×(T-38.5)`

### M4. RAAS 与 ADH 双重调制同一参数

**来源**：生理专家

ADH_level 和 aldosterone 独立调制同一 `distal_reabsorption_fraction`。高醛固酮时尿量过度减少。

**修复**：分离 ADH 效应（直接水通道调节）和醛固酮效应（通过 Na+ 重吸收的间接水效应）。

### M5. VdP 子步进中化学反馈不实时更新

**来源**：生理引擎专家

VdP 振荡器将 dt 拆分为 n 个子步，但 `arterial_PCO2` 在子步循环中不更新——VdP 在整个子步序列中使用相同的 PCO2 值。

**修复**：在每个子步中重新计算动脉血气。

### M6. 可卡因剂量-效应使用线性假设

**来源**：生理引擎专家

`dose_ratio = dose_mg_kg / COCAINE_DOSE_MG_KG` 线性缩放效应。但可卡因的药效学存在饱和。

**修复**：使用 Hill 方程或 Emax 模型替代线性缩放。

### M7. PK 模型使用一室模型

**来源**：生理引擎专家

`self.concentration *= math.exp(-self.k * dt)` 是一室模型的消除相。许多药物有明显的分布相。

**修复**：升级为二室模型。

### M8. _pack/_unpack_unified_state 160 行 if/elif 链

**来源**：程序员

`_pack_unified_state()` 和 `_unpack_unified_state()` 通过硬编码的 if/elif 链将模块属性映射到/从 y 向量。添加新状态变量需要在两处各加一个 elif 分支。

**修复**：使用声明式映射表替代 if/elif 链。

### M9. coupling.py eval() 安全面窄

**来源**：架构师 / 程序员

`eval(rule.condition, ...)` 和 `eval(rule.fn_expr, ...)` 虽然限制了 `__builtins__`，但如果 coupling_rules.json 被篡改仍有风险。

**修复**：将表达式求值替换为 `asteval` 库或 `simpleeval`。

### M10. 凝血因子半衰期未区分

**来源**：生理专家

所有因子使用统一 decay_rate = 0.001 × dt_min。各凝血因子半衰期差异显著（VII ≈ 4-6h, II ≈ 60-72h, IX ≈ 24h）。

**修复**：为每个因子设置不同的半衰期。

### M11. 呼吸商 RQ 固定

**来源**：生理专家

`respiratory_quotient = 0.8`（固定）。DKA 时脂肪代谢主导 → RQ 应降至 0.7。

**修复**：使 RQ 与代谢状态耦合。

### M12. 肾素释放公式简化过度

**来源**：生理专家

`renin = 0.5 × MAP_deficit + 0.5 × Na_deficit`。真实肾素-血压关系是非线性 sigmoid，且缺少交感神经通路。

**修复**：使用 sigmoid 函数 + 加入 sympathetic_tone。

### M13. 肾小管水重吸收参数应用范围不当

**来源**：生理专家

TUBULAR_WATER_REABSORPTION = 0.99 作为全局乘子，同时 RAAS 又额外乘以 (1 + 0.1 × aldosterone)。醛固酮主要保钠而非直接保水。

### M14. 毛细血管静水压固定

**来源**：生理专家

Pc = 25 mmHg（固定常数）。当 MAP 因休克降至 50 mmHg 时，模型仍使用 Pc=25 mmHg。

### M15. Frank-Starling 曲线在 vol_ratio > 1.2 时封顶过于保守

**来源**：生理引擎专家

`else: target_SV = self.base_SV * 1.05`。过度输液时 SV 仅增加 5%，与 Frank-Starling 机制的生理学不符。

### M16. Starling 力使用常数 πc 而非动态计算

**来源**：生理引擎专家

`osmotic_gradient = BASE_PLASMA_COLLOID_MMHG - BASE_TISSUE_COLLOID_MMHG` 使用常数。血浆胶体渗透压实际由白蛋白浓度决定。

### M17. 双 compute() / derivatives() 路径逻辑重复

**来源**：架构师 / 程序员

heart.py, lung.py, kidney.py, immune.py, neuro.py 都有两套计算逻辑。两者的中间计算是相同的，但实现细节有微妙差异。

### M18. MAP 计算在 Euler 和 Radau 路径中不一致

**来源**：生理引擎专家

Euler 路径对 MAP 使用低通滤波，Radau 路径直接赋值。同一物理量在不同路径中有不同的动力学。

### M19. 器官健康退化在 Radau 路径中缺失

**来源**：生理引擎专家

`organ_health.track()` 在 `_step_radau()` 中被完全跳过。

### M20. history 字典手动维护

**来源**：架构师

`__init__()` 定义了 history dict 的 key 列表，`_record_history()` 向这些 key append 值，`to_minimal_snapshot()` 中读取这些 key。三处需要同步编辑。

### M21-M31

其他 MEDIUM 发现包括：
- lung.py pH clamp 范围 [7.0, 7.8] 与 HendersonHasselbalch [6.8, 7.8] 不一致
- PCO2 化学感受器驱动增益偏高
- 血氧饱和度曲线缺少年龄/品种修正
- 基础 CO 在血容量变化时未重算
- Noble 模型动作电位各期时间固定
- solve_ivp rtol/atol 设置两处不一致
- A-a 梯度公式与扩散系数耦合不区分死腔和扩散障碍
- 解剖死腔未建模
- 水通道蛋白 (AQP) 未建模
- 动脉血气初始值无稳态维持说明
- _step_euler() 330 行违反函数长度规范

---

## 四、LOW — 持续改进

### L1. 肺动脉压固定比例

PAP = MAP × 0.15（固定）。肺动脉高压（心脏worm、肺栓塞）时不准确。

### L2. 呼气/吸气时间比上限过于保守

inspiration_fraction 上限 0.55，应激呼吸可达 I:E 2:1（insp_fraction = 0.65）。

### L3. 渗透压计算公式简化

`plasma_osmolality = 2 × Na+ + 5 + 10`。常数 5 和 10 没有生理学对应物，应改为 `2 × Na+ + glucose/18 + BUN/2.8`。

### L4. VdP 振荡器初始瞬态

用余弦函数初始化 x=A, v=0（吸气峰值），跳过收敛瞬态。建议预运行 20-30 步 VdP 积分后再接入主仿真。

### L5. 凝血因子半衰期均一

详见 M10。

### L6. HCO3- 细胞内分布不完整

HCO3- 不参与 ISF↔ICF 交换。实际上 HCO3- 可通过阴离子交换体跨膜移动，缓冲细胞内 pH 变化。

### L7. 血氧饱和度曲线缺少年龄/品种修正

详见 M3 扩展。

### L8. 动脉血气初始值无稳态维持说明

详见 M17 扩展。

### L9-L19

其他 LOW 发现包括：
- coupling.py eval() 仅内置 min/max/abs，无法使用 math 函数
- coupling oscillation detection 阈值 50% 过于宽松
- Noble 模型 APD 固定相位
- 静脉 PO2 公式下限 20 mmHg 在极端休克时过于乐观
- HR 下限 40 bpm 允许高钾性心动过缓但无独立超低限保护
- GFR 下限为 0 时 RAAS 响应过强
- blood_volume=0 时 vol_ratio 除零
- 血容量为 0 时的系统行为无测试覆盖
- magic numbers 未完全提取为常量
- run_scenario() 中 `self.__init__()` 重新初始化会丢弃疾病/事件状态

---

## 五、按来源分布

### 生理引擎专家（19 发现）

| 严重度 | 数量 | 核心议题 |
|--------|------|---------|
| CRITICAL | 4 | Radau 功能残缺、耦合退化为显式、尿液失血缺失、血容量滞后 |
| HIGH | 6 | dt 解耦、双路径不等价、MAP 不一致、器官退化非马尔可夫、映射表重复 |
| MEDIUM | 6 | VdP 子步反馈缺失、A-a 简化、剂量线性饱和、PK 一室局限、Starling πc 固定 |
| LOW | 3 | VdP 瞬态、渗透压简化、振荡检测阈值 |

### 生理专家（29 发现）

| 严重度 | 数量 | 核心议题 |
|--------|------|---------|
| HIGH | 7 | Factor VIII 缺失、A-a 梯度基线偏高、K+毒性双重叠加、GFR 省略 πBS、Noble 传导速度、A-a 映射不准确、静脉 PO2 公式 |
| MEDIUM | 12 | 氧解离曲线固定、RAAS/ADH 耦合、肾素公式简化、pH 限幅、毛细管静水压固定、VdP 增益、RQ 固定等 |
| LOW | 10 | 肺动脉压比例、AQP 未建模、死腔、VdP 瞬态、渗透压公式、Hb 固定、凝血半衰期均一、APD 固定等 |

### 架构师（16 发现）

| 严重度 | 数量 | 核心议题 |
|--------|------|---------|
| CRITICAL | 1 | PhysiologyEngine 死代码 |
| HIGH | 5 | FactorCommand 重复、_PARAM_PATHS 双份、god-class import、共享可变状态、双重耦合源 |
| MEDIUM | 8 | eval 安全、双 compute 路径、手动映射、属性绕过、BloodCompartment 职责过重 |
| LOW | 2 | history 手动维护、逻辑重复 |

### 程序员（18 发现）

| 严重度 | 数量 | 核心议题 |
|--------|------|---------|
| HIGH | 7 | 类型不安全、HR clamp 不一致、pH clamp 冲突、validate_parameters 死代码、无并发保护等 |
| MEDIUM | 5 | _Frank_Starling 死代码、_cached_inputs 污染、eval 安全、pack/unpack 160 行、solve_ivp 精度不一致 |
| LOW | 4 | magic numbers、函数过长、K+ HR 下限、GFR=0 场景 |

---

## 六、优先修复路线图

### Phase 1：架构清理（消除死代码和重复）— 1-2 天

| 优先级 | 任务 | 影响范围 |
|--------|------|---------|
| P0 | 删除 `physiology_engine.py`（死代码） | 消除 560 行维护负担 + 漂移源 |
| P0 | 统一 `FactorCommand` 为单一模块 | 消除 5 处重复定义 |
| P0 | 统一 `_PARAM_PATHS` 为单一数据源 | 消除静默漂移 |
| P1 | 删除 `_Frank_Starling()` 死代码 | heart.py |
| P1 | 将 `validate_parameters()` 集成到 `VirtualCreature` | simulation.py |

### Phase 2：Radau 路径修复（恢复功能等价）— 2-3 天

| 优先级 | 任务 | 影响范围 |
|--------|------|---------|
| P0 | 修复 `_USE_DT` 与实际步长解耦 | simulation.py |
| P0 | 将 fluid 纳入 Radau 统一积分 | simulation.py + fluid.py |
| P0 | 将 derivatives() 的 blood 写入改为 outputs dict | lung.py, kidney.py |
| P1 | 将耦合引擎嵌入 `_unified_rhs()` | simulation.py + coupling.py |
| P1 | 修复 _cached_inputs 在 Newton 迭代中的隐式修改 | simulation.py |
| P1 | 在 Radau 路径末尾补充缺失的 compute() 调用 | simulation.py |
| P2 | 统一 Euler/Radau 的 MAP 计算方式 | heart.py |

### Phase 3：生理准确性 — 3-5 天

| 优先级 | 任务 | 影响范围 |
|--------|------|---------|
| P0 | 添加 Factor VIII + 修正 aPTT 公式 | coagulation.py |
| P1 | A-a 梯度基线 10→5 mmHg | lung.py |
| P1 | 添加 πBS 到 GFR Starling | kidney.py |
| P1 | 修复 K+ 毒性在 compute() 路径双重叠加 | heart.py |
| P1 | 统一 pH clamp 范围 [6.8, 7.8] | lung.py, fluid.py |
| P1 | 统一 HR clamp 为单一常量 | heart.py, simulation.py |
| P2 | 氧解离曲线 P50 动态调制 | lung.py |
| P2 | 分离 ADH/醛固酮效应 | kidney.py |
| P2 | Noble 传导速度 4.0→5.0 m/s | noble_purkinje.py |
| P2 | 毛细血管静水压随 MAP 动态变化 | fluid.py |
| P2 | 静脉 PO2 公式引入 Hb 校正 | simulation.py |
| P2 | 凝血因子半衰期区分 | coagulation.py |
| P3 | 可卡因剂量-效应升级 Hill 方程 | toxicology.py |
| P3 | PK 模型升级二室 | pharmacology.py |
| P3 | AQP 水通道建模 | kidney.py |
| P3 | 解剖死腔建模 | lung.py |

### Phase 4：测试覆盖 — 2-3 天

| 优先级 | 任务 | 影响范围 |
|--------|------|---------|
| P1 | Noble-Purkinje 直接单元测试 | tests/ |
| P1 | Cardiac Electrophysiology 直接单元测试 | tests/ |
| P1 | Respiratory Rhythm (VdP) 直接单元测试 | tests/ |
| P1 | CouplingEngine eval/lag/oscillation 直接单元测试 | tests/ |
| P1 | Lung derivatives() 纯函数测试 | tests/ |
| P2 | Radau 求解器回归测试 | tests/ |
| P2 | GFR=0 边界测试 | tests/ |
| P2 | 多器官衰竭集成测试 | tests/ |
| P2 | BloodCompartment 并发写入测试 | tests/ |
| P3 | NeuroModule 直接单元测试 | tests/ |
| P3 | 模块间数据流集成测试 | tests/ |

---

## 附录：发现索引

### 按文件

| 文件 | CRITICAL | HIGH | MEDIUM | LOW | 合计 |
|------|----------|------|--------|-----|------|
| simulation.py | 3 | 8 | 6 | 2 | **19** |
| physiology_engine.py | 1 | 1 | 0 | 0 | **2** |
| heart.py | 0 | 3 | 2 | 1 | **6** |
| lung.py | 0 | 3 | 4 | 2 | **9** |
| kidney.py | 0 | 2 | 3 | 1 | **6** |
| fluid.py | 0 | 1 | 3 | 1 | **5** |
| blood.py | 0 | 1 | 0 | 0 | **1** |
| coagulation.py | 0 | 1 | 1 | 1 | **3** |
| coupling.py | 0 | 0 | 2 | 1 | **3** |
| noble_purkinje.py | 0 | 1 | 1 | 0 | **2** |
| respiratory_rhythm.py | 0 | 0 | 1 | 1 | **2** |
| toxicology.py | 0 | 0 | 1 | 0 | **1** |
| pharmacology.py | 0 | 0 | 1 | 0 | **1** |
| endocrine.py | 0 | 0 | 0 | 0 | **0** |
| immune.py | 0 | 0 | 1 | 0 | **1** |
| neuro.py | 0 | 0 | 1 | 0 | **1** |
| organ_health.py | 0 | 0 | 0 | 0 | **0** |
| parameters.py | 0 | 0 | 0 | 0 | **0** |
| tests/ | 0 | 1 | 1 | 2 | **4** |
| data/coupling_rules.json | 0 | 1 | 0 | 0 | **1** |
| 架构（跨文件） | 1 | 3 | 3 | 1 | **8** |

### 按分类

| 分类 | CRITICAL | HIGH | MEDIUM | LOW | 合计 |
|------|----------|------|--------|-----|------|
| ODE求解器 | 2 | 3 | 2 | 0 | **7** |
| 耦合架构 | 1 | 3 | 2 | 1 | **7** |
| 架构/设计 | 1 | 5 | 3 | 1 | **10** |
| 数据流 | 1 | 2 | 1 | 0 | **4** |
| 数值稳定性 | 0 | 1 | 0 | 0 | **1** |
| 边界条件 | 0 | 2 | 2 | 4 | **8** |
| 类型安全 | 0 | 1 | 0 | 0 | **1** |
| 并发/状态管理 | 0 | 2 | 0 | 0 | **2** |
| 性能 | 0 | 0 | 2 | 0 | **2** |
| 代码质量 | 0 | 2 | 3 | 4 | **9** |
| 生理准确性 | 0 | 7 | 12 | 7 | **26** |
| 测试覆盖 | 0 | 1 | 1 | 2 | **4** |
| 参数一致性 | 0 | 0 | 1 | 0 | **1** |
