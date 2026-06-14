"""
Heart Module - 心血管循环系统（修正版）
建模心脏泵血、血管阻力、血压调节

核心方程（修正）：
  MAP = MAP_rest + (CO / 60) × SVR
  MAP_rest ≈ 60 mmHg（基础血管张力）
  CO = HR × SV

压力感受器反馈：
  MAP ↓ → 交感神经 ↑ → HR ↑ + SVR ↑（代偿）
  MAP ↑ → 副交感神经 ↑ → HR ↓（降压）

电生理（Hodgkin-Huxley）：
  心率由 HH 模块从第一性原理推导，替代线性查表。
  K⁺ 毒性由 HH 的 h∞ 稳态推导，替代 _potassium_cardiac_effect()。
"""

import math

from parameters import *
from src.cardiac_electrophysiology import CardiacElectrophysiology
from src.noble_purkinje import NoblePurkinjeFiber
from src.organ_guard import organ_setattr, _blood_escape


class HeartModule:

    # P1(2026-06-13): physical enforcement of FactorCommand-only writes
    __setattr__ = organ_setattr

    # ── Phase 5: I/O contract (declarative, no behavior change) ────────
    INPUTS: tuple[str, ...] = ('svr_factor', 'chemoreceptor_drive', 'T3_factor', 'K_potassium_mEq_L')
    OUTPUTS: tuple[str, ...] = ('cardiac_output', 'MAP', 'CVP', 'stroke_volume', 'preload_factor')
    READS_BLOOD: tuple[str, ...] = ('arterial_pH', 'potassium_mEq_L', 'arterial_PCO2_mmHg', 'arterial_PO2_mmHg')
    WRITES_BLOOD: tuple[str, ...] = ()

    # ── Step 2 (solver-refactor-roadmap-v3): ODE state declaration ──────
    # Each tuple is (ode_name, attr_name):
    #   - ode_name: logical name entering the unified y-vector (stable contract
    #     consumed by src/engine/state_vector.py; renaming breaks pack/unpack).
    #   - attr_name: the instance attribute holding the value.
    # Declared here (not in a central table) so the module owns its own ODE
    # state surface — adding a state var is now a 1-place edit.
    STATE_VARS: tuple[tuple[str, str], ...] = (
        ("HR", "heart_rate"),
        ("SV", "stroke_volume"),
        ("SVR", "SVR"),
        ("blood_volume", "circulating_volume_ml"),
        ("sympathetic", "sympathetic"),
        ("parasympathetic", "parasympathetic"),
    )
    """
    心血管模块：模拟心脏泵血功能与血压调节
    状态变量：HR, SV, MAP, CVP, blood_volume

    derivatives() 方法为 P0-B（统一 Radau 求解器）提供导数。
    compute() 保持向后兼容（Euler 步进，供 step() 使用）。
    """

    def __init__(
        self,
        weight_kg: float,
        blood,
        HR_rest: float = HEART_RATE_REST_BPM,
        HR_max: float = HEART_RATE_STRESS_BPM,
        sv_ml: float = None,
        base_co_ml_min: float = None,
        SVR: float = SYSTEMIC_VASCULAR_RESISTANCE,
        MAP_target: float = MEAN_ARTERIAL_PRESSURE_MMHG,
    ):
        self.w = weight_kg
        with _blood_escape(HeartModule):
            self.blood = blood

        # 心率参数
        self.HR_rest = HR_rest
        self.HR_max = HR_max
        self.heart_rate = HR_rest

        # 每搏输出量
        _sv = sv_ml if sv_ml is not None else 1.0 * weight_kg
        self.base_SV = _sv
        self.stroke_volume = _sv

        # 血管阻力
        # 校准：MAP = CVP + CO/60 × SVR  (Guyton C2, Ch.14)
        # CVP = central venous pressure (outflow pressure of systemic circuit)
        # SVR = (MAP_target - CVP) / (CO_baseline/60)，单位 mmHg·s/mL
        # 例：SVR = (100-4) / (1700/60) = 3.39 mmHg·s/mL
        CO_baseline_mL_min = HEART_RATE_REST_BPM * stroke_volume_ml(self.w)  # 85 × 20 = 1700 mL/min
        self.SVR = (MEAN_ARTERIAL_PRESSURE_MMHG - CENTRAL_VENOUS_PRESSURE_MMHG) / (CO_baseline_mL_min / 60.0)
        self.SVR_baseline = self.SVR
        self.SVR_max = self.SVR * 3.0

        # 血压
        self.MAP_baseline = CENTRAL_VENOUS_PRESSURE_MMHG  # CVP as outflow pressure (Guyton C2)
        self.MAP_target = MAP_target
        self.mean_arterial_pressure = MAP_target
        self.central_venous_pressure = CENTRAL_VENOUS_PRESSURE_MMHG
        self.pulmonary_arterial_pressure = PULMONARY_ARTERIAL_PRESSURE_MMHG

        # 血液动力学
        self.cardiac_output = self.heart_rate * self.stroke_volume

        # 循环血量
        self.total_BV = total_blood_volume_ml(weight_kg)
        self.circulating_volume_ml = self.total_BV

        # 交感/副交感活动（0-1）
        self.sympathetic = SYMPATHETIC_BASELINE
        self.parasympathetic = 0.7

        # 收缩力因子（由 ToxicologyModule 调制，1.0 = 正常）
        self.contractility_factor = 1.0

        # 前负荷因子（由心包积液等疾病调制，1.0 = 正常）
        # 心包积液 → 舒张期心脏受压 → 前负荷下降 → SV 下降（不是收缩力问题）
        # 公式：effective_target = target_SV × contractility_factor × preload_factor
        self.preload_factor = 1.0

        # 失血/输液累计
        self.blood_loss_ml = 0.0
        self.fluid_infused_ml = 0.0

        # 电生理计算器（Noble 1962 浦肯野纤维，扩展 HH）
        self.hh = NoblePurkinjeFiber()

    def _post_unpack_state(self) -> None:
        """Re-sync mean_arterial_pressure after the Radau path unpacks STATE_VARS.

        Step 2 (solver-refactor-roadmap-v3): extracted verbatim from the old
        if-vname=='blood_volume' branch in state_vector.unpack_state. MAP is
        not itself an ODE state var (not in STATE_VARS), but it is a low-pass-
        filtered function of the unpacked HR/SV/SVR/blood_volume. Must run
        AFTER all heart STATE_VARS are unpacked (needs vol_ratio from
        circulating_volume_ml). Called by state_vector.unpack_state via the
        optional `_post_unpack_state` hook protocol.
        """
        CO = self.heart_rate * self.stroke_volume
        vol_ratio = self.circulating_volume_ml / self.total_BV
        MAP_base = self.MAP_baseline
        raw_MAP = MAP_base + (CO / 60.0) * self.SVR
        if vol_ratio < 0.7:
            raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)
        raw_MAP = max(30.0, min(180.0, raw_MAP))
        self.mean_arterial_pressure = raw_MAP  # 直接赋值，无状态记忆

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: HR, SV, SVR
    # 输出变量（供其他模块）: CO, MAP, CVP, PAP

    def derivatives(self, dt: float, svr_factor: float = 1.0, blood_loss_rate_ml_s: float = 0.0) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        不修改任何内部状态，只返回数学导数。

        Args:
            dt: 时间步长（秒），供低通滤波 time constant 计算用
            svr_factor: 外部 SVR 倍数（ToxicologyModule 输出，1.0 = 无调制）
            blood_loss_rate_ml_s: 当前失血率（mL/s），由连续失血模型提供

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        # ── 0. 诊断：检测 dt=1e-9（Pure Euler / convergence study 路径）
        # if dt < 1e-6:
        #     vol_ratio = self.circulating_volume_ml / self.total_BV
        #     CO = self.heart_rate * self.stroke_volume
        #     print(f"⚠️  dt={dt:.1e}, vol_ratio={vol_ratio:.3f}, CO={CO:.1f}, stroke_vol={self.stroke_volume:.3f}")
        # ── 1. Frank-Starling: dSV/dt ──────────────────────────────────────
        # 生理学：每搏输出量由静脉回流（前负荷）决定
        # 失血 → 静脉回流↓ → 前负荷↓ → SV↓
        # 公式：SV = base_SV × f(vol_ratio)，非线性响应
        vol_ratio = self.circulating_volume_ml / self.total_BV
        if 0.5 <= vol_ratio <= 1.2:
            # 失血 >15%BV 时需要显著 SV 下降才能触发压力感受器代偿
            # 曲线：vol_ratio=0.85 → SV≈17.5（-12.5%），vol_ratio=0.75 → SV≈14.5（-27.5%）
            #      vol_ratio=0.65 → SV≈11.5（-42.5%）
            target_SV = self.base_SV * (0.05 + 0.95 * vol_ratio ** 2.5)
        elif vol_ratio < 0.5:
            target_SV = self.base_SV * 0.3
        else:
            target_SV = self.base_SV * 1.05

        effective_target = target_SV * self.contractility_factor * self.preload_factor
        pH_factor = self._pH_contractility_effect(self.blood.arterial_pH)
        effective_target *= pH_factor
        coronary_factor = self._coronary_perfusion_effect(self.mean_arterial_pressure)
        effective_target *= coronary_factor

        # Frank-Starling: τ = 1/alpha_sv ≈ 3.3s
        # 连续形式: τ · dSV/dt + SV = effective_target
        # Anti-windup clamp on target (not derivative): prevents >100% change in one τ
        clamped_target = max(self.base_SV * 0.15, min(self.base_SV * 2.0, effective_target))
        tau_sv = 1.0 / 0.3  # ≈ 3.33s
        dSV = (clamped_target - self.stroke_volume) / tau_sv

        # ── 2. 心输出量（代数） ─────────────────────────────────────────────
        CO = self.heart_rate * self.stroke_volume

        # ── 3. SVR 代偿（代数+动态）─────────────────────────────────────────
        effective_SVR = self.SVR * svr_factor
        # 生理学：MAP = CVP + CO/60 × SVR  (Guyton C2, Ch.14)
        # CVP = central venous pressure (systemic circuit outflow)
        raw_MAP = CENTRAL_VENOUS_PRESSURE_MMHG + (CO / 60.0) * effective_SVR
        # 当血容量严重不足（vol_ratio < 0.7）时，静脉回流减少进一步降低 MAP
        if vol_ratio < 0.7:
            raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)
        raw_MAP = max(30.0, min(180.0, raw_MAP))

        # ── 4. 压力感受器反馈: dHR/dt, dSVR/dt ──────────────────────────────
        error = (self.MAP_target - raw_MAP) / self.MAP_target

        # 交感/副交感 baroreflex：副交感主导（迷走神经反射快且强）
        # τ_para=1s（迷走快），τ_symp=5s（交感慢）
        # 增益：副交感 40 > 交感 15（Ursino 1998 心血管模型）
        sym_target = self._clamp(SYMPATHETIC_BASELINE + 0.7 * max(0.0, error), 0.0, 1.0)
        para_target = self._clamp(0.7 - 0.5 * error, 0.0, 1.0)
        tau_symp = 5.0   # 交感响应时间常数 (s)（β1 受体较慢）
        tau_para = 1.0   # 副交感响应时间常数 (s)（迷走神经最快 0.5-1s）
        d_sym = (sym_target - self.sympathetic) / tau_symp
        d_para = (para_target - self.parasympathetic) / tau_para

        # dHR/dt: HR rate in beats/s per second (units: 1/s)
        # 副交感主导：增益 40 > 交感 15（Ursino 1998, Am J Physiol）
        HR_para = -self.parasympathetic * 40.0 * max(0.0, -error)
        HR_symp = self.sympathetic * 15.0 * max(0.0, error)
        dHR = (HR_para + HR_symp)  # 已经是 1/s 单位
        # K⁺ 毒性
        k_factor = self._potassium_cardiac_effect(self.blood.potassium_mEq_L)
        dHR = dHR * k_factor

        # SVR 补偿（τ = 1/alpha_svr = 10s）
        SVR_increase = 1.0 + 2.0 * self.sympathetic * max(0.0, error)
        target_SVR = min(self.SVR_max, self.SVR_baseline * SVR_increase)
        alpha_svr = 0.1
        dSVR = (target_SVR - self.SVR) * alpha_svr  # τ=10s

        dydt = {
            "HR": dHR,
            "SV": dSV,
            "SVR": dSVR,
            "blood_volume": -blood_loss_rate_ml_s,  # 负值 = 血容量减少
            "sympathetic": d_sym,
            "parasympathetic": d_para,
        }

        outputs = {
            "cardiac_output": CO,
            "MAP": raw_MAP,
            "CVP": max(0.0, CENTRAL_VENOUS_PRESSURE_MMHG * (1.0 - 0.5 * (1.0 - vol_ratio))),
            "PAP": max(10.0, min(35.0, raw_MAP * 0.15)),
            "blood_volume_ratio": vol_ratio,
            "MAP_filtered": raw_MAP,  # 代数输出，用于低通滤波
        }

        return dydt, outputs

    def blood_volume_change(self, delta_ml: float):
        """外部调用：改变血容量"""
        self.circulating_volume_ml = max(0.0, self.circulating_volume_ml + delta_ml)
        if delta_ml < 0:
            self.blood_loss_ml += abs(delta_ml)
        else:
            self.fluid_infused_ml += delta_ml

    def _pH_contractility_effect(self, pH: float) -> float:
        """
        酸中毒对心肌收缩力的抑制效应。

        生理机制：H⁺ 竞争性抑制 Ca²⁺ 与肌钙蛋白 C 的结合，
        降低心肌细胞对钙离子的敏感性 → 收缩力下降。

        量化关系（基于犬类离体心脏实验数据）：
        - pH ≥ 7.4：无抑制（因子 = 1.0）
        - pH 7.2-7.4：轻度抑制（线性插值 1.0 → 0.7）
        - pH 7.0-7.2：重度抑制（线性插值 0.7 → 0.35）
        - pH < 7.0：极重度抑制（线性插值 0.35 → 0.1）
        - pH < 6.8：接近停搏（因子 ≈ 0.1）

        这是死亡螺旋的核心正反馈：
        低灌注 → 乳酸↑ → pH↓ → 收缩力↓ → CO↓ → 灌注↓↓ → pH↓↓
        """
        if pH >= 7.4:
            return 1.0
        elif pH >= 7.2:
            return 0.7 + 0.3 * (pH - 7.2) / 0.2
        elif pH >= 7.0:
            return 0.35 + 0.35 * (pH - 7.0) / 0.2
        elif pH >= 6.8:
            return 0.1 + 0.25 * (pH - 6.8) / 0.2
        else:
            return max(0.05, 0.1 * pH / 6.8)

    def _potassium_cardiac_effect(self, k_mEq_L: float) -> float:
        """
        高钾血症对心率的毒性效应。

        生理机制：
        - K⁺ 升高 → 静息膜电位去极化（负值减小）
        - 快 Na⁺ 通道失活 → 0 期去极化速率↓ → 传导速度↓
        - 心电图表现：T 波高尖 → QRS 增宽 → P 波消失 → 正弦波 → 停搏

        量化关系：
        - K⁺ ≤ 5.5：正常（因子 = 1.0）
        - K⁺ 5.5-6.5：轻度心动过缓（线性插值 1.0 → 0.7）
        - K⁺ 6.5-8.0：重度心动过缓（线性插值 0.7 → 0.15）
        - K⁺ > 8.0：接近停搏/室颤（因子 ≤ 0.15）

        ARF 时高钾血症是主要死因之一。
        """
        if k_mEq_L <= 5.5:
            return 1.0
        elif k_mEq_L <= 6.5:
            return 1.0 - 0.3 * (k_mEq_L - 5.5) / 1.0
        elif k_mEq_L <= 8.0:
            return 0.7 - 0.55 * (k_mEq_L - 6.5) / 1.5
        else:
            return max(0.05, 0.15 - 0.1 * (k_mEq_L - 8.0) / 2.0)

    def _coronary_perfusion_effect(self, map_mmHg: float) -> float:
        """
        冠脉自主调节对心肌收缩力的影响。

        生理机制：
        - 冠脉血流主要发生在舒张期，依赖舒张压（≈ MAP - 10）
        - 冠肌自主调节范围：MAP 60-140 mmHg（通过小动脉舒张/收缩）
        - MAP < 60：自主调节失效，冠脉血流线性下降
        - MAP < 40：严重心肌缺血，无氧代谢主导
        - 缺血后果：ATP↓ → Na⁺/K⁺ 泵失效 → 细胞内 Ca²⁺↑ → 收缩带坏死

        量化关系：
        - MAP ≥ 60：完全灌注（因子 = 1.0）
        - MAP 40-60：线性下降 1.0 → 0.4
        - MAP < 40：极重度缺血（因子 ≤ 0.4）

        这是正反馈回路：MAP↓ → 冠脉灌注↓ → 心肌缺血 → 收缩力↓ → MAP↓↓
        """
        if map_mmHg >= 60.0:
            return 1.0
        elif map_mmHg >= 40.0:
            return 0.4 + 0.6 * (map_mmHg - 40.0) / 20.0
        else:
            return max(0.1, 0.4 * map_mmHg / 40.0)

    def _Frank_Starling(self, dt: float):
        """
        Frank-Starling：前负荷（静脉回流/血容量）调节 SV
        血容量↑ → 心肌初长度↑ → SV↑（有限度）

        叠加效应：
        1. 前负荷（血容量）→ 基础 SV
        2. 毒理学/疾病收缩力因子 → 外部调制
        3. pH 效应 → 酸中毒抑制（正反馈）
        4. 冠脉灌注效应 → 心肌缺血抑制（正反馈）
        """
        vol_ratio = self.circulating_volume_ml / self.total_BV

        # 血容量充足时：SV 随血容量增加而增加
        if 0.5 <= vol_ratio <= 1.2:
            # 失血 >15%BV 时需要显著 SV 下降才能触发压力感受器代偿
            # 曲线：vol_ratio=0.85 → SV≈17.5（-12.5%），vol_ratio=0.75 → SV≈14.5（-27.5%）
            #      vol_ratio=0.65 → SV≈11.5（-42.5%）
            target_SV = self.base_SV * (0.05 + 0.95 * vol_ratio ** 2.5)
        elif vol_ratio < 0.5:
            target_SV = self.base_SV * 0.3
        else:
            target_SV = self.base_SV * 1.05

        # 收缩力因子：外部调制（毒理学 + 疾病）
        effective_target = target_SV * self.contractility_factor * self.preload_factor

        # pH 效应：酸中毒抑制心肌收缩力（正反馈核心）
        pH_factor = self._pH_contractility_effect(self.blood.arterial_pH)
        effective_target *= pH_factor

        # 冠脉灌注效应：低 MAP → 心肌缺血 → 收缩力↓
        coronary_factor = self._coronary_perfusion_effect(self.mean_arterial_pressure)
        effective_target *= coronary_factor

        # 低通滤波
        alpha = 0.3
        self.stroke_volume = alpha * self.stroke_volume + (1 - alpha) * effective_target
        self.stroke_volume = max(self.base_SV * 0.15, self.stroke_volume)

    def _baroreceptor_feedback(self, MAP: float, dt: float,
                               chemoreceptor_drive: float = 0.0):
        """
        压力感受器反馈（动态版）+ HH 电生理耦合

        核心生理：MAP ↓ → 交感 ↑ + 副交感 ↓ → HR ↑（协同代偿）
        正常犬：HR 范围 60-180 bpm，稳态 85 bpm

        Chemoreceptor 直连路径（连续量纲正确版本）：
        - chemo_drive 经 low-pass 滤波（τ=30s）后以 RATE（bpm/s）形式叠加到 HR
        - 与离散 FC 通道分离，避免 O(1) 数值偏差
        - 参考：Tucker et al. 1984, Am J Vet Res (PMID: 6703442)

        HH 耦合：
        - 心率由 baroreceptor 反馈决定（传统路径）
        - HH 电生理模块接收心率和 [K⁺]，计算 K⁺ 毒性因子
        - K⁺ 毒性由 HH 的 h∞ 稳态推导（替代 _potassium_cardiac_effect 线性查表）
        """
        error = (self.MAP_target - MAP) / self.MAP_target

        # 交感/副交感 baroreflex：副交感主导（迷走神经快且强）
        # 与 derivatives() 的公式一致：dS/dt = (target - S) / τ
        sym_target = self._clamp(SYMPATHETIC_BASELINE + 0.7 * max(0.0, error), 0.0, 1.0)
        para_target = self._clamp(0.7 - 0.5 * error, 0.0, 1.0)
        tau_symp = 5.0   # 交感慢
        tau_para = 1.0   # 副交感快
        self.sympathetic = self._first_order_relax(
            self.sympathetic, sym_target, dt, tau_symp
        )
        self.parasympathetic = self._first_order_relax(
            self.parasympathetic, para_target, dt, tau_para
        )

        # HR 计算：副交感在MAP偏高时减速，交感在MAP偏低时加速
        # 副交感主导：增益 40 > 交感 15（Ursino 1998）
        HR_para = -self.parasympathetic * 40.0 * max(0.0, -error)
        HR_symp = self.sympathetic * 15.0 * max(0.0, error)
        # Chemoreceptor 直连：chemo_drive → HR 升速（bpm/s），量纲正确 × dt
        # 最大约 15 bpm/s，与 Tucker 1984 数据一致（PaO₂=29 时 HR +8 bpm over ~10s）
        chemo_HR = chemoreceptor_drive * 15.0
        HR_delta = (HR_para + HR_symp + chemo_HR) * dt
        # H7: 使用统一全局常量（HEART_RATE_HARD_MIN/MAX）
        self.heart_rate = max(HEART_RATE_HARD_MIN, min(self.HR_max, self.heart_rate + HR_delta))

        # ── HH 电生理耦合 ──────────────────────────────────────────────
        # 推进电生理计算器（接收当前心率和 [K⁺]）
        self.hh.update(dt, self.heart_rate, self.blood.potassium_mEq_L)

        # K⁺ 毒性：从 HH 第一性原理推导的毒性因子
        # 替代原有的 _potassium_cardiac_effect() 线性查表
        k_factor = self.hh.k_toxicity_factor
        self.heart_rate *= k_factor
        self.heart_rate = max(5.0, self.heart_rate)

        # SVR 代偿
        SVR_increase = 1.0 + 2.0 * self.sympathetic * max(0.0, error)
        self.SVR = min(self.SVR_max, self.SVR_baseline * SVR_increase)

    @staticmethod
    def _clamp(value: float, lo: float, hi: float) -> float:
        return max(lo, min(hi, value))

    @staticmethod
    def _first_order_relax(current: float, target: float, dt: float, tau: float) -> float:
        """Stable first-order lag update for coarse outer simulation steps."""
        if tau <= 0.0:
            return target
        alpha = 1.0 - math.exp(-max(0.0, dt) / tau)
        return current + (target - current) * alpha

    def compute(self, dt: float, svr_factor: float = 1.0,
                chemoreceptor_drive: float = 0.0):
        """
        主计算：推进心脏循环一个时间步

        Args:
            dt: 时间步长（秒）
            svr_factor: 外部 SVR 倍数（ToxicologyModule 输出，1.0 = 无调制）
            chemoreceptor_drive: 化学感受器驱动（0-1, 来自 neuro 模块上一时间步）

        ODE:
        1. Frank-Starling：SV = f(前负荷) × contractility_factor
        2. 心输出量：CO = HR × SV
        3. 平均动脉压：MAP = MAP_base + CO × (SVR × svr_factor) / 60
        4. 压力感受器：HR = f(MAP_error, chemoreceptor_drive)
        """
        # Step 1: Frank-Starling（前负荷调节 SV）
        self._Frank_Starling(dt)

        # Step 2: 心输出量
        self.cardiac_output = self.heart_rate * self.stroke_volume  # mL/min

        # Step 3: 平均动脉压（MAP = CVP + CO/60 × SVR, Guyton C2）
        effective_SVR = self.SVR * svr_factor
        raw_MAP = CENTRAL_VENOUS_PRESSURE_MMHG + (self.cardiac_output / 60.0) * effective_SVR

        # 血容量严重不足时血压下降
        vol_ratio = self.circulating_volume_ml / self.total_BV
        if vol_ratio < 0.7:
            raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)

        raw_MAP = max(30.0, min(180.0, raw_MAP))

        # Step 4: 压力感受器（含化学感受器直连路径）
        self._baroreceptor_feedback(raw_MAP, dt,
                                    chemoreceptor_drive=chemoreceptor_drive)

        # 低通滤波平滑 MAP
        alpha = 0.1
        self.mean_arterial_pressure = alpha * self.mean_arterial_pressure + (1 - alpha) * raw_MAP

        # Step 5: 肺动脉压
        self.pulmonary_arterial_pressure = self.mean_arterial_pressure * 0.15
        self.pulmonary_arterial_pressure = max(10.0, min(35.0, self.pulmonary_arterial_pressure))

        # Step 6: 中心静脉压
        vol_deficit = 1.0 - vol_ratio
        self.central_venous_pressure = CENTRAL_VENOUS_PRESSURE_MMHG * (1.0 - 0.5 * vol_deficit)
        self.central_venous_pressure = max(0.0, self.central_venous_pressure)

        return {
            "cardiac_output_ml_min": round(self.cardiac_output, 1),
            "heart_rate_bpm": round(self.heart_rate, 1),
            "stroke_volume_ml": round(self.stroke_volume, 1),
            "MAP_mmHg": round(self.mean_arterial_pressure, 1),
            "CVP_mmHg": round(self.central_venous_pressure, 2),
            "PAP_mmHg": round(self.pulmonary_arterial_pressure, 1),
            "SVR": round(self.SVR * svr_factor, 3),
            "contractility_factor": round(self.contractility_factor
                * self._pH_contractility_effect(self.blood.arterial_pH)
                * self._coronary_perfusion_effect(self.mean_arterial_pressure), 3),
            "blood_volume_ml": round(self.circulating_volume_ml, 1),
            "blood_volume_ratio": round(vol_ratio, 3),
            # HH 电生理数据
            "hh_heart_rate_bpm": round(self.hh.heart_rate, 1),
            "hh_k_toxicity_factor": round(self.hh.k_toxicity_factor, 3),
            "hh_h_inf": round(self.hh._h_inf, 3),
            "hh_e_k": round(self.hh._nernst_k(self.blood.potassium_mEq_L), 1),
            "ecg_interpretation": self.hh.get_ecg_interpretation(self.blood.potassium_mEq_L),
            # Noble 浦肯野纤维数据
            "noble_conduction_velocity": round(self.hh.conduction_velocity, 2),
            "noble_pr_interval_ms": round(self.hh.pr_interval_ms, 1),
            "noble_qrs_width_ms": round(self.hh.qrs_width_ms, 1),
            "noble_av_block_degree": self.hh.av_block_degree,
            "noble_av_interpretation": self.hh.get_av_interpretation(self.blood.potassium_mEq_L),
        }

    def summary(self):
        return self.compute(0.1)
