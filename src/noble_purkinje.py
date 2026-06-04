"""
Noble 1962 Purkinje Fiber Model

基于 Noble (1962) 的浦肯野纤维动作电位模型，扩展 Hodgkin-Huxley 框架。

与标准 HH 的关键区别：
  1. 增加慢内向 Ca²⁺ 电流（ICaL）→ 产生平台期
  2. 增加时间依赖性 K⁺ 电流（IK）→ 更真实的复极化
  3. 增加超极化激活的起搏电流（If）→ 浦肯野纤维固有节律
  4. 细胞外 K⁺ 浓度对 IK1 整流的影响 → 高钾时传导减慢

生理背景：
  浦肯野纤维是心室传导系统的末端，负责将电冲动快速传导至心室肌。
  其动作电位时程（APD）比心室肌长（~400ms vs ~250ms），具有：
  - 快速 0 期去极化（Na⁺ 通道，Vmax 高）
  - 明显平台期（Ca²⁺ 通道）
  - 较长复极化（K⁺ 通道）
  - 4 期自动去搏（If 通道，频率 20-40 bpm）

高钾对浦肯野纤维的影响：
  - IK1 整流减弱 → 静息电位去极化
  - Na⁺ 通道可用性降低 → 0 期 Vmax 降低 → 传导速度减慢
  - 4 期自动去极化减慢 → 逸搏节律减慢
  - 最终 → 传导阻滞 + 停搏

参考：
    Noble, D. (1962). "A modification of the Hodgkin-Huxley equations
        applicable to Purkinje fibre action and pacemaker potentials".
    Journal of Physiology 160:317-352.
"""

from __future__ import annotations

import math
from src.cardiac_electrophysiology import (
    CardiacElectrophysiology,
    C_M, G_NA_MAX, G_K_MAX, G_L, E_NA, E_L,
    K_O_NORMAL, K_I, TEMP_C,
)


# ── Noble 1962 浦肯野纤维额外参数 ────────────────────────────────────────────

# Ca²⁺ 通道参数（慢内向电流 ICaL）
G_CAL = 0.15        # Ca²⁺ 最大电导 (mS/cm²)
E_CA = 70.0         # Ca²⁺ 平衡电位 (mV)
CA_ACT_TAU = 3.0    # Ca²⁺ 激活时间常数 (ms)
CA_INACT_TAU = 80.0 # Ca²⁺ 失活时间常数 (ms)

# 时间依赖性 K⁺ 电流参数（IK，替代 HH 的 n⁴ 模型）
G_K_NOBLE = 0.6     # K⁺ 最大电导 (mS/cm²)
K_ACT_TAU = 300.0   # K⁺ 激活时间常数 (ms)

# 起搏电流 If（超极化激活的 Na⁺/K⁺ 混合电流）
G_F = 0.05          # If 最大电导 (mS/cm²)
E_F = -20.0         # If 逆转电位 (mV)
F_ACT_TAU = 500.0   # If 激活时间常数 (ms)

# 浦肯野纤维固有频率
PURKINJE_INTRINSIC_HZ = 30.0 / 60.0  # 30 bpm → 0.5 Hz

# 传导速度参数
CONDUCTION_VELOCITY_MAX = 5.0   # 最大传导速度 (m/s) — REF: Noble 1962
PR_INTERVAL_NORMAL_MS = 80.0    # 正常 PR 间期 (ms)


class NoblePurkinjeFiber(CardiacElectrophysiology):
    """
    Noble 1962 浦肯野纤维模型

    继承 CardiacElectrophysiology（HH 基础），增加：
    - 慢内向 Ca²⁺ 电流 → 平台期
    - 时间依赖性 K⁺ 电流 → 复极化
    - 起搏电流 If → 4 期自动去极化
    - 传导速度计算 → PR 间期、QRS 宽度

    使用方式:
        npf = NoblePurkinjeFiber()
        for _ in range(n_steps):
            npf.update(dt=0.01, heart_rate_bpm=85, k_ext=4.2)
        print(npf.conduction_velocity)  # m/s
        print(npf.pr_interval_ms)       # ms
        print(npf.get_av_interpretation(k_ext=4.2))
    """

    def __init__(self):
        super().__init__()

        # Noble 额外门控变量
        self.d = 0.01       # Ca²⁺ 激活
        self.f = 0.95       # Ca²⁺ 失活
        self.p = 0.01       # K⁺ 激活（Noble 模型）
        self.q = 0.05       # If 通道激活

        # 浦肯野纤维特异性状态
        self.conduction_velocity = CONDUCTION_VELOCITY_MAX  # m/s
        self.pr_interval_ms = PR_INTERVAL_NORMAL_MS          # ms
        self.qrs_width_ms = 60.0                             # ms
        self.av_block_degree = 0                             # 0=正常, 1=一度, 2=二度, 3=三度

        # 起搏状态
        self._pacemaker_phase = 0.0     # 起搏相位
        self._intrinsic_rate_hz = PURKINJE_INTRINSIC_HZ

        # 细胞内 Na⁺/K⁺ 浓度（影响起搏）
        self._na_i = 10.0   # 细胞内 Na⁺ (mEq/L)

    def update(self, dt: float, heart_rate_bpm: float, k_ext: float = K_O_NORMAL) -> None:
        """
        推进浦肯野纤维电生理一个时间步

        Args:
            dt: 时间步长（秒）
            heart_rate_bpm: 当前心率 (bpm)
            k_ext: 细胞外 K⁺ 浓度 (mEq/L)
        """
        # 调用父类 HH 更新（基础电生理）
        super().update(dt, heart_rate_bpm, k_ext)

        # Noble 扩展更新
        self._update_noble_gates(dt, k_ext)
        self._update_conduction_velocity(k_ext)
        self._update_av_intervals(k_ext)
        self._update_pacemaker(dt, k_ext)

    def _update_noble_gates(self, dt: float, k_ext: float) -> None:
        """
        更新 Noble 模型额外门控变量

        Ca²⁺ 通道 (d, f):
          dd/dt = (d_inf - d) / tau_d
          df/dt = (f_inf - f) / tau_f

        K⁺ 通道 (p):
          dp/dt = (p_inf - p) / tau_p

        起搏通道 (q):
          dq/dt = (q_inf - q) / tau_q
        """
        V = self.V

        # Ca²⁺ 激活 d
        d_inf = 1.0 / (1.0 + math.exp(-(V + 10.0) / 6.0))
        tau_d = CA_ACT_TAU
        self.d += (d_inf - self.d) * min(1.0, dt * 1000.0 / tau_d)

        # Ca²⁺ 失活 f
        f_inf = 1.0 / (1.0 + math.exp((V + 30.0) / 7.0))
        tau_f = CA_INACT_TAU
        self.f += (f_inf - self.f) * min(1.0, dt * 1000.0 / tau_f)

        # Noble K⁺ 通道 p
        p_inf = 1.0 / (1.0 + math.exp(-(V + 20.0) / 10.0))
        tau_p = K_ACT_TAU
        self.p += (p_inf - self.p) * min(1.0, dt * 1000.0 / tau_p)

        # 起搏通道 q（If，超极化激活）
        # 高钾时 If 被抑制（膜电位去极化 → q_inf 降低）
        q_inf = 1.0 / (1.0 + math.exp((V + 70.0) / 6.0))
        tau_q = F_ACT_TAU
        self.q += (q_inf - self.q) * min(1.0, dt * 1000.0 / tau_q)

    def _update_conduction_velocity(self, k_ext: float) -> None:
        """
        计算浦肯野纤维传导速度

        传导速度 ∝ 0 期 Vmax ∝ Na⁺ 通道可用性（h∞）

        使用与 _compute_k_toxicity 相同的 Boltzmann 参数计算 h∞，
        确保传导速度评估与 K⁺ 毒性因子一致。

        高钾时：
        - 静息电位去极化 → h∞ 下降 → Vmax 降低 → 传导减慢
        - 严重高钾 → 传导阻滞
        """
        # 用 Boltzmann 方程计算 Na⁺ 通道可用性（与 _compute_k_toxicity 一致）
        ek = self._nernst_k(k_ext)
        ek_normal = self._nernst_k(K_O_NORMAL)
        v_rest = ek + 8.0
        v_rest = max(-100.0, min(-50.0, v_rest))

        # Nav1.5 稳态失活 Boltzmann 参数（与 _compute_k_toxicity 相同）
        v_half_h = -78.0
        k_h = 5.0
        h_inf = 1.0 / (1.0 + math.exp((v_rest - v_half_h) / k_h))

        # Na⁺ 通道可用性 → 传导速度映射
        # h_inf > 0.5: 正常传导
        # h_inf 0.3-0.5: 传导减慢（一度 AVB）
        # h_inf 0.1-0.3: 严重减慢（二度 AVB）
        # h_inf < 0.1: 三度 AVB（完全阻滞）
        na_availability = max(0.0, min(1.0, h_inf))

        # 传导速度（Sigmoid 映射）
        self.conduction_velocity = CONDUCTION_VELOCITY_MAX * (
            1.0 / (1.0 + math.exp(-20.0 * (na_availability - 0.3)))
        )

        # AV 阻滞分级
        if na_availability > 0.5:
            self.av_block_degree = 0   # 正常
        elif na_availability > 0.3:
            self.av_block_degree = 1   # 一度 AVB（PR 延长）
        elif na_availability > 0.1:
            self.av_block_degree = 2   # 二度 AVB（间歇性传导中断）
        else:
            self.av_block_degree = 3   # 三度 AVB（完全阻滞）

    def _update_av_intervals(self, k_ext: float) -> None:
        """
        更新 PR 间期和 QRS 宽度

        使用 Boltzmann h_inf（与 _update_conduction_velocity 一致）
        """
        # 用 Boltzmann 计算 Na⁺ 通道可用性
        ek = self._nernst_k(k_ext)
        v_rest = ek + 8.0
        v_rest = max(-100.0, min(-50.0, v_rest))
        v_half_h = -78.0
        k_h = 5.0
        h_inf = 1.0 / (1.0 + math.exp((v_rest - v_half_h) / k_h))

        # PR 间期：随 h_inf 降低而延长（正常 80ms）
        pr_factor = max(1.0, 1.0 / max(0.05, h_inf))
        self.pr_interval_ms = PR_INTERVAL_NORMAL_MS * pr_factor
        self.pr_interval_ms = min(400.0, self.pr_interval_ms)

        # QRS 宽度：随 h_inf 降低而增宽（正常 60ms）
        qrs_factor = max(1.0, 1.0 / max(0.1, h_inf))
        self.qrs_width_ms = 60.0 * qrs_factor
        self.qrs_width_ms = min(200.0, self.qrs_width_ms)

    def _update_pacemaker(self, dt: float, k_ext: float) -> None:
        """
        浦肯野纤维起搏电流（If）驱动的固有节律

        当心房传导完全阻滞时，浦肯野纤维作为逸搏起搏点接管心率。
        If 电流在高钾时被抑制 → 逸搏频率减慢。
        """
        # If 驱动 4 期自动去极化
        if_drive = self.q

        # 高钾抑制 If（通过 h_inf 映射）
        ek = self._nernst_k(k_ext)
        ek_normal = self._nernst_k(K_O_NORMAL)
        k_suppression = max(0.0, min(1.0, (ek - ek_normal) / 25.0))

        # 固有频率（If 驱动）
        self._intrinsic_rate_hz = PURKINJE_INTRINSIC_HZ * if_drive * (1.0 - 0.9 * k_suppression)
        self._intrinsic_rate_hz = max(0.05, self._intrinsic_rate_hz)  # 最低 ~3 bpm

    def get_av_interpretation(self, k_ext: float = K_O_NORMAL) -> dict:
        """
        返回房室传导系统临床解读

        Returns:
            {
                "conduction_velocity": float,    # m/s
                "pr_interval_ms": float,         # ms
                "qrs_width_ms": float,           # ms
                "av_block_degree": int,          # 0-3
                "av_block_description": str,
                "purkinje_intrinsic_rate_bpm": float,
                "h_inf": float,
            }
        """
        av_desc = {
            0: "normal_conduction",
            1: "first_degree_avb",
            2: "second_degree_avb",
            3: "third_degree_avb",
        }

        return {
            "conduction_velocity": round(self.conduction_velocity, 2),
            "pr_interval_ms": round(self.pr_interval_ms, 1),
            "qrs_width_ms": round(self.qrs_width_ms, 1),
            "av_block_degree": self.av_block_degree,
            "av_block_description": av_desc[self.av_block_degree],
            "purkinje_intrinsic_rate_bpm": round(self._intrinsic_rate_hz * 60.0, 1),
            "h_inf": round(self._h_inf, 3),
        }
