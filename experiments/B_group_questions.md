# VetSim — 待专家决策问题（B组）

## 诊断背景

2026-05-22 诊断脚本 `tools/diagnose_rhs.py` 结果：

```
T1: rhs 非确定性检测（5次调用）
d1 vs d2: 4.33e-01  ← 第一次调用 map_input=0 → V_vascular=-0.067
d2 vs d3: 1.26e-08  ← 收敛
d3 vs d4: 1.66e-08
d4 vs d5: 1.91e-08
最大差异: 4.33e-01
FAIL（非确定性）

T2: VdP 状态检测
VdP (x,v) 在 y 向量中: False ← 不在
Respiratory 模块条目: [] ← 空
VdP 对象: x=2.0, v=0.0, rr_rest=0.25 Hz (=15/min)
```

---

## ❓ B1 — VdP μ 参数化（从 RR=18→15 触发）

**问题**：当前 `VanDerPolRespiratoryRhythm` 的自然频率 μ 是硬编码（`MU_NORMAL=1.5`），无法随 rr_rest 参数调整。

**具体疑问**：
- μ=1.5 对应 RR=18Hz 时，μ 与 rr_rest 如何协调？
- 从用户确认的 A1 决策："保持 VdP 的 (x, v) 在 y 向量里"，但 VdP 的 μ 参数如何从 rr_rest=15/60 自动调整？
- 生理含义：μ 控制振荡衰减率（弱束缚 vs 强束缚振荡），与化学感受器驱动强度耦合

**选项**：
- A: 在 `VanDerPolRespiratoryRhythm.__init__()` 添加 `mu` 参数，默认 `MU_NORMAL`
- B: μ 根据 rr_rest 动态计算（如 μ = μ0 * (rr_rest_normalized)^0.5）
- C: μ 保持固定，但 rr_rest 只控制 ω（频率），不控制 μ

**推荐**：选项 A（μ 作为独立可调参数）

---

## ❓ B2 — 凝血非确定性（PT/aPTT 在 rhs 内游走）

**问题**：`blood.derivatives()` 读取 `cached_inputs["heart.cardiac_output"]`，但该值由 `heart.derivatives()` 在同一 rhs 调用内写入。同一时刻的 PT_sec 取决于调用顺序，造成非确定性。

**诊断数据**：
```
max|dydt1 - dydt2| = 1.26e-08  (收敛后)
最大差异分量: [10] fluid.V_vascular = -0.067 vs -0.50
根因: 第一次 rhs 调用 map_input=0 → fluid.V_vascular=-0.067
      第二次 rhs 调用 map_input=100 → fluid.V_vascular=-0.50
      收敛后 diff=1.26e-08（由 blood PT_sec 游走造成）
```

**选项**：
- A: `blood.derivatives()` 直接从 `heart` 模块读取（而非 `_cached_inputs`）
- B: 保持现状（非确定性已收敛到 1.26e-08，对 Radau Newton 迭代影响有限）
- C: 在 `_unified_rhs` 开始时强制刷新 `_cached_inputs["heart"]` 一次

**推荐**：选项 B（当前非确定性在可接受范围内，且根本上是初始化问题，非结构性问题）

---

## ❓ B3 — sigmoid 失血参数

**问题**：失血模型参数（替代 `schedule_event` 的连续 ODE）：

| 参数 | 含义 | 建议值 | 依据 |
|------|------|--------|------|
| `t_onset` | 失血开始时间 | 5s | 实验设定 |
| `duration` | 400mL 多久放完？ | **?** | 临床：II级休克 400mL 在 5-10min 内丢失 |
| `width` | sigmoid 上升沿宽度 | 5s？ | 使失血开始平滑 |

**具体疑问**：
- duration=300s（5min）还是更短？动物实验通常 5-10min
- width=5s 是否合理？（sigmoid 平滑 5s 内上升到峰值）

**选项**：
- A: duration=300s, width=5s（缓慢失血，5min）
- B: duration=60s, width=3s（快速失血，1min）
- C: duration=600s, width=10s（极慢失血，10min）

**推荐**：选项 A（II级休克 400mL/5min 更符合失血性休克病理生理）

---

## ❓ B4 — Radau rtol/atol 选择

**问题**：对于 44 变量 stiff 系统，当前 `rtol=1e-8, atol=1e-10` 是否足够？

**参考**：
- `run_unified_ivp` 当前设置：`rtol=1e-5, atol=1e-8`（较宽松）
- 实验 `solver_comparison.py`：`rtol=1e-8, atol=1e-10`（更严格）

**具体疑问**：
- 生理验证标准：PaCO₂/pH 需要多高精度？
- 当前 RR=15 下 PaCO₂=40.0, pH=7.401 是否满足"临床可接受误差"？

**选项**：
- A: 保持 rtol=1e-5, atol=1e-8（宽松，快速）
- B: rtol=1e-8, atol=1e-10（严格，更慢但更准确）
- C: rtol=1e-10, atol=1e-12（极高精度，用于验证；生产用 A）

**推荐**：选项 B（严格但不过度，用于 Figure 4 实验；生产环境用 A）

---

## 诊断截图（供专家参考）

### T1 非确定性来源

```
Unified_rhs 调用序列：
1. 解包 y
2. module_inputs = cached_inputs（第1次调用时为空）
3. heart.derivatives() → 输出写入 all_outputs["heart"]
4. 按 CONNECTIONS 路由 → cached_inputs["heart"] = {cardiac_output: ..., MAP: ...}
5. lung.derivatives() → 从 cached_inputs["lung"]["co_input"] 读取（空=0）
6. ...
7. 第二次 rhs 调用：cached_inputs 已填充 → 一致性建立
```

### VdP 状态缺失的影响

```
y 向量长度: 44（无 VdP 状态）
VdP 在 rhs 调用间独立推进（每次 update() 用内部 dt=0.01）
→ VdP 相位在 rhs 调用间游走
→ Radau 认为系统达到稳态（60s 时相位恰好对齐）
→ 60s 显示 "success=True, steps=19"（假的）
```

---

## 下一步

1. 用户咨询专家 → 获得 B1-B4 答案
2. 实施 A1（VdP μ 参数化）+ A3（sigmoid 失血）
3. 运行 Figure 4 耦合对比实验