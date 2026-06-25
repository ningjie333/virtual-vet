# 生理仿真引擎系统性审计

**触发**: dashboard SpO2 公式把所有正常 PaO2 映射到 100%（已修复）
**目标**: 排查同类"看起来能跑但生理学上完全错误"的 bug

## Phase 1 审计结果

### 1. 氧合与呼吸

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| SpO2 Hill 方程 (P50=30, n=2.8) | lung.py:392 | ✅ 正确 |
| SpO2 Bohr 效应 (pH→P50) | lung.py:400-401 | ✅ 正确 |
| SpO2 温度效应 (T→P50) | lung.py:402-403 | ✅ 正确 |
| O2 content = Hb×1.34×Sat + 0.003×PO2 | blood.py:148-156 | ✅ 已修复 (HCT→Hb) |
| Henderson-Hasselbalch pH = 6.1 + log(HCO3/0.03×PCO2) | lung.py:410-421 | ✅ 正确 |
| 肺泡气体方程 PAO2 = FiO2×(Patm-PH2O) - PaCO2/R | lung.py:221-248 | ✅ 正确 (含 RQ 代谢耦合) |
| Fick 扩散 VO2 = DL×(PAO2-PaO2) | lung.py:250-260 | ✅ 正确 |
| 呼吸代偿 (Van der Pol 振荡器) | lung.py:274-321 | ✅ 正确 (Kussmaul 呼吸) |

### 2. 心血管

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| CO = HR × SV | heart.py:213 | ✅ 正确 |
| MAP = CVP + CO/60 × SVR (Guyton) | heart.py:219 | ✅ 正确 |
| Frank-Starling: SV = base_SV × f(vol_ratio) | heart.py:186-194 | ✅ 正确 |
| 压力感受器: 交感/副交感反馈 | heart.py:225-251 | ✅ 正确 (Ursino 1998) |
| pH 对心肌收缩力影响 | heart.py:300 | ✅ 正确 |
| 心肌缺血 ODE (失代偿螺旋) | heart.py:253-269 | ✅ 正确 |

### 3. 肾脏

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| GFR = Kf × (PGC - PBS - πGC) | kidney.py:282-306 | ✅ Starling 方程 |
| 尿量 = 滤过 - 近端重吸收(67%) - 远端ADH调节 | kidney.py:324-348 | ✅ 正确 |
| 渗透性利尿 (血糖>8 mmol/L) | kidney.py:350-356 | ✅ 正确 |
| 钠重吸收 99% + 醛固酮调节 | kidney.py:308-320 | ✅ 正确 |

### 4. 单位转换 (症状引擎)

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| Glu mmol/L → mg/dL (×18.018) | clinical_signs_engine.py:515 | ✅ 已修复 |
| blood.Glu alias → glucose_mmol_L | clinical_signs_engine.py:528 | ✅ 已修复 |
| blood.bun alias → bun_mg_dL | clinical_signs_engine.py:529 | ✅ 已修复 |
| blood.bilirubin_mg_dL | symptom_definitions.json | ✅ 属性名匹配 |
| blood.consciousness_level | symptom_definitions.json | ✅ 属性名匹配 |

### 5. 仪表盘显示

| 检查项 | 文件:行 | 状态 |
|--------|---------|------|
| SpO2 Hill 方程 (P50=26.6, n=2.7) | ascii_dashboard.py:358 | ✅ 已修复 |
| Glu ×18.018 转换 | ascii_dashboard.py:360 | ✅ 正确 |
| 热力图/火花线 | ascii_dashboard.py | ✅ 正确 |

## 已修复 (4 commits)

| Bug | 文件 | 问题 | 修复 |
|-----|------|------|------|
| SpO2 线性公式 | dashboard | 所有正常 PaO2→100% | Hill 方程 |
| O2 content 硬编码 Hb | blood.py:153 | Hb=14.0，贫血时错误 | 从 HCT 推算 |
| blood.Glu 不存在 | clinical_signs_engine | 6 条规则永不触发 | alias + 单位转换 |
| blood.bun 不存在 | clinical_signs_engine | 2 条规则永不触发 | alias 映射 |

## 已修复 (追加)

- [x] ketotic_breath: blood.beta_hydroxybutyrate → disease.ketone_accumulation (commit b1c9139)
- [x] pH clamp [7.0, 7.8]: 验证合理，DKA 公式 max(6.95, 7.40-anion_gap*0.4) → pH≈7.0 at max severity
