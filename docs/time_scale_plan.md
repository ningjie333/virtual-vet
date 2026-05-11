# ODE 时间尺度重缩放方案

## 问题

引擎 ODE 速率常数以秒为单位，游戏时间以分钟为单位。玩家每消耗 1 游戏分钟，引擎模拟 1 分钟（600 步 × 0.1s）。所有疾病在 2-17 引擎分钟内杀死患者，但游戏时间预算 60-120 分钟，检查耗时 5-45 分钟。玩家做一个检查的时间，患者已经死了。

## 方案

统一全局缩放系数 **14x**。在 `ConfigDrivenDiseaseModule.__init__()` 加载参数时，将所有速率参数、tau 值、seed_boost 除以 14。

### 14x 后各疾病死亡时间

| 疾病 | 当前死亡时间 | 14x 后死亡时间 |
|------|------------|--------------|
| DKA | 5 min | 70 min |
| 磷化锌中毒 | 5 min | 70 min |
| DCM | 5 min | 70 min |
| 肺炎 | 7 min | 98 min |
| GDV | 7 min | 98 min |
| IMHA | 9 min | 126 min |
| 心包积液 | 9 min | 126 min |
| DIC | 11 min | 154 min |
| 急性肾衰 | 16 min | 224 min |
| 尿道梗阻 | 16 min | 224 min |

与时间预算对比：困难 60 min / 普通 90 min / 简单 120 min。最快死亡 70 min，困难模式下玩家必须在超时前完成诊断+治疗，有压力但不至于不可能。

## 改动

### 只改 1 个文件：`src/diseases/config_driven.py`

**改动 A：速率参数缩放**（severity preset 加载之后，line ~194）

```python
# 时间缩放：引擎速率 → 游戏速率（统一 14x）
_TIME_SCALE = 14.0
for key in list(self._params.keys()):
    if key.endswith("_rate"):
        self._params[key] /= _TIME_SCALE
```

**改动 B：tau 和 seed_boost 缩放**（state_variables 循环中，line ~205）

在构建 `raw_params` 之后：

```python
if "tau" in raw_params:
    raw_params["tau"] /= _TIME_SCALE
if "seed_boost" in raw_params:
    raw_params["seed_boost"] /= _TIME_SCALE
```

## 不需要改的文件

- `simulation.py`、`action_system.py`、`game_config.json`、`examinations.json`、`time_manager.py`、所有 organ 模块 — 全部不变
- `ode_diseases.json` — 不需要加字段，缩放写死在代码里（单一常量，未来好调）

## 风险

- `seed_boost_fn` 表达式中的硬编码系数（如 `0.001 * min(...)`）也是速率量纲，但只在状态变量很小时起作用，影响小。不处理。
- 夜间系数（0.8x）只影响 HR，不影响 ODE 速率。正确。
- `test_arf_hr_bradycardia` 已有 skip 路径，钾上升变慢会 skip 而非 fail。

## 验证

```python
from src.simulation import VirtualCreature
from src.diseases import create_disease

DISEASES = [
    ("diabetic_ketoacidosis", "DKA"),
    ("phosphorus_poisoning", "磷化锌中毒"),
    ("dilated_cardiomyopathy", "DCM"),
    ("pneumonia", "肺炎"),
    ("gastric_dilatation_volvulus", "GDV"),
    ("immune_mediated_hemolytic_anemia", "IMHA"),
    ("pericardial_effusion", "心包积液"),
    ("disseminated_intravascular_coagulation", "DIC"),
    ("acute_renal_failure", "急性肾衰"),
    ("urinary_obstruction", "尿道梗阻"),
]

for name, label in DISEASES:
    creature = VirtualCreature(body_weight_kg=20.0)
    disease = create_disease(name, severity="moderate")
    creature.attach_disease(disease)
    creature.simulate(240)
    death_min = None
    for i, map_val in enumerate(creature.history["MAP_mmHg"]):
        if map_val < 40:
            death_min = creature.history["time_s"][i] / 60
            break
    if death_min:
        print(f"{label}: 死亡 {death_min:.0f} min")
    else:
        print(f"{label}: 存活 240 min")
```
