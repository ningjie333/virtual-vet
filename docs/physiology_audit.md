# 生理仿真引擎系统性审计计划

**触发**: dashboard SpO2 公式把所有正常 PaO2 映射到 100%（已修复）
**目标**: 排查同类"看起来能跑但生理学上完全错误"的 bug

## 审计维度

### 1. 氧合与呼吸 (HIGH)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| SpO2 Hill 方程 (P50=30, n=2.8) | lung.py:392 | ✅ 正确 |
| SpO2 Bohr 效应 (pH→P50) | lung.py:400-401 | ✅ 正确 |
| SpO2 温度效应 (T→P50) | lung.py:402-403 | ✅ 正确 |
| O2 content = Hb×1.34×Sat + 0.003×PO2 | blood.py:148-156 | ⚠️ Hb 硬编码 14.0 |
| Henderson-Hasselbalch pH = 6.1 + log(HCO3/0.03×PCO2) | lung.py:410-421 | ✅ 正确 |
| 肺泡气体方程 PAO2 = FiO2×(Patm-PH2O) - PaCO2/R | lung.py:221 | 待查 |

### 2. 心血管 (HIGH)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| MAP = DBP + 1/3×(SBP-DBP) | heart.py | 待查 |
| CO = HR × SV | heart.py | 待查 |
| SV 与 Frank-Starling 关系 | heart.py | 待查 |
| SVR = (MAP-CVP)/CO | heart.py | 待查 |
| pH 对心肌收缩力的影响 | heart.py:300 | 待查 |

### 3. 肾脏 (HIGH)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| GFR = Kf × (PGC - PBS - πGC) | kidney.py:282-306 | ✅ Starling 方程 |
| GFR 肾小球毛细血管压 PGC = MAP × ratio | kidney.py:295 | ✅ 正确 |
| 钠重吸收 99% + 醛固酮调节 | kidney.py:308-320 | ✅ 正确 |
| 尿量与 GFR 关系 | kidney.py:324 | 待查 |

### 4. 酸碱平衡 (HIGH)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| Henderson-Hasselbalch 公式 | lung.py:410-421 | ✅ 正确 |
| HCO3 从 fluid 模块获取 | fluid.py | 待查 |
| 代谢性酸中毒→呼吸代偿 | lung.py:274 | 待查 |

### 5. 单位转换 (MEDIUM)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| Glu mmol/L → mg/dL (×18.018) | ascii_dashboard.py | ✅ 正确 |
| Glu 在症状引擎中的单位 | clinical_signs_engine.py | 待查 |
| BUN 单位 (mg/dL) | blood.py | 待查 |
| 肌酐单位 | kidney.py | 待查 |

### 6. 钳位/截断 (MEDIUM)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| SpO2 clamp [0, 1] | lung.py:408 | ✅ 合理 |
| pH clamp [7.0, 7.8] | lung.py:421 | ⚠️ 7.0 可能太低 |
| GFR clamp ≥ 0 | kidney.py:302,306 | ✅ 合理 |
| 心率 clamp | heart.py | 待查 |
| 血压 clamp | heart.py | 待查 |

## 执行计划

**Phase 1**: 逐行审查 HIGH 项（氧合、心血管、肾脏、酸碱）
**Phase 2**: 单位转换全链路追踪
**Phase 3**: 钳位边界是否合理
**Phase 4**: 回归测试（用已知生理参数验证输出范围）

## 已修复

- [x] dashboard SpO2 线性公式 → Hill 方程 (commit 7cbac62)
