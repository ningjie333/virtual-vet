# 检查并行化方案

## 问题

当前每个检查 = `time_cost_min`（采样）+ `latency_min`（出报告），玩家必须串行等待。比如生化全项要采样 40 分钟 + 等 30 分钟报告 = 70 分钟，期间什么都不能做。

实际上很多检查可以**同时采样**——抽血做血气和生化，采样时间重叠，只是出报告时间不同。

## 方案

把 `time_cost_min` 拆成两部分：

1. **采样时间**（`setup_time_min`）：实际采血/拍片/操作的时间，很短（1-5 分钟）
2. **处理时间**（`processing_time_min`）：机器跑分析 + 出报告延迟，期间玩家可以做其他事

玩家点击检查 → 采样快速完成 → 样本自动送检 → 玩家可以立即做下一个检查 → 报告按各自延迟陆续出来。

## 检查时间拆分参考

| 检查 | 采样时间 | 报告延迟 | 总等待 |
|------|---------|---------|-------|
| 体格检查 | 2 min | 0 min | 2 min |
| 听诊 | 1 min | 0 min | 1 min |
| 视诊 | 1 min | 0 min | 1 min |
| 血压测量 | 1 min | 0 min | 1 min |
| 心电图 | 2 min | 0 min | 2 min |
| 血气分析 | 2 min | 0 min | 2 min |
| 血常规 | 2 min | 10 min | 12 min |
| 尿液分析 | 2 min | 0 min | 2 min |
| 生化全项 | 3 min | 30 min | 33 min |
| X光胸片 | 3 min | 15 min | 18 min |
| 超声检查 | 3 min | 15 min | 18 min |
| CT | 5 min | 30 min | 35 min |
| 超声心动图 | 5 min | 20 min | 25 min |
| 内窥镜 | 5 min | 15 min | 20 min |
| 腹腔穿刺 | 3 min | 30 min | 33 min |
| 胸腔穿刺 | 3 min | 30 min | 33 min |
| 细胞学检查 | 3 min | 1440 min | 1443 min |
| 细针穿刺 | 3 min | 1440 min | 1443 min |
| 组织病理学 | 5 min | 2880 min | 2885 min |
| MRI | 5 min | 30 min | 35 min |
| 快速检测（SNAP） | 2 min | 0 min | 2 min |

## 改动

### 1. `data/examinations.json`

每个检查把 `time_cost_min` 拆成 `setup_time_min` + `latency_min`：

```json
"blood_biochem": {
    "name": "生化全项",
    "tier": 3,
    "setup_time_min": 3,
    "latency_min": 30,
    ...
}
```

### 2. `game/action_system.py`

- `examine` 行动消耗的时间从 `time_cost_min` 改成 `setup_time_min`
- 报告延迟队列的 `minutes_remaining` 从 `latency_min` 改成 `processing_time_min`
- 采样完成后样本自动送检，玩家可以立即做下一个检查

### 3. 前端

- UI 上显示"采样中"和"报告中"两种状态
- 采样中的检查显示进度条
- 报告队列显示倒计时

## 关键规则

- 采样阶段：玩家一次只能做一个采样（不能同时抽两管血）
- 采样完成后：样本自动送检，玩家可以立即做下一个检查
- 报告延迟：独立计时，从采样完成开始算
- 已有 `PendingReport` 队列机制可以直接复用

## 不需要改的部分

- 引擎核心（`simulation.py`）— 不变
- 疾病 ODE — 不变
- 游戏时间预算 — 不变
- `report_engine.py` — 不变
