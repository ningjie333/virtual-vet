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

from parameters import *
from src.cardiac_electrophysiology import CardiacElectrophysiology


class HeartModule:
    """
    心血管模块：模拟心脏泵血功能与血压调节
    状态变量：HR, SV, MAP, CVP, blood_volume
    """

    def __init__(
        self,
        weight_kg: float,
        blood,
        HR_rest: float = HEART_RATE_REST_BPM,
        HR_max: float = HEART_RATE_STRESS_BPM,
        sv_ml: float = None,           # 若为 None 则按 1.0 mL/kg 计算
        base_co_ml_min: float = None,  # 若为 None 则按 HR_rest × sv_ml 计算
        SVR: float = SYSTEMIC_VASCULAR_RESISTANCE,
        MAP_baseline: float = 60.0,
        MAP_target: float = MEAN_ARTERIAL_PRESSURE_MMHG,
    ):
        self.w = weight_kg
        self.blood = blood

        # 心率参数
        self.HR_rest = HR_rest
        self.HR_max = HR_max
        self.heart_rate = HR_rest

        # 每搏输出量（外部传入或按 1.0 mL/kg 计算）
        _sv = sv_ml if sv_ml is not None else 1.0 * weight_kg
        self.base_SV = _sv
        self.stroke_volume = _sv

        # 血管阻力（mmHg·s/mL = PRU）
        self.SVR = SVR
        self.SVR_baseline = SVR
        self.SVR_max = SVR * 3.0  # 交感神经最大收缩时的阻力

        # 血压
        self.MAP_baseline = MAP_baseline  # 基础血管张力（mmHg）
        self.MAP_target = MAP_target
        self.mean_arterial_pressure = MAP_target
        self.central_venous_pressure = CENTRAL_VENOUS_PRESSURE_MMHG
        self.pulmonary_arterial_pressure = PULMONARY_ARTERIAL_PRESSURE_MMHG

        # 血液动力学
        self.cardiac_output = 0.0  # mL/min

        # 循环血量
        self.total_BV = total_blood_volume_ml(weight_kg)
        self.circulating_volume_ml = self.total_BV

        # 交感/副交感活动（0-1）
        self.sympathetic = SYMPATHETIC_BASELINE
        self.parasympathetic = 0.7

        # 收缩力因子（由 ToxicologyModule 调制，1.0 = 正常）
        self.contractility_factor = 1.0

        # 失血/输液累计
        self.blood_loss_ml = 0.0
        self.fluid_infused_ml = 0.0

        # 电生理计算器（基于 HH 第一性原理）
        self.hh = CardiacElectrophysiology()

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
            target_SV = self.base_SV * (0.6 + 0.4 * vol_ratio)
        elif vol_ratio < 0.5:
            # 严重低血容量：SV 下降，但下降速率受限制
            target_SV = self.base_SV * 0.5
        else:
            target_SV = self.base_SV * 1.05

        # 收缩力因子：外部调制（毒理学 + 疾病）
        effective_target = target_SV * self.contractility_factor

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

    def _baroreceptor_feedback(self, MAP: float, dt: float):
        """
        压力感受器反馈（动态版）+ HH 电生理耦合

        核心生理：MAP ↓ → 交感 ↑ + 副交感 ↓ → HR ↑（协同代偿）
        正常犬：HR 范围 60-180 bpm，稳态 85 bpm

        HH 耦合：
        - 心率由 baroreceptor 反馈决定（传统路径）
        - HH 电生理模块接收心率和 [K⁺]，计算 K⁺ 毒性因子
        - K⁺ 毒性由 HH 的 h∞ 稳态推导（替代 _potassium_cardiac_effect 线性查表）
        """
        error = (self.MAP_target - MAP) / self.MAP_target

        # 交感活动动态更新
        sym_target = self._clamp(SYMPATHETIC_BASELINE + 0.7 * max(0.0, error), 0.0, 1.0)
        self.sympathetic += (sym_target - self.sympathetic) * min(1.0, dt / 2.0)

        # 副交感活动动态更新
        para_target = self._clamp(0.7 - 0.5 * error, 0.0, 1.0)
        self.parasympathetic += (para_target - self.parasympathetic) * min(1.0, dt / 5.0)

        # HR 计算：副交感在MAP偏高时减速，交感在MAP偏低时加速
        HR_para = -self.parasympathetic * 15.0 * max(0.0, -error)
        HR_symp = self.sympathetic * 50.0 * max(0.0, error)
        HR_delta = (HR_para + HR_symp) * dt
        self.heart_rate = max(60.0, min(self.HR_max, self.heart_rate + HR_delta))

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

    def compute(self, dt: float, svr_factor: float = 1.0):
        """
        主计算：推进心脏循环一个时间步

        Args:
            dt: 时间步长（秒）
            svr_factor: 外部 SVR 倍数（ToxicologyModule 输出，1.0 = 无调制）

        ODE:
        1. Frank-Starling：SV = f(前负荷) × contractility_factor
        2. 心输出量：CO = HR × SV
        3. 平均动脉压：MAP = MAP_base + CO × (SVR × svr_factor) / 60
        4. 压力感受器：HR = f(MAP_error)
        """
        # Step 1: Frank-Starling（前负荷调节 SV）
        self._Frank_Starling(dt)

        # Step 2: 心输出量
        self.cardiac_output = self.heart_rate * self.stroke_volume  # mL/min

        # Step 3: 平均动脉压（含外部 SVR 调制，如可卡因交感收缩）
        effective_SVR = self.SVR * svr_factor
        pressure_contribution = (self.cardiac_output / 60.0) * effective_SVR
        raw_MAP = self.MAP_baseline + pressure_contribution

        # 血容量严重不足时血压下降
        vol_ratio = self.circulating_volume_ml / self.total_BV
        if vol_ratio < 0.7:
            raw_MAP = raw_MAP * (0.5 + 0.5 * vol_ratio / 0.7)

        raw_MAP = max(30.0, min(180.0, raw_MAP))

        # Step 4: 压力感受器
        self._baroreceptor_feedback(raw_MAP, dt)

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
        }

    def summary(self):
        return self.compute(0.1)