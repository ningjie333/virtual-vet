"""
Lung Module - 肺气体交换系统
建模肺通气、气体扩散、血气交换

呼吸节律由 Van der Pol 振荡器驱动（替代线性化学感受器反馈）：
  - 呼吸频率和深度由 VdP 极限环振荡产生
  - 化学感受器（PCO2/PO2/pH）调制 VdP 的 ω 和 μ 参数
  - 产生自然的呼吸性窦性心律不齐（吸气相 RR 轻微加快）
"""

from parameters import *
from src.respiratory_rhythm import VanDerPolRespiratoryRhythm
from src.organ_guard import organ_setattr, _blood_escape
import math


class LungModule:

    __setattr__ = organ_setattr

    # ── Phase 5: I/O contract (declarative, no behavior change) ────────
    INPUTS: tuple[str, ...] = ('co_input', 'P_ACO2')
    OUTPUTS: tuple[str, ...] = ('arterial_PO2_mmHg', 'arterial_PCO2_mmHg', 'arterial_pH', 'arterial_saturation', 'alveolar_PO2_mmHg', 'alveolar_PCO2_mmHg', 'minute_ventilation')
    READS_BLOOD: tuple[str, ...] = ('arterial_PO2_mmHg', 'arterial_PCO2_mmHg', 'arterial_saturation', 'arterial_pH', 'venous_PCO2_mmHg', 'HCO3')
    WRITES_BLOOD: tuple[str, ...] = ('arterial_PO2_mmHg', 'arterial_PCO2_mmHg', 'arterial_pH', 'arterial_saturation')

    # ── Step 2 (solver-refactor-roadmap-v3): ODE state declaration ──────
    STATE_VARS: tuple[tuple[str, str], ...] = (
        ("RR", "respiratory_rate"),
        ("TV", "tidal_volume"),
        ("VQ", "VQ_ratio"),
    )
    """
    肺气体交换模块：模拟肺通气与气体交换

    核心变量：
    - alveolar_PO2, alveolar_PCO2: 肺泡气体分压
    - arterial_PO2, arterial_PCO2: 动脉血气分压
    - respiratory_rate: 呼吸频率
    - tidal_volume_ml: 潮气量

    核心方程：
    - A-a gradient = PAO2 - PaO2
    - O2 diffusion: VO2 = DL × (PAO2 - PaO2)
    - CO2 diffusion: VCO2 = DL × (PaCO2 - PACO2)
    - Alveolar gas equation: PAO2 = FiO2 × (Patm - PH2O) - PACO2/R
    """

    def __init__(
        self,
        weight_kg: float,
        blood,
        base_RR: float = RESPIRATORY_RATE_REST,
        max_RR: float = RESPIRATORY_RATE_STRESS,
        tidal_vol_ml: float = None,       # 若为 None 则按 12 mL/kg 计算
        diffusion_coef: float = LUNG_DIFFUSION_COEFFICIENT,
        pulmonary_compliance: float = PULMONARY_COMPLIANCE,
        base_minute_vent: float = None,   # 若为 None 则按 TV × RR 计算
    ):
        self.w = weight_kg
        with _blood_escape(LungModule):
            self.blood = blood  # 血液隔室引用

        # 潮气量（外部传入或按 12 mL/kg 计算）
        _tv = tidal_vol_ml if tidal_vol_ml is not None else 12.0 * weight_kg

        # 通气参数
        self.base_respiratory_rate = base_RR
        self.max_respiratory_rate = max_RR
        self.respiratory_rate = base_RR            # 当前呼吸频率 /min
        self.base_tidal_volume = _tv
        self.tidal_volume = _tv                     # 当前潮气量 mL
        self.base_minute_ventilation = base_minute_vent if base_minute_vent is not None else _tv * base_RR

        # 扩散参数
        self.diffusion_coefficient = diffusion_coef  # 肺扩散系数 mL O2/min/mmHg

        # 顺应性
        self.pulmonary_compliance = pulmonary_compliance  # mL/mmHg

        # 肺泡气体分压
        self.alveolar_PO2 = ALVEOLAR_PO2_NORMAL    # mmHg
        self.alveolar_PCO2 = ALVEOLAR_PCO2_NORMAL  # mmHg

        # 大气参数
        self.FiO2 = 0.2093                          # 吸入气氧浓度 21%
        self.Patm_mmHg = ATMOSPHERIC_PRESSURE_MMHG   # 大气压（海平面）
        self.PH2O_mmHg = WATER_VAPOR_PRESSURE_MMHG    # 37°C 水蒸气分压

        # 气体交换量
        self.O2_consumption = 0.0                   # mL O2/min
        self.CO2_production = 0.0                   # mL CO2/min

        # 呼吸商
        self.respiratory_quotient = 0.8             # RQ = VCO2/VO2

        # 通气血流比（V/Q matching）
        self.VQ_ratio = 0.8                         # 正常约 0.8

        # VdP 幅度平滑追踪器（步骤3：消除每呼吸周期振幅振荡）
        # amplitude 振荡在呼吸周期频率上，用 3s 窗口平均消除
        self._vdp_amp_smoothed = 2.0                # 初始值与极限环幅值一致
        # Phase 2 #6: 分流 + 死腔通道 (West 2012)
        self.shunt_fraction = 0.0                   # 0=正常, 0.3=ARDS
        self.dead_space_fraction = 0.3              # 正常 ≈ 0.3

        # 代偿参数
        self.respiratory_compensation = 0.0         # 呼吸代偿程度

        # Van der Pol 呼吸节律振荡器
        # 静息 RR=18/min 与 parameters.RESPIRATORY_RATE_REST 保持一致，
        # 使 baseline minute ventilation 与 PaCO2=40 mmHg 匹配。
        dt = DT_SECONDS  # 与仿真步长一致
        self._vdp = VanDerPolRespiratoryRhythm(
            dt=dt,
            rr_rest=18.0 / 60.0,  # 18/min → 0.3 Hz
        )

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: RR, TV, VQ_ratio
    # 输出端口（供其他模块）: arterial_PO2, arterial_PCO2, arterial_saturation, minute_vent

    def derivatives(self, dt: float, co_input: float = None) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Args:
            dt: 时间步长（秒）
            co_input: 心输出量 mL/min（来自心脏模块，若为 None 则用当前 self.cardiac_output）

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        # ── 1. 分钟通气量（代数） ─────────────────────────────────────────────
        minute_ventilation = self.respiratory_rate * self.tidal_volume  # mL/min

        # ── 2. PACO2（代数） ──────────────────────────────────────────────────
        vent_ratio = minute_ventilation / self.base_minute_ventilation
        alveolar_PCO2 = 40.0 / vent_ratio
        alveolar_PCO2 = max(15.0, min(80.0, alveolar_PCO2))

        # ── 3. PAO2（代数） ──────────────────────────────────────────────────
        alveolar_PO2 = self._alveolar_gas_equation(
            self.respiratory_rate, self.tidal_volume, alveolar_PCO2)

        # ── 4. 气体扩散（代数） ──────────────────────────────────────────────
        # NOTE(C5): 纯函数化 — VO2/VCO2 不再直接写 self，改为本地变量 +
        # self_ 输出端口（由 caller 在 Newton 迭代收敛后一次性写回）
        PO2_gradient = alveolar_PO2 - self.blood.arterial_PO2_mmHg
        VO2 = self.diffusion_coefficient * PO2_gradient * self.VQ_ratio
        VO2 = max(0.0, VO2)

        PCO2_gradient = self.blood.venous_PCO2_mmHg - alveolar_PCO2
        VCO2 = self.diffusion_coefficient * 0.2 * PCO2_gradient * self.VQ_ratio
        VCO2 = max(0.0, VCO2)

        # ── 5. 动脉血气（代数）─────────────────────────────────────────────
        # A-a 梯度上限提到 60 mmHg 以表达 ARDS 级低氧（McCaffree 1978）
        # NOTE(C5): 不再直接写 self.blood.*，改为返回值由调用方写入
        # Phase 2 #6: A-a 梯度加 shunt + dead_space
        # shunt: 直通右→左血 (PaO2 ↓ 严重, 即使 DL 正常)
        # dead_space: 通气但不换气 (PaCO2 ↑)
        # REF: West 2012
        aa_gradient = 5.0 + (1.0 - self.diffusion_coefficient / LUNG_DIFFUSION_COEFFICIENT) * 50.0
        # shunt 增加梯度 (右向左分流 5% → +5 mmHg, 30% → +30 mmHg)
        aa_gradient += self.shunt_fraction * 100.0
        a_PO2 = max(40.0, min(110.0, alveolar_PO2 - aa_gradient))
        a_PCO2 = max(15.0, min(80.0, alveolar_PCO2))
        a_saturation = self._oxygen_saturation_curve(a_PO2)
        HCO3 = getattr(self.blood, 'HCO3', HCO3_EXTRACELLULAR_MEQ_L)
        if HCO3 < 1.0:
            HCO3 = HCO3_EXTRACELLULAR_MEQ_L
        pH = 6.1 + math.log10(HCO3 / (0.03 * a_PCO2)) if a_PCO2 > 0 else 7.4
        a_pH = max(6.8, min(7.8, pH))
        # 文献：Henderson-Hasselbalp 方程，pKa=6.1, CO2 溶解系数 0.03
        # 本地文献：Batzel 2009 心血管调节系统识别

        # ── 8. VdP 振荡器（读取目标 RR/TV） ──────────────────────────────
        # NOTE(C5): 纯函数化 — 不再调用 _vdp.update() 推进内部状态。
        # VdP 状态由 compute() 中的 _respiratory_compensation() 管理
        # （每步调用一次 update()），derivatives() 只读取当前 VdP 输出
        # 计算 RR/TV 的目标值。Newton 子迭代期间 VdP 目标保持不变，
        # 避免子迭代间状态污染。
        target_rr = self._vdp.respiratory_rate
        target_tv_factor = 1.0 + 0.7 * max(0.0, (self._vdp.amplitude - 0.8) / 1.2) if self._vdp.amplitude > 0.8 else 1.0
        target_tv = self.base_tidal_volume * target_tv_factor

        # ── 9. 状态变量导数（dRR/dt, dTV/dt） ────────────────────────────────
        # dRR/dt = (target_rr - RR) / τ_RR, τ_RR = 0.5s → rate = 2.0 * error
        # dTV/dt = (target_tv - TV) / τ_TV, τ_TV = 0.5s → rate = 2.0 * error
        # 使用 time-constant 公式（不依赖 dt），使 RHS 与求解器 dt 解耦
        tau_rr = 0.5  # s
        tau_tv = 0.5  # s
        dRR = (target_rr - self.respiratory_rate) / tau_rr
        dTV = (target_tv - self.tidal_volume) / tau_tv

        # VQ_ratio 缓慢适应（由其他模块调节，本身为慢变量）
        dVQ = 0.0  # 保持不变

        dydt = {
            "RR": dRR,
            "TV": dTV,
            "VQ": dVQ,
        }

        outputs = {
            "arterial_PO2_mmHg": a_PO2,
            "arterial_PCO2_mmHg": a_PCO2,
            "arterial_saturation": a_saturation,
            "arterial_pH": a_pH,
            "minute_ventilation": minute_ventilation,
            "O2_consumption_mL_min": VO2,
            "CO2_production_mL_min": VCO2,
            "alveolar_PO2_mmHg": alveolar_PO2,
            "alveolar_PCO2_mmHg": alveolar_PCO2,
            "vdp_amplitude": self._vdp.amplitude,
            "vdp_phase": self._vdp.phase,
            "vdp_is_inspiration": self._vdp.is_inspiration,
            # NOTE(C5): self_* 字段 — caller 在 Newton 迭代收敛后一次性写回
            # O2_consumption / CO2_production 不在 STATE_VARS，需通过 self_ 写回
            "self_O2_consumption": VO2,
            "self_CO2_production": VCO2,
        }

        return dydt, outputs

    def _alveolar_gas_equation(self, RR: float, Vt: float, PACO2: float) -> float:
        """
        肺泡气体方程 + Phase 2 #11 代谢耦合 RQ — REF: Frayn 2010
        PAO2 = FiO2 × (Patm - PH2O) - PACO2/R
        RQ 随血糖状态变化:
        - glucose > 12 (DKA) → RQ ≈ 0.70 (脂肪氧化)
        - glucose 6-12 → RQ ≈ 0.85
        - glucose 4-6 → RQ ≈ 0.95 (糖类氧化)
        - glucose < 4 → RQ ≈ 0.80 (低血糖脂肪)
        """
        PIO2 = self.FiO2 * (self.Patm_mmHg - self.PH2O_mmHg)  # 吸入气氧分压 ≈ 150 mmHg
        # Phase 2 #11: 代谢耦合 RQ (温和范围, 不破坏基线 PAO2)
        # - DKA (glucose > 12) → RQ 0.70 (脂肪氧化)
        # - 高血糖 (6-12) → 0.82
        # - 正常 (4-6) → 0.88 (略低于 0.95 避免 PAO2 越界)
        # - 低血糖 (<4) → 0.78
        glucose = getattr(self.blood, 'glucose_mmol_L', 5.0)
        if glucose > 12.0:
            R = 0.70
        elif glucose > 6.0:
            R = 0.82
        elif glucose > 4.0:
            R = 0.88
        else:
            R = 0.78
        R = max(0.65, min(1.0, R))
        PAO2 = PIO2 - PACO2 / R
        return max(50.0, min(150.0, PAO2))

    def _compute_oxygen_diffusion(self):
        """
        氧扩散：肺泡 → 动脉血
        Fick's law: VO2 = DL × (PAO2 - PaO2)
        """
        PO2_gradient = self.alveolar_PO2 - self.blood.arterial_PO2_mmHg
        # 实际扩散量受 V/Q 比调节
        VO2 = self.diffusion_coefficient * PO2_gradient * self.VQ_ratio
        VO2 = max(0.0, VO2)
        self.O2_consumption = VO2
        return VO2

    def _compute_CO2_diffusion(self):
        """
        CO2 扩散：静脉血 → 肺泡
        Fick's law: VCO2 = DL × (PaCO2 - PACO2)
        """
        PCO2_gradient = self.blood.venous_PCO2_mmHg - self.alveolar_PCO2
        # CO2 扩散系数约为 O2 的 20 倍（但浓度换算后）
        VCO2 = self.diffusion_coefficient * 0.2 * PCO2_gradient * self.VQ_ratio
        VCO2 = max(0.0, VCO2)
        self.CO2_production = VCO2
        return VCO2

    def _respiratory_compensation(self, arterial_PCO2: float, arterial_PO2: float, dt: float):
        """
        呼吸代偿：通过 Van der Pol 振荡器驱动

        化学感受器（PCO2/PO2/pH）调制 VdP 的 ω（频率）和 μ（幅度）参数，
        振荡器自然产生节律性呼吸驱动，替代原有的线性反馈。

        - 高碳酸血症 → VdP ω↑ + μ↑ → RR 加快 + 深度增大
        - 低氧血症  → VdP ω↑ → RR 加快
        - 酸中毒    → VdP ω↑ + μ↑ → Kussmaul 呼吸
        """
        # 获取当前 pH
        arterial_pH = self.blood.arterial_pH

        # VdP 推进：将 dt 拆分为不超过 VdP 设计步长（0.1s）的子步。
        # dt<=0.1 时单步推进（修复原 10 倍速 bug），dt>0.1 时多步迭代。
        _VDP_DT = 0.1  # VdP 原始设计步长
        n = max(1, round(dt / _VDP_DT))
        sub_dt = dt / n
        self._vdp.dt = sub_dt
        for _ in range(n):
            self._vdp.update(pco2=arterial_PCO2, po2=arterial_PO2, ph=arterial_pH)

        # 从 VdP 输出获取目标呼吸频率
        target_rr = self._vdp.respiratory_rate

        # 步骤5：RR 变化限幅（速率限制：10 breath/min/s，防止 Kussmaul 超调）
        # 原 dt=0.1s 时每步 ±1 breath/min = 10 breath/min/s；改为按 dt 缩放，dt 改变时代偿速度不变。
        rr_error = target_rr - self.respiratory_rate
        max_rr_change = 10.0 * dt  # breath/min per step (rate-limited: 10 breath/min/s)
        clamped_error = max(-max_rr_change, min(max_rr_change, rr_error))
        self.respiratory_rate += clamped_error

        # 限幅
        self.respiratory_rate = max(
            self.base_respiratory_rate * 0.5,
            min(self.max_respiratory_rate, self.respiratory_rate)
        )

        # 步骤3：VdP 幅度3s 滑动平均（消除每呼吸周期振荡）
        alpha_amp = min(1.0, dt / 3.0)
        self._vdp_amp_smoothed += (self._vdp.amplitude - self._vdp_amp_smoothed) * alpha_amp

        # 步骤4：TV 改用 RR 偏差驱动（而非 amplitude），解耦 TV 与 VdP 幅度
        # RR 偏离基线越大 → 通气需求越高 → TV 增大
        rr_ratio = self.respiratory_rate / self.base_respiratory_rate
        tv_factor = 1.0 + 0.3 * max(0.0, rr_ratio - 1.0)
        tv_factor = max(0.8, min(1.5, tv_factor))
        self.tidal_volume = self.base_tidal_volume * tv_factor

    def compute(self, dt: float, cardiac_output: float):
        """
        主计算函数：推进肺部气体交换一个时间步

        Args:
            dt: 时间步长（秒）
            cardiac_output: 心输出量 mL/min（来自心脏模块）

        Returns:
            肺部气体交换状态 dict
        """
        # Step 1: 分钟通气量
        minute_ventilation = self.respiratory_rate * self.tidal_volume  # mL/min

        # Step 2: PACO2 受通气量影响：通气量↑ → PACO2 ↓
        vent_ratio = minute_ventilation / self.base_minute_ventilation
        self.alveolar_PCO2 = 40.0 / vent_ratio
        self.alveolar_PCO2 = max(15.0, min(80.0, self.alveolar_PCO2))

        # 肺泡气体方程计算 PAO2（用计算后的 PACO2）
        self.alveolar_PO2 = self._alveolar_gas_equation(
            self.respiratory_rate, self.tidal_volume, self.alveolar_PCO2)

        # Step 3: 气体扩散（肺泡 ↔ 血液）
        O2_consumed = self._compute_oxygen_diffusion()
        CO2_produced = self._compute_CO2_diffusion()

        # Step 4: 血气分压更新
        # A-a gradient 随扩散能力下降而增大（正常 10，严重障碍时可达 40）
        aa_gradient = 5.0 + (1.0 - self.diffusion_coefficient / LUNG_DIFFUSION_COEFFICIENT) * 50.0  # REF: West Ch. 5 (正常 5-15 mmHg, 年轻 5)
        a_PO2 = self.alveolar_PO2 - aa_gradient
        a_PCO2 = self.alveolar_PCO2        # 动脉 PCO2 ≈ 肺泡 PCO2

        self.blood.arterial_PO2_mmHg = max(40.0, min(110.0, a_PO2))
        self.blood.arterial_PCO2_mmHg = max(15.0, min(80.0, a_PCO2))

        # Step 5: 血氧饱和度（基于 PO2，用 Hill 方程近似）
        self.blood.arterial_saturation = self._oxygen_saturation_curve(
            self.blood.arterial_PO2_mmHg)

        # Step 6: 静脉血气（由组织代谢决定，下一步由组织交换模块处理）
        # 这里保持不变，由其他器官模块更新

        # Step 7: 呼吸代偿
        self._respiratory_compensation(
            self.blood.arterial_PCO2_mmHg, self.blood.arterial_PO2_mmHg, dt)

        # Step 8: 血液 pH（由 CO2 调节，碳酸氢盐缓冲系统）
        self._update_arterial_pH()

        return {
            "alveolar_PO2": self.alveolar_PO2,
            "alveolar_PCO2": self.alveolar_PCO2,
            "arterial_PO2": self.blood.arterial_PO2_mmHg,
            "arterial_PCO2": self.blood.arterial_PCO2_mmHg,
            "arterial_saturation": self.blood.arterial_saturation,
            "respiratory_rate": self.respiratory_rate,
            "minute_ventilation": minute_ventilation,
            "O2_consumption": self.O2_consumption,
            "CO2_production": self.CO2_production,
            "V_Q_ratio": self.VQ_ratio,
            "tidal_volume_ml": self.tidal_volume,
            # Van der Pol 振荡器状态
            "vdp_amplitude": self._vdp.amplitude,
            "vdp_phase": self._vdp.phase,
            "vdp_is_inspiration": self._vdp.is_inspiration,
            "vdp_inspiration_fraction": self._vdp.inspiration_fraction,
        }

    def _oxygen_saturation_curve(self, PO2_mmHg: float, pH: float = 7.4, temperature_C: float = 38.5) -> float:
        """
        氧解离曲线（Hill 方程近似）+ Bohr+温度效应 — REF: Bohr 1904
        P50 随 pH↓ 增大 (右移, 释氧能力↑), 随 T↑ 增大
        P50_base ≈ 30 mmHg (犬, 文献 29-31; 人类 26-27)
        Phase 2 #9: 动态 P50 反映临床情况
        """
        P50_base = 30.0  # mmHg
        # Bohr 效应: 每降 1 pH 单位, P50 +3 mmHg (Bohr 系数犬约 -0.5)
        pH_effect = 3.0 * (7.4 - pH)
        # 温度效应: 每升 1°C, P50 +1.5 mmHg
        T_effect = 1.5 * (temperature_C - 38.5)
        P50 = P50_base + pH_effect + T_effect
        P50 = max(15.0, min(50.0, P50))  # clamp
        n = 2.8     # Hill 系数
        sat = PO2_mmHg**n / (P50**n + PO2_mmHg**n)
        return max(0.0, min(1.0, sat))

    def _update_arterial_pH(self):
        """
        Henderson-Hasselbalch 方程近似：
        pH = 6.1 + log10([HCO3-] / (0.03 × PCO2))
        简化：假设 [HCO3-] = 24 mEq/L
        """
        PCO2 = self.blood.arterial_PCO2_mmHg
        HCO3 = getattr(self.blood, 'HCO3', HCO3_EXTRACELLULAR_MEQ_L)
        if HCO3 < 1.0:
            HCO3 = HCO3_EXTRACELLULAR_MEQ_L
        pH = 6.1 + math.log10(HCO3 / (0.03 * PCO2)) if PCO2 > 0 else 7.4
        self.blood.arterial_pH = max(7.0, min(7.8, pH))

    def summary(self) -> dict:
        return {
            "alveolar_PO2": round(self.alveolar_PO2, 1),
            "alveolar_PCO2": round(self.alveolar_PCO2, 1),
            "arterial_PO2": round(self.blood.arterial_PO2_mmHg, 1),
            "arterial_PCO2": round(self.blood.arterial_PCO2_mmHg, 1),
            "saturation": round(self.blood.arterial_saturation, 3),
            "RR": round(self.respiratory_rate, 1),
            "pH": round(self.blood.arterial_pH, 3),
            "vdp_amplitude": round(self._vdp.amplitude, 3),
            "vdp_phase": round(self._vdp.phase, 3),
        }
