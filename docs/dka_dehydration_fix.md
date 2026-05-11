# DKA 血容量崩溃问题分析与改造方案

## 1. 问题诊断

### 当前现象
14x 时间缩放后，DKA 仍在 6 分钟内杀死患者。血容量从 1720 mL 在 5 分钟内降到 0，MAP 从 100 降到 11.6。

| 时间 | dehydration | 乘数 | BV (mL) | MAP |
|------|------------|------|---------|-----|
| 0 min | 0.0000 | 1.000 | 1720 | 100 |
| 1 min | 0.0013 | 0.9995 | 1505 | 90.5 |
| 2 min | 0.0026 | 0.9991 | 997 | 85.9 |
| 3 min | 0.0040 | 0.9986 | 500 | 78.2 |
| 5 min | 0.0067 | 0.9977 | 53 | 62.6 |
| 10 min | 0.0140 | 0.9951 | 0 | 11.6 |

### 根因：每步乘法 = 指数衰减

DKA dehydration 输出：
```json
{ "target": "heart.blood_volume", "op": "multiply", "fn": "max(0.6, 1.0 - dehydration * 0.35)" }
```

**每步（0.1s）都执行一次乘法**。dehydration 在增长，乘数持续 < 1。

数学事实：**任何固定的 mult < 1，执行 N 次后 → mult^N → 0**。

即使乘数只比 1 小 0.001，42000 步（70 分钟）后：`0.999^42000 ≈ 10^(-18)`，血容量归零。

### 为什么其他疾病不会崩溃

| 疾病 | 乘法目标 | 最低乘数 | 影响 |
|------|---------|---------|------|
| 肺炎 | lung.diffusion_coefficient | 0.1 | 氧合下降，不直接致命 |
| DCM | heart.contractility_factor | 0.2 | 心功能下降，进展慢 |
| GDV | heart.SVR | 0.3 | 血管扩张，有代偿 |

这些参数降到很低只是"器官功能下降"，不会立即致命。但血容量归零 → MAP 崩溃 → 立即死亡。

### 饱和函数为何无效

`1/(1 + k×d)` 仍然是每步乘法。只要 dehydration 持续增长，乘数持续 < 1，长期必然归零。

**结论：任何每步都执行的乘法输出，只要乘数 < 1，长期都会归零。这是数学必然。**

## 2. 解决方案

### 核心思路

删除 dehydration 对血容量的直接乘法输出。DKA 的血容量丢失通过**尿量**间接实现（高血糖 → 渗透性利尿 → 尿量增加 → 血容量丢失）。

当前肾脏模型已有完整的尿量→血容量损失路径（加法模型，不会指数归零）：
```python
# kidney.py
self.blood_volume_loss_rate = self.urine_output * 0.30  # mL/min

# simulation.py Step 7.5
bv_loss = kidney.blood_volume_loss_rate * dt / 60.0  # 每步线性减
```

### 改动 1：删除 DKA 的 dehydration 血容量乘法输出

```json
// 删除这条：
{ "target": "heart.blood_volume", "op": "multiply", "fn": "max(0.6, 1.0 - dehydration * 0.35)" }
```

删除后，DKA 不会直接丢失血容量。正常尿量 0.6 mL/min → 血容量损失 0.18 mL/min，120 分钟损失 21.6 mL（1.3%），几乎无影响。

### 改动 2：在肾脏模型中添加高血糖 → 尿量效应

当前肾脏模型的尿量计算不受血糖影响。添加渗透性利尿效应：

```python
# kidney.py _compute_urine_output() 中添加：
# 渗透性利尿：血糖 > 8 mmol/L 时，尿量随血糖升高而增加
glucose = self.blood.glucose_mmol_L
if glucose > 8.0:
    osmotic_factor = 1.0 + (glucose - 8.0) * 0.3
else:
    osmotic_factor = 1.0
self.urine_output *= osmotic_factor
```

### 参数估算

| 血糖 (mmol/L) | 渗透因子 | 尿量 (mL/min) | 血容量损失 (mL/min) |
|--------------|---------|-------------|-------------------|
| 4.5 (正常) | 1.0 | 0.60 | 0.18 |
| 10 | 1.6 | 0.96 | 0.29 |
| 15 | 3.1 | 1.86 | 0.56 |
| 20 | 4.6 | 2.76 | 0.83 |
| 25 | 6.1 | 3.66 | 1.10 |
| 30 | 7.6 | 4.56 | 1.37 |

DKA 进展估算（14x 缩放，moderate preset）：
- hyperglycemia 从 0.1 增长到 0.8（血糖从 8 升到 29）约需 60-90 分钟
- 平均血糖 ≈ 20，平均尿量 ≈ 2.5 mL/min
- 120 分钟血容量损失 ≈ 2.5 × 0.30 × 120 = 90 mL
- BV 从 1720 → 1630（损失 5.2%）

MAP 下降 ≈ 5-8%，不会致死。**DKA 的主要死因将变为酸中毒（pH 下降）而非脱水**，这更符合真实病理。

### 验证目标

改动后，DKA 死亡时间应达到 70-100 分钟（由酸中毒驱动，而非脱水驱动）。

## 3. 其他疾病的类似问题

检查所有使用乘法输出的疾病，确认不会影响血容量：

| 疾病 | 乘法目标 | 是否影响 BV | 风险 |
|------|---------|------------|------|
| DKA | heart.blood_volume | **是** | **高（已修复）** |
| DCM | heart.blood_volume | **是**（fluid_retention × 0.15） | 低（乘法 > 1，增加 BV） |
| 其他 | 器官功能参数 | 否 | 无 |

DCM 的 fluid_retention 输出是 `1.0 + fluid_retention * 0.15`，乘数 > 1，血容量增加，不会崩溃。

## 4. 实施步骤

1. `data/ode_diseases.json`：删除 DKA 的 dehydration → blood_volume 乘法输出
2. `src/kidney.py`：在 `_compute_urine_output()` 中添加血糖 → 渗透性利尿效应
3. 运行验证脚本，确认 DKA 死亡时间达到 70-100 分钟
4. 运行全套测试，确认其他疾病不受影响
