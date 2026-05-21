# Virtual Vet — 兽医临床生理仿真引擎

> 基于多器官 ODE 系统的研究级生理仿真引擎，支持 Radau 隐式求解器统一求解全系统。

## 定位

**科研级生理仿真** — 用于兽医临床教育的生理引擎，也可作为论文投稿的技术基础。

与传统教学模拟器不同，本引擎：
- 使用 **Radau 隐式 ODE 求解器**（`scipy.integrate.solve_ivp`）同时求解 44 个状态变量
- **半隐式耦合**：模块间通过 CONNECTIONS 表路由输出→输入，避免顺序耦合的误差
- 12 个器官模块各自拥有 `derivatives()` 方法，支持独立验证和替换
- 配置驱动的疾病系统（`data/ode_diseases.json`），无需修改代码即可添加新疾病

## 架构

```
VirtualCreature
 ├── heart / lung / kidney / fluid          # 心血管 + 体液
 ├── gut / liver / endocrine                 # 消化 + 代谢 + 内分泌
 ├── neuro / immune / coagulation            # 神经 + 免疫 + 凝血
 ├── lymphatic                                # 淋巴 + 脾脏
 └── disease (config-driven)                 # 疾病 ODE → FactorCommand
```

**状态变量**（44 个）：

| 模块 | 状态变量 |
|------|---------|
| heart | HR, SV, SVR |
| lung | RR, TV, VQ |
| kidney | GFR, RBF, urine_output, ADH |
| fluid | V_vascular, V_isf, V_icf |
| gut | motility, barrier, microbiome |
| liver | glycogen_fraction, bilirubin_accumulation |
| endocrine | T3, insulin, glucagon, cortisol, PTH, IGF1, HPA_axis |
| neuro | sympathetic_tone, parasympathetic_tone, consciousness, seizure, pain |
| immune | cytokine, acute_phase, wbc, coagulation_state |
| coagulation | factor_VII, factor_V, factor_II, factor_IX, factor_X, factor_XI, fibrinogen, coagulation_state |
| lymphatic | splenic_reserve_mL, interstitial_fluid_mL |

## 核心 API

```python
from src.simulation import VirtualCreature

vc = VirtualCreature(body_weight_kg=20.0)

# 方式 1：Euler 步进（向后兼容）
vc.simulate(duration_minutes=30, verbose=True)
for _ in range(300):
    vc.step()

# 方式 2：Radau 统一求解（科研验证用）
sol = vc.run_unified_ivp(t_end=600.0, dt_save=1.0)
# sol.y.shape == (44, 601) — 44 状态变量 × 601 时间点
```

## 运行

```bash
# 安装依赖
uv sync

# 启动游戏
python gui_app.py
# 访问 http://127.0.0.1:5000

# 运行测试
python -m pytest tests/ -v

# 研究验证
python -c "
from src.simulation import VirtualCreature
vc = VirtualCreature(body_weight_kg=20.0)
sol = vc.run_unified_ivp(t_end=60.0)
print(f'Radau 求解: {sol.success}, 状态变量: {sol.y.shape}')
"
```

## 技术指标

- **求解器**：Radau IIA（5阶隐式 Runge-Kutta）— 无条件稳定，适合病态 ODE
- **状态维度**：44 个 ODE + 代数约束（通过一阶 lag 近似融入 ODE）
- **模块数量**：12 个器官模块 + 1 个疾病模块
- **测试覆盖**：698 tests PASS
- **稳态精度**：HR drift < 0.01 over 60s

## 论文定位

本引擎满足 CCF-C 论文的技术要求：
- **非 Euler 求解器**：Radau 隐式方法，收敛阶 ≥ 3
- **非顺序耦合**：半隐式耦合 + CONNECTIONS 表，模块间无显示依赖
- **可验证**：每个模块的 `derivatives()` 方法独立测试
- **可复现**：配置驱动疾病系统，JSON 声明式定义

> 配套论文写作中。详见 [CLAUDE.md](./CLAUDE.md) 的已知问题和待办。