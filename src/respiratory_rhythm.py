"""
Respiratory Rhythm Generator — Van der Pol Oscillator Model

基于 Van der Pol (1926) 方程的呼吸中枢节律发生器模型。

生理背景：
  呼吸节律由延髓 pre-Bötzinger 复合体产生，本质上是自持振荡器。
  Van der Pol 方程是最简单的自持振荡器模型：
    x'' - μ(1 - x²)x' + x = 0
  其中：
    x — 振荡变量（映射为呼吸幅度/驱动信号）
    μ — 非线性阻尼系数（控制振荡强度和波形）
    当 |x| < 1 时，负阻尼 → 幅度增长
    当 |x| > 1 时，正阻尼 → 幅度衰减
    最终稳定为极限环振荡

与生理的映射：
    x > 0 → 吸气相（inspiration）
    x < 0 → 呼气相（expiration）
    |x| 峰值 → 呼吸深度
    振荡频率 → 呼吸频率（RR）

化学感受器驱动：
    PCO2↑ → 频率加快 + 幅度增大（通过中枢化学感受器）
    PO2↓  → 频率加快（通过外周化学感受器，阈值 ~80 mmHg）
    代谢性酸中毒 → 频率加快（Kussmaul 呼吸）

Van der Pol 参数生理校准（犬）：
    μ = 1.5（正常呼吸波形，适度非线性）
    ω₀ = 2π × (18/60) ≈ 1.885 rad/s（静息 RR = 18/min）
    驱动增益：PCO2 每升高 1 mmHg → ω₀ 增加 ~2%

参考：
    Van der Pol, B. (1926). "On relaxation-oscillations". Philosophical Magazine.
    Feldman, J.L. & Del Negro, C.A. (2006). "Looking for inspiration: new perspectives
        on respiratory rhythm". Nature Reviews Neuroscience 7:232-242.
"""

from __future__ import annotations

import math

# ── 生理常数 ──────────────────────────────────────────────────────────────────

# 犬静息呼吸频率
RR_REST_HZ = 18.0 / 60.0          # 18/min → 0.3 Hz
RR_STRESS_HZ = 40.0 / 60.0       # 40/min → 0.667 Hz

# Van der Pol 参数
MU_NORMAL = 1.5                    # 非线性阻尼系数（正常呼吸波形）
MU_DEEP = 3.0                      # 深呼吸/酸中毒时（Kussmaul 呼吸）
MU_SHALLOW = 0.8                   # 浅快呼吸（肺顺应性降低时）

# 化学感受器驱动增益
PCO2_DRIVE_GAIN = 0.008            # PCO2 每升高 1 mmHg → 频率增加 0.8%（生理：严重高碳酸血症 RR约增加 50-80%）
PO2_DRIVE_THRESHOLD = 80.0         # 低氧驱动阈值 (mmHg)
PO2_DRIVE_GAIN = 0.04              # PO2 每降低 1 mmHg → 频率增加 4%（外周化学感受器）
PH_DRIVE_GAIN = 0.8                # pH 每降低 0.1 → 频率增加 80%（Kussmaul 呼吸）

# 呼气/吸气时间比（正常 I:E ≈ 1:1.5）
IE_RATIO_EXPIRATION = 1.5          # 呼气时长 = 吸气 × 1.5


class VanDerPolRespiratoryRhythm:
    """
    Van der Pol 呼吸节律振荡器

    每个 update() 调用：
      1. 根据化学感受器驱动更新目标频率
      2. 推进 Van der Pol 方程一个时间步
      3. 从振荡状态推导呼吸频率和深度

    使用方式:
        vdp = VanDerPolRespiratoryRhythm(dt=0.01)
        for _ in range(n_steps):
            vdp.update(pco2=40.0, po2=95.0, ph=7.40)
        print(vdp.respiratory_rate)  # → ~18 /min
        print(vdp.inspiration_fraction)  # → ~0.4 (吸气占周期比例)
    """

    def __init__(self, dt: float = 0.01, rr_rest: float = RR_REST_HZ):
        self.dt = dt
        self.rr_rest_hz = rr_rest

        # Van der Pol 参数
        self.mu = MU_NORMAL
        self.omega = 2.0 * math.pi * rr_rest  # 固有角频率

        # Van der Pol 状态变量
        # x: 振荡位移（吸气相 > 0，呼气相 < 0）
        # v: 振荡速度（dx/dt）
        #
        # 初始状态设在极限环上（避免收敛瞬态影响生理仿真）
        # VdP 极限环幅值 ≈ 2.0（μ=1.5 时），用余弦初始化：
        #   x(t) ≈ A·cos(ωt), v(t) = dx/dt ≈ -A·ω·sin(ωt)
        # 从 t=0 开始：x=A, v=0（吸气峰值）
        vdp_amplitude = 2.0  # 极限环幅值近似
        self.x = vdp_amplitude   # 初始在吸气峰值
        self.v = 0.0             # 初始速度为零（峰值处）

        # 输出状态
        self.respiratory_rate_hz = rr_rest    # 当前呼吸频率 (Hz)
        self.respiratory_rate = rr_rest * 60.0  # 当前呼吸频率 (/min)
        self.inspiration_fraction = 0.4       # 吸气占周期比例
        self.amplitude = vdp_amplitude        # 振荡幅度（映射为呼吸深度）
        self.phase = 0.0                      # 当前呼吸相位 (0-1)

        # 周期追踪
        self._last_zero_cross_positive = True  # 上一次过零点方向
        self._period_estimate = 1.0 / rr_rest  # 周期估计 (s)
        self._cycle_count = 0                  # 完整周期计数
        self._last_phase = 0.0

        # 驱动信号
        self._target_omega = self.omega
        self._target_mu = self.mu

    def update(self, pco2: float = 40.0, po2: float = 95.0, ph: float = 7.40) -> None:
        """
        推进呼吸节律一个时间步

        Args:
            pco2: 动脉 PCO2 (mmHg)，正常 ~40
            po2: 动脉 PO2 (mmHg)，正常 ~95
            ph: 动脉 pH，正常 ~7.40
        """
        # 1. 计算化学感受器驱动
        self._compute_chemoreceptor_drive(pco2, po2, ph)

        # 2. 平滑更新 VdP 参数（避免突变）
        alpha = min(1.0, self.dt / 5.0)  # 5s 时间常数（与 RR 代偿同步）
        self.omega += (self._target_omega - self.omega) * alpha
        self.mu += (self._target_mu - self.mu) * alpha

        # 3. 积分 Van der Pol 方程（四阶 Runge-Kutta）
        self._rk4_step()

        # 4. 从振荡状态推导输出
        self._update_output()

    def _compute_chemoreceptor_drive(self, pco2: float, po2: float, ph: float) -> None:
        """
        化学感受器驱动 → VdP 参数映射

        生理映射：
        - PCO2↑ → 频率加快 + 幅度增大（中枢化学感受器主导）
        - PO2↓  → 频率加快（外周化学感受器，阈值效应）
        - pH↓   → 频率加快 + 幅度增大（Kussmaul 呼吸）
        """
        omega = 2.0 * math.pi * self.rr_rest_hz
        mu = MU_NORMAL

        # PCO2 驱动（中枢化学感受器，线性响应）
        pco2_error = pco2 - 40.0
        if pco2_error > 0:
            omega *= (1.0 + PCO2_DRIVE_GAIN * pco2_error)
            mu = min(MU_DEEP, mu + 0.02 * pco2_error)  # 更慢的深度响应（避免Kussmaul过度触发）
        elif pco2_error < -10:
            # 过度通气 → 呼吸抑制
            omega *= max(0.5, 1.0 + 0.015 * pco2_error)
            mu = max(MU_SHALLOW, mu + 0.03 * pco2_error)

        # PO2 驱动（外周化学感受器，阈值效应）
        if po2 < PO2_DRIVE_THRESHOLD:
            hypoxic_drive = (PO2_DRIVE_THRESHOLD - po2) / PO2_DRIVE_THRESHOLD
            omega *= (1.0 + PO2_DRIVE_GAIN * hypoxic_drive * 10.0)
            mu = min(MU_DEEP, mu + 0.1 * hypoxic_drive)

        # pH 驱动（代谢性酸中毒 → Kussmaul 呼吸）
        ph_error = 7.40 - ph
        if ph_error > 0.05:
            omega *= (1.0 + PH_DRIVE_GAIN * ph_error)
            mu = min(MU_DEEP, mu + 0.5 * ph_error)

        self._target_omega = omega
        self._target_mu = mu

    def _rk4_step(self) -> None:
        """
        四阶 Runge-Kutta 积分 Van der Pol 方程

        Van der Pol: x'' - μ(1 - x²)x' + ω²x = 0
        令 v = x'，化为状态方程：
          x' = v
          v' = μ(1 - x²)v - ω²x
        """
        dt = self.dt
        mu = self.mu
        w2 = self.omega ** 2

        x, v = self.x, self.v

        # k1
        k1x = v
        k1v = mu * (1.0 - x * x) * v - w2 * x

        # k2
        x2 = x + 0.5 * dt * k1x
        v2 = v + 0.5 * dt * k1v
        k2x = v2
        k2v = mu * (1.0 - x2 * x2) * v2 - w2 * x2

        # k3
        x3 = x + 0.5 * dt * k2x
        v3 = v + 0.5 * dt * k2v
        k3x = v3
        k3v = mu * (1.0 - x3 * x3) * v3 - w2 * x3

        # k4
        x4 = x + dt * k3x
        v4 = v + dt * k3v
        k4x = v4
        k4v = mu * (1.0 - x4 * x4) * v4 - w2 * x4

        # Update
        self.x += (dt / 6.0) * (k1x + 2.0 * k2x + 2.0 * k3x + k4x)
        self.v += (dt / 6.0) * (k1v + 2.0 * k2v + 2.0 * k3v + k4v)

        # 幅度限幅（防止数值发散）
        max_amp = 3.0
        if abs(self.x) > max_amp:
            self.x = max_amp * (1.0 if self.x > 0 else -1.0)
            self.v *= 0.5

    def _update_output(self) -> None:
        """从振荡状态推导呼吸频率和深度"""
        # 过零点检测（正过零 = 吸气开始）
        current_positive = self.x >= 0.0
        if current_positive and not self._last_zero_cross_positive:
            # 正过零 → 新周期开始
            self._cycle_count += 1

        self._last_zero_cross_positive = current_positive

        # 振荡频率估计（从 ω 直接推导，比过零计数更稳定）
        self.respiratory_rate_hz = self.omega / (2.0 * math.pi)
        self.respiratory_rate = self.respiratory_rate_hz * 60.0

        # 振荡幅度（滑动窗口 RMS 估计）
        instant_amp = math.sqrt(self.x ** 2 + (self.v / self.omega) ** 2)
        alpha_amp = self.dt / 0.1  # 100ms 平滑
        self.amplitude += (instant_amp - self.amplitude) * alpha_amp

        # 呼吸相位 (0-1)
        # 用 x 的符号和 v 的符号判断：
        # x>0, v>0 → 吸气早期 (0-0.25)
        # x>0, v<0 → 吸气后期 (0.25-0.5)
        # x<0, v<0 → 呼气早期 (0.5-0.75)
        # x<0, v>0 → 呼气后期 (0.75-1.0)
        raw_phase = math.atan2(-self.v / max(self.omega, 0.01), self.x) / (2.0 * math.pi)
        if raw_phase < 0:
            raw_phase += 1.0
        self.phase = raw_phase

        # 吸气占周期比例（正常 ~0.4，即 I:E ≈ 1:1.5）
        # 频率越快，吸气比例略增
        rr_ratio = self.respiratory_rate / 18.0
        self.inspiration_fraction = min(0.55, 0.35 + 0.02 * max(0, rr_ratio - 1.0))

    @property
    def is_inspiration(self) -> bool:
        """当前是否在吸气相"""
        return self.x >= 0.0

    @property
    def is_expiration(self) -> bool:
        """当前是否在呼气相"""
        return self.x < 0.0

    @property
    def inspiration_depth(self) -> float:
        """
        吸气深度因子 (0-1)
        用于调制潮气量
        """
        if self.x < 0:
            return 0.0
        return min(1.0, self.x / 1.5)  # 归一化到典型峰值

    def get_state(self) -> dict:
        """返回当前振荡状态"""
        return {
            "respiratory_rate": round(self.respiratory_rate, 1),
            "respiratory_rate_hz": round(self.respiratory_rate_hz, 3),
            "amplitude": round(self.amplitude, 3),
            "phase": round(self.phase, 3),
            "is_inspiration": self.is_inspiration,
            "inspiration_fraction": round(self.inspiration_fraction, 3),
            "mu": round(self.mu, 2),
            "omega": round(self.omega, 2),
        }
