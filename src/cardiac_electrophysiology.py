"""
Cardiac Electrophysiology Module
基于 Hodgkin-Huxley (1952) 方程的心脏电生理模型

架构说明:
  本模块不模拟窦房结起搏（标准 HH 模型在 DC 刺激下无法产生生理性周期振荡），
  而是作为"电生理计算器"：
    - 心率由 HeartModule 的 baroreceptor 反馈决定
    - HH 模块接收当前心率和 [K⁺]，计算单次动作电生理响应
    - 从 h∞ 稳态推导 K⁺ 毒性因子（替代 _potassium_cardiac_effect 线性查表）
    - 生成模拟 ECG Lead II 波形

K⁺ 毒性机制（从第一性原理推导）:
  高钾 → E_K 去极化（Nernst 方程）→ 静息膜电位去极化
       → 快 Na⁺ 通道稳态失活（h∞ 下降）→ 0 期 Vmax 降低 → 传导速度↓
       → T 波高尖 → QRS 增宽 → P 波消失 → 正弦波 → 停搏
"""

from __future__ import annotations

import math


# ── 生理常数 ─────────────────────────────────────────────────────────────────

# HH 模型参数（Hodgkin & Huxley 1952，哺乳动物心肌细胞适配）
C_M = 1.0           # 膜电容 (μF/cm²)
G_NA_MAX = 120.0    # Na⁺ 最大电导 (mS/cm²)
G_K_MAX = 36.0      # K⁺ 最大电导 (mS/cm²)
G_L = 0.3           # 漏电流电导 (mS/cm²)

# 平衡电位 (mV)
E_NA = 55.0         # Na⁺（心肌细胞）
E_L = -65.0         # 漏电流

# K⁺ 正常值
K_O_NORMAL = 4.2    # 细胞外 K⁺ (mEq/L)
K_I = 140.0         # 细胞内 K⁺ (mEq/L)

# 犬正常体温
TEMP_C = 38.5


class CardiacElectrophysiology:
    """
    心脏电生理计算器

    每个 update() 调用：
      1. 根据当前 [K⁺] 计算 E_K（Nernst 方程）
      2. 根据当前心率推进动作电位仿真
      3. 从 h∞ 稳态推导 K⁺ 毒性因子
      4. 更新 ECG 波形缓冲区

    使用方式:
        cep = CardiacElectrophysiology()
        for _ in range(n_steps):
            cep.update(dt=0.01, heart_rate_bpm=85, k_ext=4.2)
        print(cep.k_toxicity_factor)
        print(cep.get_ecg_interpretation(4.2))
    """

    def __init__(self):
        # 膜电位状态（追踪一个代表性心室肌细胞）
        self.V = -85.0          # 静息膜电位 (mV)
        self.m = 0.02           # Na⁺ 激活
        self.h = 0.95           # Na⁺ 失活
        self.n = 0.05           # K⁺ 激活

        # 门控变量稳态缓存
        self._h_inf = 0.95
        self._m_inf = 0.02
        self._n_inf = 0.05

        # K⁺ 毒性因子
        self.k_toxicity_factor = 1.0

        # E_K 缓存
        self._e_k = self._nernst_k(K_O_NORMAL)

        # 当前心率（由外部设置）
        self.heart_rate = 85.0

        # 动作电位周期追踪
        self._ap_phase = 0.0    # 当前在动作电位周期中的相位 (0-1)
        self._ap_duration_ms = 250.0  # 动作电位时程 (ms)

        # ECG 波形缓冲区
        self._ecg_buffer: list[float] = []
        self._ecg_time_ms: float = 0.0

    # ── Nernst 方程 ─────────────────────────────────────────────────────────

    @staticmethod
    def _nernst_k(k_ext: float, k_int: float = K_I, temp_c: float = TEMP_C) -> float:
        """
        Nernst 方程计算 K⁺ 平衡电位
        E_K = (R·T / z·F) · ln([K⁺]_o / [K⁺]_i)
        简化（37°C）: E_K = 61.5 · log10([K⁺]_o / [K⁺]_i)
        犬体温 38.5°C: 温度修正
        """
        if k_ext <= 0 or k_int <= 0:
            return -85.0
        temp_factor = 62.1 + 0.6 * (temp_c - 37.0)
        return temp_factor * math.log10(k_ext / k_int)

    # ── HH 速率常数 ─────────────────────────────────────────────────────────

    @staticmethod
    def _alpha_m(V: float) -> float:
        dV = V + 40.0
        if abs(dV) < 1e-6:
            return 1.0
        return 0.1 * dV / (1.0 - math.exp(-dV / 10.0))

    @staticmethod
    def _beta_m(V: float) -> float:
        return 4.0 * math.exp(-(V + 65.0) / 18.0)

    @staticmethod
    def _alpha_h(V: float) -> float:
        return 0.07 * math.exp(-(V + 65.0) / 20.0)

    @staticmethod
    def _beta_h(V: float) -> float:
        return 1.0 / (1.0 + math.exp(-(V + 35.0) / 10.0))

    @staticmethod
    def _alpha_n(V: float) -> float:
        dV = V + 55.0
        if abs(dV) < 1e-6:
            return 0.1
        return 0.01 * dV / (1.0 - math.exp(-dV / 10.0))

    @staticmethod
    def _beta_n(V: float) -> float:
        return 0.125 * math.exp(-(V + 65.0) / 80.0)

    # ── 核心更新 ────────────────────────────────────────────────────────────

    def update(self, dt: float, heart_rate_bpm: float, k_ext: float = K_O_NORMAL) -> None:
        """
        推进电生理计算一个时间步

        Args:
            dt: 时间步长（秒）
            heart_rate_bpm: 当前心率 (bpm)，由 baroreceptor 反馈决定
            k_ext: 细胞外 K⁺ 浓度 (mEq/L)
        """
        self.heart_rate = heart_rate_bpm

        # 1. 计算 E_K（Nernst 方程）
        self._e_k = self._nernst_k(k_ext)

        # 2. 计算动作电位周期
        period_s = 60.0 / max(10.0, heart_rate_bpm)
        self._ap_phase += dt / period_s
        if self._ap_phase >= 1.0:
            self._ap_phase -= 1.0

        # 3. 根据动作电位相位设置膜电位和门控变量
        self._update_action_potential(period_s, k_ext)

        # 4. 计算 K⁺ 毒性因子
        self._compute_k_toxicity(k_ext)

        # 5. 更新 ECG 波形
        self._update_ecg(dt)

    def _update_action_potential(self, period_s: float, k_ext: float) -> None:
        """
        根据动作电位相位更新膜电位和门控变量

        简化但生理准确的 AP 形态：
        - 相位 0-0.02: 快速去极化（0 期，Na⁺ 内流）
        - 相位 0.02-0.08: 早期复极化（1 期，瞬时 K⁺ 外流）
        - 相位 0.08-0.25: 平台期（2 期，Ca²⁺ vs K⁺）
        - 相位 0.25-0.45: 复极化（3 期，K⁺ 外流）
        - 相位 0.45-1.0: 静息期（4 期）

        [K⁺] 升高效应（通过 HH 门控稳态计算）：
        - 静息电位去极化（E_K 更正）
        - 去极化 → h∞ 下降 → 0 期 Vmax 降低 → 传导速度↓
        """
        phase = self._ap_phase

        # 计算当前 [K⁺] 下的静息膜电位
        v_rest = self._e_k + 8.0
        v_rest = max(-95.0, min(-55.0, v_rest))

        # 计算 h∞ 在静息膜电位的值（关键：K⁺ 毒性指标）
        a_h = self._alpha_h(v_rest)
        b_h = self._beta_h(v_rest)
        self._h_inf = a_h / (a_h + b_h)

        # 计算 m∞ 和 n∞
        a_m = self._alpha_m(v_rest)
        b_m = self._beta_m(v_rest)
        self._m_inf = a_m / (a_m + b_m)
        a_n = self._alpha_n(v_rest)
        b_n = self._beta_n(v_rest)
        self._n_inf = a_n / (a_n + b_n)

        # 动作电位峰值（受 h∞ 调节——高钾时峰值降低）
        h_effect = max(0.1, min(1.0, self._h_inf / 0.6))
        v_peak = max(-20.0, 30.0 * h_effect + (-10.0) * (1.0 - h_effect))

        # 预计算各期过渡电位
        notch_v = v_peak - 15.0       # 1 期切迹电位
        plateau_start_v = notch_v     # 2 期起始电位
        plateau_end_v = -10.0         # 2 期结束电位

        # 根据相位计算膜电位和门控变量
        if phase < 0.02:
            # 0 期：快速去极化
            t = phase / 0.02
            s = self._smooth_step(t)
            self.V = v_rest + (v_peak - v_rest) * s
            self.m = 0.02 + 0.88 * s
            self.h = max(0.05, self._h_inf - 0.5 * s)
            self.n = self._n_inf
        elif phase < 0.08:
            # 1 期：早期复极化
            t = (phase - 0.02) / 0.06
            s = self._smooth_step(t)
            self.V = v_peak + (notch_v - v_peak) * s
            self.h = max(0.02, self._h_inf * 0.3 * (1.0 - t))
            self.n = 0.3 + 0.4 * t
            self.m = 0.02
        elif phase < 0.25:
            # 2 期：平台期
            t = (phase - 0.08) / 0.17
            s = self._smooth_step(t)
            self.V = plateau_start_v + (plateau_end_v - plateau_start_v) * s
            self.h = max(0.02, self._h_inf * 0.15)
            self.n = 0.5 + 0.3 * t
            self.m = 0.02
        elif phase < 0.45:
            # 3 期：复极化
            t = (phase - 0.25) / 0.20
            s = self._smooth_step(t)
            self.V = plateau_end_v + (v_rest - plateau_end_v) * s
            self.h = min(0.95, self._h_inf * (0.15 + 0.85 * t))
            self.n = 0.8 - 0.3 * t
            self.m = self._m_inf
        else:
            # 4 期：静息期
            t = (phase - 0.45) / 0.55
            self.V = v_rest
            self.h = min(0.98, self._h_inf)
            self.n = max(0.02, self._n_inf + (0.5 - self._n_inf) * (1.0 - t))
            self.m = max(0.01, self._m_inf)

    @staticmethod
    def _smooth_step(t: float) -> float:
        """平滑阶跃函数（Hermite 插值）"""
        t = max(0.0, min(1.0, t))
        return t * t * (3.0 - 2.0 * t)

    def _compute_k_toxicity(self, k_ext: float) -> None:
        """
        从 HH 第一性原理计算 K⁺ 毒性因子

        机制：
        1. 高钾 → E_K 去极化（Nernst 方程）→ 静息膜电位去极化
        2. 去极化 → Na⁺ 通道稳态失活（Boltzmann 曲线）
        3. Na⁺ 通道可用性 ↓ → 0 期 Vmax ↓ → 传导速度 ↓
        4. 传导速度 ↓ → 心率 ↓（窦房结传导阻滞）

        毒性曲线基于心肌细胞 Nav1.5 通道实验数据：
        - K⁺ 4.2: 正常（factor = 1.0）
        - K⁺ 5.5-6.5: 轻度毒性（T波高尖）
        - K⁺ 6.5-7.5: 中度毒性（QRS增宽）
        - K⁺ 7.5-8.5: 重度毒性（P波消失）
        - K⁺ > 8.5: 极重度（正弦波→停搏）

        计算方法：
        - 用 Nernst 方程计算 E_K
        - 用心肌细胞静息电位模型计算 V_rest
        - 用 Boltzmann 方程计算 Na⁺ 通道可用性（h∞）
        - 映射为毒性因子
        """
        # 计算当前 [K⁺] 下的 E_K
        ek = self._e_k
        ek_normal = self._nernst_k(K_O_NORMAL)

        # 计算静息膜电位（心肌细胞：主要由 K⁺ 电导决定）
        # V_rest ≈ E_K + δ（δ 为背景电流导致的偏移，约 5-10 mV）
        v_rest = ek + 8.0
        v_rest = max(-100.0, min(-50.0, v_rest))

        # 心肌细胞 Nav1.5 Na⁺ 通道稳态失活（Boltzmann 方程）
        # 参数来源：犬心室肌实验数据
        # V_half = -78 mV, k = +5.0 mV（正值 = 去极化时可用性下降 = 失活）
        v_half_h = -78.0   # Na⁺ 通道失活半激活电位
        k_h = 5.0          # 斜率因子（正值：去极化→h∞↓→Na⁺通道失活）
        h_inf = 1.0 / (1.0 + math.exp((v_rest - v_half_h) / k_h))

        # 正常 h∞
        v_rest_normal = ek_normal + 8.0
        h_inf_normal = 1.0 / (1.0 + math.exp((v_rest_normal - v_half_h) / k_h))

        # Na⁺ 通道可用性因子
        h_factor = max(0.0, min(1.0, h_inf / h_inf_normal))

        # E_K 去极化对窦房结起搏的直接抑制
        ek_depolarization = max(0.0, (ek - ek_normal) / 25.0)
        ek_factor = max(0.0, 1.0 - 0.9 * ek_depolarization)

        # 综合毒性因子
        # Na⁺ 通道可用性占主要权重（75%），E_K 直接效应占 25%
        self.k_toxicity_factor = max(0.02, min(1.0, 0.75 * h_factor + 0.25 * ek_factor))

    def _update_ecg(self, dt: float) -> None:
        """
        更新 ECG 波形缓冲区

        将动作电位映射为模拟 ECG Lead II 波形：
        - P 波：心房去极化（简化为小正波）
        - QRS 复合波：心室快速去极化
        - ST 段：心室平台期
        - T 波：心室复极化

        [K⁺] 升高效应：
        - T 波高尖（高钾早期）
        - QRS 增宽（高钾进展）
        - P 波消失（严重高钾）
        """
        self._ecg_time_ms += dt * 1000.0
        phase = self._ap_phase

        # 基础 ECG 波形（简化 Lead II）
        ecg_mv = 0.0

        # P 波（心房去极化，发生在 QRS 前 ~80ms）
        # 高钾时 P 波幅度降低直至消失
        p_wave_factor = max(0.0, min(1.0, self._h_inf / 0.4))  # h∞ < 0.4 时 P 波消失
        if 0.52 < phase < 0.58:
            t = (phase - 0.52) / 0.06
            ecg_mv += 0.1 * p_wave_factor * math.sin(math.pi * t)

        # QRS 复合波（心室去极化）
        if phase < 0.06:
            if phase < 0.02:
                # Q 波（初始负向）
                t = phase / 0.02
                ecg_mv += -0.1 * self._smooth_step(t)
            elif phase < 0.04:
                # R 波（主峰）
                t = (phase - 0.02) / 0.02
                # R 波幅度受 h∞ 调节（高钾时幅度降低）
                r_amplitude = 1.0 * max(0.2, min(1.0, self._h_inf / 0.5))
                ecg_mv += r_amplitude * math.sin(math.pi * t)
            else:
                # S 波（终末负向）
                t = (phase - 0.04) / 0.02
                ecg_mv += -0.2 * self._smooth_step(t)

        # ST 段 + T 波（复极化）
        if 0.25 < phase < 0.45:
            t = (phase - 0.25) / 0.20
            # T 波幅度受 [K⁺] 调节（高钾时 T 波高尖）
            ek_normal = self._nernst_k(K_O_NORMAL)
            depolarization = self._e_k - ek_normal
            # 高钾 → T 波高尖
            t_amplitude = 0.2 + 0.3 * max(0.0, depolarization / 20.0)
            t_amplitude = min(0.6, t_amplitude)
            ecg_mv += t_amplitude * math.sin(math.pi * t)

        # QRS 增宽效应（高钾时 QRS 增宽）
        # 通过降低高频分量实现
        if phase < 0.06:
            qrs_broadening = max(0.0, (0.5 - self._h_inf) / 0.5)  # h∞ < 0.5 时增宽
            ecg_mv *= (1.0 - 0.3 * qrs_broadening)  # 增宽时幅度略降

        self._ecg_buffer.append(ecg_mv)

        # 限制缓冲区大小（保留最近 3 秒）
        max_len = int(3.0 / dt)
        if len(self._ecg_buffer) > max_len:
            self._ecg_buffer = self._ecg_buffer[-max_len:]

    def get_ecg_waveform(self, duration_ms: float = 2000.0, dt: float = 0.1) -> list[dict]:
        """
        返回最近 duration_ms 毫秒的 ECG 波形数据

        Returns:
            [{"t_ms": float, "mV": float}, ...]
        """
        n_points = int(duration_ms / dt)
        buf = self._ecg_buffer[-n_points:] if len(self._ecg_buffer) > n_points else self._ecg_buffer
        t_start = self._ecg_time_ms - len(buf) * dt
        return [
            {"t_ms": round(t_start + i * dt, 1), "mV": round(v, 4)}
            for i, v in enumerate(buf)
        ]

    def get_ecg_interpretation(self, k_ext: float = K_O_NORMAL) -> dict:
        """
        返回 ECG 的临床解读数据（基于 HH 第一性原理）

        Returns:
            {
                "heart_rate_bpm": float,
                "rhythm": str,
                "t_wave_amplitude": str,
                "qrs_width": str,
                "p_wave": str,
                "k_toxicity_stage": str,
                "h_inf": float,
                "e_k": float,
            }
        """
        hr = self.heart_rate
        h_inf = self._h_inf
        e_k = self._e_k

        # 节律判断
        if hr > 140:
            rhythm = "sinus_tachycardia"
        elif hr < 60:
            rhythm = "sinus_bradycardia"
        else:
            rhythm = "normal_sinus"

        # T 波振幅（高钾 → T 波高尖）
        ek_normal = self._nernst_k(K_O_NORMAL)
        depolarization = e_k - ek_normal
        if depolarization > 15:
            t_wave = "tall_peaked"
        elif depolarization > 8:
            t_wave = "tall"
        else:
            t_wave = "normal"

        # QRS 宽度（高钾 → QRS 增宽）
        if h_inf < 0.2:
            qrs = "very_wide"
        elif h_inf < 0.35:
            qrs = "wide"
        elif h_inf < 0.5:
            qrs = "slightly_wide"
        else:
            qrs = "normal"

        # P 波（高钾 → P 波消失）
        if h_inf < 0.25:
            p_wave = "absent"
        elif h_inf < 0.4:
            p_wave = "variable"
        else:
            p_wave = "present"

        # K⁺ 毒性分期
        k = k_ext
        if k <= 5.5:
            k_stage = "none"
        elif k <= 6.5:
            k_stage = "mild"
        elif k <= 7.5:
            k_stage = "moderate"
        elif k <= 8.5:
            k_stage = "severe"
        else:
            k_stage = "critical"

        return {
            "heart_rate_bpm": round(hr, 1),
            "rhythm": rhythm,
            "t_wave_amplitude": t_wave,
            "qrs_width": qrs,
            "p_wave": p_wave,
            "k_toxicity_stage": k_stage,
            "h_inf": round(h_inf, 3),
            "e_k": round(e_k, 1),
        }
