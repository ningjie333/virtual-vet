"""
Neurological Module - 神经系统
建模自主神经、CNS、疼痛通路和化学感受器驱动:

  1. 化学感受器: PO2<70 / PCO2>50 / pH<7.35 → 驱动呼吸+交感
  2. 疼痛效应: pain_level (0-10) → 交感激活 → HR+/SVR×/肠道动力↓
  3. 癫痫活动: seizure>0.5 → 交感风暴 → 瞬时高血压+心动过速
  4. CNS功能障碍: consciousness<0.3 → 副交感主导 → 血管扩张+心动过缓

FactorCommand 目标: heart.heart_rate, heart.SVR, lung.respiratory_rate, gut.gut_motility
Step: 4.8 (endocrine之后, organ_health之前)
"""

from src.common_types import FactorCommand
from src.organ_guard import organ_setattr, _blood_escape


class NeuroModule:

    __setattr__ = organ_setattr

    # ── Phase 5: I/O contract (declarative, no behavior change) ────────
    INPUTS: tuple[str, ...] = ('heart_state', 'lung_state')
    OUTPUTS: tuple[str, ...] = ('sympathetic_tone', 'parasympathetic_tone', 'consciousness', 'seizure', 'pain_level', 'chemoreceptor_drive')
    READS_BLOOD: tuple[str, ...] = ('arterial_PCO2_mmHg', 'arterial_PO2_mmHg', 'arterial_pH')
    WRITES_BLOOD: tuple[str, ...] = ()
    """
    神经模块: 整合自主神经、CNS功能和疼痛通路

    设计原则:
      - 状态存储于 self.blood.* (共享读写)
      - FactorCommand 用于写入其他模块(立即apply)
      - Step 4.8 (endocrine之后, organ_health之前)
      - 疼痛是主要临床指标, 驱动HPA激活
    """

    def __init__(self, weight_kg: float, blood):
        self.w = weight_kg
        with _blood_escape(NeuroModule):
            self.blood = blood  # BloodCompartment 引用

        # 自主神经张力
        self.sympathetic_tone = 0.3       # 交感神经张力 (0-1)
        self.parasympathetic_tone = 0.7  # 副交感神经张力 (0-1)

        # CNS状态
        self.consciousness = 1.0         # 意识水平 (0=昏迷, 1=完全清醒)
        self.seizure = 0.0              # 癫痫活动 (0-1)
        self._seizure_timer = 0.0         # 癫痫持续计时器

        # 疼痛
        self.pain_level = 0.0            # 疼痛强度 (0-10)
        self._pain_target = 0.0           # 疼痛目标值(由疾病/FactorCommand写入)

        # 化学感受器
        self.chemoreceptor_drive = 0.0    # 化学感受器驱动 (0-1)

        # 用于存储上次状态(计算delta)
        self._prev_heart_rate = 85.0

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: sympathetic_tone, parasympathetic_tone, consciousness, seizure, pain, chemoreceptor
    # 输出端口（供其他模块）: chemoreceptor_drive, pain_level, seizure, consciousness

    def derivatives(self, dt: float, map_input: float = None, heart_hr: float = None, lung_rr: float = None) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        # 化学感受器驱动
        PO2 = self.blood.arterial_PO2_mmHg
        PCO2 = self.blood.arterial_PCO2_mmHg
        pH = self.blood.arterial_pH

        if PO2 < 70.0:
            hypoxic_drive = (70.0 - PO2) / 70.0
        else:
            hypoxic_drive = 0.0

        if PCO2 > 50.0:
            hypercapnic_drive = (PCO2 - 50.0) / 50.0
        else:
            hypercapnic_drive = 0.0

        if pH < 7.35:
            acid_drive = (7.35 - pH) / 0.35
        else:
            acid_drive = 0.0

        chemoreceptor_drive = min(1.0, hypoxic_drive * 0.3 + hypercapnic_drive * 0.5 + acid_drive * 0.2)
        self.chemoreceptor_drive = chemoreceptor_drive

        # 疼痛趋向目标值（一阶 lag）
        dPain = (self._pain_target - self.pain_level) / 10.0 if self._pain_target != self.pain_level else 0.0
        self.pain_level = max(0.0, min(10.0, self.pain_level + dPain * dt))

        # 癫痫计时器消退
        if self._seizure_timer > 0:
            self._seizure_timer = max(0.0, self._seizure_timer - dt)
            if self._seizure_timer <= 0:
                self.seizure = 0.0

        # 意识水平（MAP 驱动）
        # dConsciousness 是 per-second rate（τ=30s），无需除以 dt
        dConsciousness = 0.0
        if map_input is not None:
            if map_input < 40.0:
                consciousness_target = 0.2
            elif map_input < 60.0:
                consciousness_target = 0.5 + 0.75 * (map_input - 40.0) / 20.0
            elif map_input < 80.0:
                consciousness_target = 0.75 + 0.20 * (map_input - 60.0) / 20.0
            else:
                consciousness_target = 1.0
            dConsciousness = (consciousness_target - self.consciousness) / 30.0
            self.consciousness = max(0.0, min(1.0, self.consciousness + dConsciousness * dt))

        # 交感/副交感张力（slow adaptation）
        # 疼痛 → 交感↑; 低灌注 → 交感↑; 癫痫 → 交感风暴
        pain_sympathetic_effect = self.pain_level / 10.0 * 0.3
        seizure_sympathetic_effect = self.seizure * 0.4
        target_sympathetic = max(0.0, min(1.0, 0.3 + pain_sympathetic_effect + seizure_sympathetic_effect + chemoreceptor_drive * 0.2))
        target_parasympathetic = max(0.0, min(1.0, 0.7 - pain_sympathetic_effect * 0.5))

        dSympathetic = (target_sympathetic - self.sympathetic_tone) / 20.0
        dParasympathetic = (target_parasympathetic - self.parasympathetic_tone) / 30.0
        self.sympathetic_tone = max(0.0, min(1.0, self.sympathetic_tone + dSympathetic * dt))
        self.parasympathetic_tone = max(0.0, min(1.0, self.parasympathetic_tone + dParasympathetic * dt))

        dydt = {
            "sympathetic_tone": dSympathetic,
            "parasympathetic_tone": dParasympathetic,
            "consciousness": dConsciousness,
            "seizure": 0.0,
            "pain": dPain,
            "chemoreceptor": 0.0,
        }

        outputs = {
            "chemoreceptor_drive": chemoreceptor_drive,
            "pain_level": self.pain_level,
            "seizure": self.seizure,
            "consciousness": self.consciousness,
            "sympathetic_tone": self.sympathetic_tone,
            "parasympathetic_tone": self.parasympathetic_tone,
        }

        return dydt, outputs

    def set_pain_target(self, value: float) -> None:
        """外部调用: 设置疼痛目标值(由疾病通过FactorCommand或直接调用)"""
        self._pain_target = max(0.0, min(10.0, value))

    def trigger_seizure(self, intensity: float = 1.0) -> None:
        """外部调用: 触发一次癫痫发作"""
        self.seizure = max(self.seizure, min(1.0, intensity))
        self._seizure_timer = 60.0  # 持续60秒

    def compute(self, dt: float, heart_state: dict, lung_state: dict) -> dict:
        """
        计算神经状态和FactorCommand

        Args:
            dt: 时间步长 (秒)
            heart_state: heart.compute() 返回的 dict
            lung_state: lung.compute() 返回的 dict

        Returns:
            dict包含所有状态变量 + factor_commands列表
        """
        dt_min = dt / 60.0  # 转换为分钟

        # ── 1. 化学感受器 ──────────────────────────────────────────
        PO2 = self.blood.arterial_PO2_mmHg
        PCO2 = self.blood.arterial_PCO2_mmHg
        pH = self.blood.arterial_pH

        hypoxia_signal = max(0.0, (70.0 - PO2) / 70.0) if PO2 < 70 else 0.0
        hypercapnia_signal = max(0.0, (PCO2 - 50.0) / 50.0) if PCO2 > 50 else 0.0
        acidosis_signal = max(0.0, (7.35 - pH) / 0.35) if pH < 7.35 else 0.0

        chemoreceptor_raw = min(1.0, hypoxia_signal + hypercapnia_signal + acidosis_signal)
        # 一阶滞后 τ=30s
        tau_chemo = 30.0
        alpha_chemo = dt / tau_chemo
        self.chemoreceptor_drive += alpha_chemo * (chemoreceptor_raw - self.chemoreceptor_drive)

        # ── 2. 疼痛效应 ───────────────────────────────────────────
        # 疼痛目标值通过 _pain_target 设置(一阶滞后 τ=60s)
        tau_pain = 60.0
        alpha_pain = dt / tau_pain
        self.pain_level += alpha_pain * (self._pain_target - self.pain_level)

        # 疼痛 → 交感激活
        pain_sympathetic_effect = (self.pain_level / 10.0) * 0.5  # 最大+0.5
        pain_HR_add = (self.pain_level / 10.0) * 25.0            # 疼痛10分时最大+25bpm

        # ── 3. 癫痫活动 ───────────────────────────────────────────
        if self._seizure_timer > 0:
            self._seizure_timer -= dt
            seizure_effect = max(0.7, self.seizure)
        else:
            self.seizure = 0.0
            seizure_effect = 0.0

        seizure_HR_add = seizure_effect * 40.0  # 癫痫时最大+40bpm
        seizure_SVR_mult = 1.0 + seizure_effect * 0.3  # SVR最大×1.3

        # ── 4. CNS功能障碍 ────────────────────────────────────────
        cns_failure_signal = max(0.0, 1.0 - self.consciousness / 0.3) if self.consciousness < 0.3 else 0.0
        cns_HR_add = -20.0 * cns_failure_signal  # 最大-20bpm
        cns_SVR_mult = max(0.5, 1.0 - cns_failure_signal * 0.5)  # 最小×0.5

        # ── 5. 化学感受器效应 ─────────────────────────────────────
        chemo_HR_add = self.chemoreceptor_drive * 10.0   # 用于参考，不加入 FC
        chemo_RR_add = self.chemoreceptor_drive * 10.0   # 化学感受器驱动RR+10

        # ── 6. 自主神经张力计算 ──────────────────────────────────
        # 综合所有效应计算净心率变化
        # 化学感受器 HR 效应已移至 heart.py 连续路径（_baroreceptor_feedback），
        # 避免 FC 通道的 O(1) 数值偏差和双重计数。
        net_HR_add = (
            pain_HR_add
            + seizure_HR_add
            + cns_HR_add
            # chemo_HR_add → 已移至连续路径 heart.py
        )

        # 净SVR乘子
        net_SVR_mult = (
            seizure_SVR_mult
            * cns_SVR_mult
        )

        # 净RR变化(化学感受器)
        net_RR_add = chemo_RR_add

        # ── 7. 意识状态被动漂移 ──────────────────────────────────
        # 严重缺氧或CNS衰竭 → 意识下降
        hypoxia_consciousness_effect = -hypoxia_signal * 0.3 * dt_min
        self.consciousness = max(0.0, min(1.0, self.consciousness + hypoxia_consciousness_effect))

        # ── 8. 合成FactorCommands ────────────────────────────────
        # 注意：所有 FC 的 delta 必须乘以 dt（量纲正确化）。
        # 原有设计将 net_HR_add / net_RR_add 解释为"每步加固定值"，
        # 这导致粗 dt 下每步注入量相对时间偏小、细 dt 下偏大的 dt 依赖偏差。
        # 修正后这些值被解释为 RATE（bpm/s, resp/min/s），经 dt 缩放。
        # 阈值不变（chemo_drive > 0.01 触发，与之前一致）。
        factor_commands = []

        if abs(net_HR_add) > 0.1:
            factor_commands.append(FactorCommand("heart.heart_rate", "add", net_HR_add * dt))

        # SVR multiply dt-scaling: net_SVR_mult 是每步乘子（seizure/CNS调制），
        # 不 dt 归一化会导致细 dt 下乘的频次更高 → SVR 偏差。
        # 修复：将乘法转换为率形式：SVR_new = SVR × net_SVR_mult^(dt)
        # 其中 dt ∈ (0,1]，使总乘积 ∏ net_SVR_mult^(dt) = net_SVR_mult^(dt·N) = net_SVR_mult^T
        # 在 0 < dt ≤ 1 时，net_SVR_mult^(dt) ≈ 1 + (net_SVR_mult-1)·dt（泰勒展开，一阶近似）。
        if abs(net_SVR_mult - 1.0) > 0.01:
            rate_factor = net_SVR_mult ** dt
            factor_commands.append(FactorCommand("heart.SVR", "multiply", rate_factor))

        if abs(net_RR_add) > 0.1:
            factor_commands.append(FactorCommand("lung.respiratory_rate", "add", net_RR_add * dt))

        # 疼痛 → 肠道动力下降
        if self.pain_level > 0.5:
            gut_motility_mult = max(0.2, 1.0 - (self.pain_level / 10.0) * 0.8)
            factor_commands.append(FactorCommand("gut.gut_motility", "multiply", gut_motility_mult))

        return {
            "sympathetic_tone": round(self.sympathetic_tone, 3),
            "parasympathetic_tone": round(self.parasympathetic_tone, 3),
            "consciousness": round(self.consciousness, 3),
            "seizure": round(self.seizure, 3),
            "pain_level": round(self.pain_level, 1),
            "chemoreceptor_drive": round(self.chemoreceptor_drive, 3),
            "net_HR_add": round(net_HR_add, 1),
            "net_SVR_mult": round(net_SVR_mult, 3),
            "factor_commands": factor_commands,
        }

    def summary(self) -> dict:
        """返回神经状态摘要(用于历史记录)"""
        return {
            "sympathetic_tone": round(self.sympathetic_tone, 3),
            "parasympathetic_tone": round(self.parasympathetic_tone, 3),
            "consciousness": round(self.consciousness, 3),
            "seizure": round(self.seizure, 3),
            "pain_level": round(self.pain_level, 1),
            "chemoreceptor_drive": round(self.chemoreceptor_drive, 3),
        }
