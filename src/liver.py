"""
Liver Module - 肝脏代谢系统
建模肝脏糖代谢、氨解毒、白蛋白合成、胆红素代谢、药物代谢
"""

import math
from typing import Any
from parameters import *

# ── 生理常数 ──
_MAX_GLYCOGEN_G = 300.0           # 满糖原储备 g（犬类约300g）
_AMINO_TO_AMMONIA_UMOL_PER_G = 10.0  # 每克氨基酸脱氨产生氨 μmol
_UREA_MMOL_TO_BUN_MG_DL = 2.8    # 尿素 mmol → BUN mg/dL 转换系数
_NORMAL_BILIRUBIN_MG_DL_PER_KG = 0.004  # 正常胆红素产生率 mg/day/kg
_BILIRUBIN_AXIS_INTERCEPT = 0.2   # 胆红素基准值 mg/dL（正常）
_BILIRUBIN_SEVERITY_SLOPE = 2.0   # 解毒能力下降时胆红素上升斜率
# Cori cycle constants
_CORI_VMAX_MMOL_L_MIN = 0.8     # 肝脏乳酸摄取最大速率 mmol/L/min
_CORI_KM_MMOL_L = 1.5            # Michaelis 常数 mmol/L
# CYP450 constants
_CYP450_BASE_CAPACITY = 1.0       # 正常 CYP450 代谢容量（相对单位）
_CYP450_KM = 2.0                 # Michaelis 常数（相对单位）


class LiverModule:

    # ── Phase 5: I/O contract (declarative, no behavior change) ────────
    INPUTS: tuple[str, ...] = ('co_input', 'gut_state', 'insulin', 'glucagon', 'PTH', 'cytokine')
    OUTPUTS: tuple[str, ...] = ('metabolic_activity', 'detox_capacity', 'cyp450_activity', 'glycogen_fraction', 'bilirubin_conjugation', 'glucose_output', 'ammonia_umol_L', 'albumin_g_dL', 'bilirubin_mg_dL', 'urea_mmol', 'PT_sec', 'INR')
    READS_BLOOD: tuple[str, ...] = ('glucose_mmol_L', 'ammonia_umol_L', 'amino_acids_g_L', 'drug_concentration_mg_kg', 'lactate_mmol_L', 'albumin_g_dL', 'bilirubin_mg_dL', 'ALT_U_L', 'AST_U_L', 'ALP_U_L', 'GGT_U_L', 'coagulation_factor_VII', 'PT_sec', 'INR', 'fibrinogen_mg_dL')
    WRITES_BLOOD: tuple[str, ...] = ('ammonia_umol_L', 'albumin_g_dL', 'bilirubin_mg_dL', 'bun_mg_dL', 'coagulation_factor_VII', 'PT_sec', 'INR', 'fibrinogen_mg_dL', 'ALT_U_L', 'AST_U_L', 'ALP_U_L', 'GGT_U_L', 'glucose_mmol_L', 'drug_concentration_mg_kg', 'amino_acids_g_L')
    """
    肝脏模块：核心代谢和解毒器官

    核心变量：
    - metabolic_activity: 代谢活性 (0-1, 1=正常)
    - detox_capacity: 氨解毒能力 (0-1, 1=正常)
    - cyp450_activity: CYP450 药物代谢活性 (0-1, 1=正常)
    - glycogen_fraction: 糖原储备比例 (0-1, 1=满)
    - bilirubin_conjugation: 胆红素结合能力 (0-1, 1=正常)

    数据流：
    compute(gut_state) → 读取 gut_state（肠道吸收速率）
                         → 读取 blood.portal_cache + gut_state
                         → 更新 blood.glucose, blood.albumin, blood.ammonia,
                           blood.ALT_U_L, blood.AST_U_L, blood.ALP_U_L
                         → 返回 liver_state
    """

    def __init__(self, weight_kg: float, blood, signal_bus=None):
        # Phase 6: signal bus 显式参数. None 时回退到 blood (BloodShim 兼容).
        self.w = weight_kg
        self.blood = blood  # 保留供向后兼容 (summary 等仍可读)
        self._bus = signal_bus if signal_bus is not None else blood

        # 代谢功能 (0-1)
        self.metabolic_activity = 1.0

        # 氨解毒能力 (CPS/OTC 酶活性, 0-1)
        self.detox_capacity = 1.0

        # 内源性氨产生速率 (μmol/min)：组织蛋白分解 + 肾脏产氨基准
        self.endogenous_ammonia_rate = 20.0

        # CYP450 药物代谢活性 (0-1)
        self.cyp450_activity = 1.0

        # 糖原储备 (0-1)
        self.glycogen_fraction = 0.6

        # 胆红素结合能力 (0-1)
        self.bilirubin_conjugation = 1.0

        # 肝脏血流量 (≈25% CO)
        self.hepatic_blood_flow = 0.25 * base_cardiac_output_ml_min(weight_kg)

        # 胆红素状态变量（用于时序ODE）
        self._bilirubin_accumulation = 0.0

        # 累计输出（用于追踪）
        self.cumulative_glucose_production_g = 0.0
        self.cumulative_urea_production_mmol = 0.0
        self.cumulative_albumin_production_g = 0.0

    # ── Phase 6: 显式 blood I/O helper ─────────────────────────────────
    def _blood_read(self, name: str) -> Any:
        """显式 blood 字段读：record to bus + return real blood value.

        Works in two regimes:
        - Phase 6 (signal_bus is SignalBus): record read + return real_blood.X
        - Legacy / tests (signal_bus is BloodCompartment or None): direct access
        """
        bus = self._bus
        if hasattr(bus, "read_blood") and hasattr(bus, "real_blood"):
            # Phase 6: proper SignalBus
            bus.read_blood(name)
            return getattr(bus.real_blood, name)
        # Legacy: direct access (backward compat for tests with plain BloodCompartment)
        return getattr(self.blood, name)

    def _blood_write(self, name: str, value: Any) -> None:
        """显式 blood 字段写：record to bus + write to real blood.

        Works in two regimes:
        - Phase 6 (signal_bus is SignalBus): record write + write to real_blood
        - Legacy / tests (signal_bus is BloodCompartment or None): direct write
        """
        bus = self._bus
        if hasattr(bus, "publish_blood") and hasattr(bus, "real_blood"):
            # Phase 6: proper SignalBus
            bus.publish_blood(name, value)
            setattr(bus.real_blood, name, value)
        else:
            # Legacy: direct write
            setattr(self.blood, name, value)

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: glycogen_fraction, bilirubin_accumulation
    # 输出端口（供其他模块）: glucose_output, ammonia_umol_L, albumin_g_dL, etc.

    def derivatives(self, dt: float, co_input: float, gut_state: dict) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Args:
            dt: 时间步长（秒）
            co_input: 心输出量 mL/min
            gut_state: dict（包含 gut.derivatives() 的输出端口，如 amino_absorption_g_min）

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        dt_min = dt / 60.0
        dt_hour = dt / 3600.0
        dt_day = dt / 86400.0

        # ── 1. 肝血流量（代数） ─────────────────────────────────────────────
        hepatic_flow = 0.25 * co_input

        # ── 2. 葡萄糖稳态（代数 + 状态更新） ───────────────────────────────
        glucose = self._blood_read("glucose_mmol_L")

        # 低血糖：糖原分解
        if glucose < 3.5:
            base_rate = 0.3 * self.glycogen_fraction
            rate = base_rate * self.metabolic_activity
            if glucose < 2.5:
                rate *= 3.0
            elif glucose < 3.0:
                rate *= 1.5
            glycogen_consumed_g = rate * dt_min * _MAX_GLYCOGEN_G
            dGlycogen = -glycogen_consumed_g / _MAX_GLYCOGEN_G
            glucose_output = rate
        else:
            dGlycogen = 0.0
            glucose_output = 0.0

        # 高血糖：糖原合成
        if glucose > 6.0:
            base_rate = 0.2 * self.metabolic_activity
            if glucose > 8.0:
                base_rate *= 2.0
            elif glucose > 7.0:
                base_rate *= 1.5
            glycogen_synthesized_g = base_rate * dt_min * _MAX_GLYCOGEN_G
            dGlycogen += glycogen_synthesized_g / _MAX_GLYCOGEN_G

        # 氨抑制
        ammonia_val = self._blood_read("ammonia_umol_L")
        if ammonia_val > 100:
            glucose_output *= max(0.3, 1.0 - (ammonia_val - 100) / 400)

        # 糖异生（利用氨基酸）
        amino_g_min = gut_state.get("amino_absorption_g_min", 0.0)
        if glucose < 3.5 and self.metabolic_activity > 0.3:
            gluconeogenesis = amino_g_min * 0.6 * self.metabolic_activity
            glucose_output += gluconeogenesis

        self.glycogen_fraction = max(0.0, min(1.0, self.glycogen_fraction + dGlycogen))

        # ── 3. 氨解毒（代数更新到 blood.ammonia） ───────────────────────────
        k = 1.0 * self.detox_capacity
        gut_ammonia_rate = amino_g_min * _AMINO_TO_AMMONIA_UMOL_PER_G
        total_production = self.endogenous_ammonia_rate + gut_ammonia_rate

        if k > 1e-6:
            new_ammonia = (
                ammonia_val * math.exp(-k * dt_min)
                + (total_production / k) * (1.0 - math.exp(-k * dt_min))
            )
            new_ammonia = max(0.0, new_ammonia)
            self._blood_write("ammonia_umol_L", new_ammonia)

        # 尿素产生
        ammonia_consumed = max(0.0, ammonia_val - new_ammonia) if k > 1e-6 else 0.0
        urea_mmol = ammonia_consumed / 2.0
        if urea_mmol > 0:
            self._blood_write("bun_mg_dL",
                self._blood_read("bun_mg_dL") + urea_mmol * _UREA_MMOL_TO_BUN_MG_DL * dt_min)

        # ── 4. 白蛋白合成（代数更新到 blood.albumin） ───────────────────────
        base_rate_g_day = 0.5 * self.w
        amino_g_L = self._blood_read("amino_acids_g_L")
        amino_factor = min(2.0, amino_g_L / 1.0)
        synthesis_rate = base_rate_g_day * self.metabolic_activity * amino_factor
        albumin_change = synthesis_rate * dt_hour / 24.0
        alb_current = self._blood_read("albumin_g_dL")
        self._blood_write("albumin_g_dL", max(1.0, min(5.0, alb_current + albumin_change)))
        self.cumulative_albumin_production_g += synthesis_rate * dt_min / 60.0

        # ── 5. 胆红素代谢（时序 ODE → 状态变量） ───────────────────────────
        normal_production = _NORMAL_BILIRUBIN_MG_DL_PER_KG * self.w
        conj = self.bilirubin_conjugation
        k_clear = 0.5 * conj
        production_input = normal_production * (1.0 - conj)

        if k_clear > 1e-6:
            new_accum = (
                self._bilirubin_accumulation * math.exp(-k_clear * dt_day)
                + (production_input / k_clear) * (1.0 - math.exp(-k_clear * dt_day))
            )
        else:
            new_accum = self._bilirubin_accumulation + production_input * dt_day
        new_accum = max(0.0, new_accum)
        dBilirubin_accum = (new_accum - self._bilirubin_accumulation) / dt_day  # 转换为 /s
        self._bilirubin_accumulation = new_accum

        bilirubin_level = _BILIRUBIN_AXIS_INTERCEPT + new_accum * _BILIRUBIN_SEVERITY_SLOPE
        self._blood_write("bilirubin_mg_dL", max(0.1, min(15.0, bilirubin_level)))

        # 肝酶
        if conj < 0.8:
            self._blood_write("ALT_U_L", 25.0 + (1.0 - conj) * 150.0)
            self._blood_write("AST_U_L", 25.0 + (1.0 - conj) * 200.0)
            self._blood_write("ALP_U_L", 30.0 + (1.0 - conj) * 300.0)

        # ── 6. 凝血因子（代数更新到 blood） ──────────────────────────────────
        k_VII = 0.12
        target_VII = 0.04 * self.metabolic_activity * max(0.1, conj)
        vii_current = self._blood_read("coagulation_factor_VII")
        vii_new = vii_current + (target_VII - vii_current) * k_VII * dt_hour
        vii_new = max(0.05, min(1.0, vii_new))
        self._blood_write("coagulation_factor_VII", vii_new)
        PT_factor = 1.0 + (1.0 - vii_new) * 1.5
        PT_sec = 12.0 * PT_factor
        INR = PT_sec / 12.0
        self._blood_write("PT_sec", PT_sec)
        self._blood_write("INR", INR)

        # ── 7. CYP450（代数） ───────────────────────────────────────────────
        drug_conc = self._blood_read("drug_concentration_mg_kg")
        if drug_conc > 0 and self.cyp450_activity > 0:
            baseline_flow = 0.25 * base_cardiac_output_ml_min(self.w)
            hepatic_factor = min(1.0, hepatic_flow / baseline_flow)
            Vmax = _CYP450_BASE_CAPACITY * self.metabolic_activity * self.cyp450_activity * hepatic_factor
            metabolism_rate = Vmax * drug_conc / (_CYP450_KM + drug_conc)
            max_clearance = drug_conc
            cleared = min(metabolism_rate, max_clearance)
            self._blood_write("drug_concentration_mg_kg", max(0.0, drug_conc - cleared))

        # ── 8. 肠道氨基酸清除 ────────────────────────────────────────────────
        if hepatic_flow > 0:
            amino_removed_g_L = amino_g_min * dt_min / (hepatic_flow / 1000)
            amino_current = self._blood_read("amino_acids_g_L")
            self._blood_write("amino_acids_g_L", max(0.1, amino_current - amino_removed_g_L))

        self.hepatic_blood_flow = hepatic_flow
        self.cumulative_glucose_production_g += glucose_output * dt_min
        self.cumulative_urea_production_mmol += total_production * dt_min / 2.0

        # ── 9. Cori cycle（代数更新到 blood.lactate 和 blood.glucose） ─────
        lactate = self._blood_read("lactate_mmol_L")
        if lactate > 0.1:
            baseline_flow = 0.25 * base_cardiac_output_ml_min(self.w)
            hepatic_factor = min(1.0, hepatic_flow / baseline_flow)
            uptake_rate = (
                _CORI_VMAX_MMOL_L_MIN * self.metabolic_activity * hepatic_factor
                * lactate / (_CORI_KM_MMOL_L + lactate)
            )
            lactate_consumed = uptake_rate * dt_min
            glucose_from_lactate = lactate_consumed / 2.0
            glu_current = self._blood_read("glucose_mmol_L")
            self._blood_write("glucose_mmol_L", min(25.0, glu_current + glucose_from_lactate))

        # ── 状态变量导数 ───────────────────────────────────────────────────
        dGlycogen_net = dGlycogen  # per-second rate
        dydt = {
            "glycogen_fraction": dGlycogen_net,
            "bilirubin_accumulation": dBilirubin_accum,
        }

        outputs = {
            "glucose_output_g_min": glucose_output,
            "ammonia_umol_L": new_ammonia,
            "albumin_g_dL": self._blood_read("albumin_g_dL"),
            "bilirubin_mg_dL": self._blood_read("bilirubin_mg_dL"),
            "ALT_U_L": self._blood_read("ALT_U_L"),
            "AST_U_L": self._blood_read("AST_U_L"),
            "ALP_U_L": self._blood_read("ALP_U_L"),
            "GGT_U_L": self._blood_read("GGT_U_L"),
            "hepatic_blood_flow_mL_min": hepatic_flow,
            "coagulation_factor_VII": self._blood_read("coagulation_factor_VII"),
            "PT_sec": PT_sec,
            "INR": INR,
            "fibrinogen_mg_dL": self._blood_read("fibrinogen_mg_dL"),
            "metabolic_activity": self.metabolic_activity,
            "detox_capacity": self.detox_capacity,
            "cyp450_activity": self.cyp450_activity,
            "glycogen_fraction": self.glycogen_fraction,
            "bilirubin_conjugation": conj,
        }

        return dydt, outputs

    def _update_hepatic_flow(self, CO: float):
        """更新肝血流量（≈25% CO）"""
        if CO <= 0:
            # Moribund states can transiently drive CO to zero or below.
            # The liver should see absent perfusion, not crash the engine.
            self.hepatic_blood_flow = 0.0
            return
        self.hepatic_blood_flow = 0.25 * CO

    def _compute_glucose_homeostasis(self, dt: float, gut_state: dict) -> float:
        """
        葡萄糖稳态调节

        规则：
        - blood.glucose < 3.5 mmol/L → 糖原分解 + 糖异生
        - blood.glucose > 6.0 mmol/L → 糖原合成
        - 极低 (< 2.5) → 强烈糖异生
        - 极高 (> 8.0) → 强烈糖原合成

        dt: 秒（转换为分钟用于 per-minute 速率计算）
        gut_state: 包含 absorption_amino_g_min 等速率值
        """
        dt_min = dt / 60.0
        glucose = self._blood_read("glucose_mmol_L")
        glucose_production_g_min = 0.0

        # 低血糖：糖原分解
        if glucose < 3.5:
            base_rate = 0.3 * self.glycogen_fraction  # 最大 0.3 g/min（满糖原时）
            rate = base_rate * self.metabolic_activity

            if glucose < 2.5:
                rate *= 3.0
            elif glucose < 3.0:
                rate *= 1.5

            glycogen_consumed_g = rate * dt_min * _MAX_GLYCOGEN_G
            self.glycogen_fraction = max(0.0, self.glycogen_fraction - glycogen_consumed_g / _MAX_GLYCOGEN_G)
            glucose_production_g_min += rate

        # 高血糖：糖原合成
        if glucose > 6.0:
            base_rate = 0.2 * self.metabolic_activity
            rate = base_rate

            if glucose > 8.0:
                rate *= 2.0
            elif glucose > 7.0:
                rate *= 1.5

            glycogen_synthesized_g = rate * dt_min * _MAX_GLYCOGEN_G
            self.glycogen_fraction = min(
                1.0,
                self.glycogen_fraction + glycogen_synthesized_g / _MAX_GLYCOGEN_G
            )

        # 氨中毒时抑制糖异生（肝脏受损时）
        ammonia_umol_L = self._blood_read("ammonia_umol_L")
        if ammonia_umol_L > 100:
            glucose_production_g_min *= max(0.3, 1.0 - (ammonia_umol_L - 100) / 400)

        # 糖异生：利用氨基酸（来自 gut_state 速率）合成葡萄糖
        blood_glucose = self._blood_read("glucose_mmol_L")
        if blood_glucose < 3.5 and self.metabolic_activity > 0.3:
            amino_g_min = gut_state.get("absorption_amino_g_min", 0.0)
            gluconeogenesis_rate = amino_g_min * 0.6  # 60% 转化为葡萄糖
            glucose_production_g_min += gluconeogenesis_rate * self.metabolic_activity

        return glucose_production_g_min

    def _compute_ammonia_detox(self, dt: float, gut_state: dict) -> float:
        """
        氨解毒（尿素循环）

        CPS → OTC → ARG 酶促反应
        氨 + CO2 → 精氨酸 → 尿素 + 鸟氨酸

        dt 的单位是秒，所有 rate 参数都是 per-minute。
        公式使用分钟制：dt_min = dt / 60.0

        稳态分析（detox_capacity=1.0, endogenous=20, gut_input≈2）：
          production_rate = 20 + 2 = 22 μmol/min
          clearance_rate = k * ammonia, where k = 1.0/min
          steady_state = production_rate / k = 22 μmol/L ≈ 正常范围 10-40 ✓

        detox_capacity=0.2 时：
          k_eff = 0.2 → SS = 22/0.2 = 110 μmol/L（严重高氨血症）
        """
        ammonia = self._blood_read("ammonia_umol_L")
        dt_min = dt / 60.0

        k = 1.0 * self.detox_capacity  # 随解毒能力缩放
        detox_rate_umol_min = k * ammonia  # 随浓度变化的清除率

        gut_amino_rate = gut_state.get("absorption_amino_g_min", 0.0)
        gut_ammonia_rate = gut_amino_rate * _AMINO_TO_AMMONIA_UMOL_PER_G

        endogenous_rate = self.endogenous_ammonia_rate

        total_production_rate = gut_ammonia_rate + endogenous_rate

        # 血氨更新：dA/dt = production - k*A
        # 解析解（每个 dt）：A(t+dt) = A(t)*exp(-k*dt_min) + (P/k)*(1-exp(-k*dt_min))
        new_ammonia = (
            ammonia * math.exp(-k * dt_min)
            + (total_production_rate / k) * (1.0 - math.exp(-k * dt_min))
        )
        new_ammonia = max(0.0, new_ammonia)
        self._blood_write("ammonia_umol_L", new_ammonia)

        # 尿素产生（2 NH3 → 1 CO(NH2)2）
        ammonia_consumed = max(0.0, ammonia - new_ammonia)
        urea_produced_mmol = ammonia_consumed / 2.0

        # 更新血尿素氮
        if urea_produced_mmol > 0:
            bun_current = self._blood_read("bun_mg_dL")
            self._blood_write("bun_mg_dL", bun_current + urea_produced_mmol * _UREA_MMOL_TO_BUN_MG_DL * dt_min)

        return total_production_rate

    def _compute_protein_synthesis(self, dt: float) -> float:
        """
        白蛋白合成

        正常合成速率：约 0.5 g/day/kg
        受代谢活性、氨基酸可用性调节
        """
        dt_min = dt / 60.0
        dt_hour = dt / 3600.0
        base_rate_g_day = 0.5 * self.w  # 0.5 g/day/kg
        activity_factor = self.metabolic_activity

        # 氨基酸可用性因子（门静脉氨基酸浓度）
        amino_g_L = self._blood_read("amino_acids_g_L")
        amino_factor = min(2.0, amino_g_L / 1.0)  # 正常 ~1.0 g/L

        # 合成速率 g/day
        synthesis_rate = base_rate_g_day * activity_factor * amino_factor

        # 更新白蛋白（正常 2.5-4.0 g/dL，半衰期 ~20 天，简化处理）
        albumin_change_g_dL = synthesis_rate * dt_hour / 24.0  # g/dL per step
        alb_current = self._blood_read("albumin_g_dL")
        self._blood_write("albumin_g_dL", max(1.0, min(5.0, alb_current + albumin_change_g_dL)))

        # 累计（g）
        self.cumulative_albumin_production_g += synthesis_rate * dt_min / 60.0

        return synthesis_rate

    def _compute_bilirubin_metabolism(self, dt: float):
        """
        胆红素代谢（时序 ODE）

        规则：
        - 正常衰老红细胞 → 非结合胆红素（间接胆红素）
        - 肝脏结合 → 胆红素葡萄糖醛酸（直接胆红素）
        - 胆汁排泄 → 肠肝循环

        时序模型：
        dBIL/dt = production_rate × (1 - conjugation_factor) - k_clear × BIL_accumulation
        """
        dt_day = dt / 86400.0  # 秒 → 天

        # 正常胆红素产生（来自红细胞分解，mg/day/kg）
        normal_production_rate = _NORMAL_BILIRUBIN_MG_DL_PER_KG * self.w  # mg/day

        # 结合能力下降 → 累积加速
        conjugation_factor = self.bilirubin_conjugation

        # 胆红素累积 ODE
        # production 输入（未结合部分），清除 = k × accumulation（肝脏排泄能力）
        k_clear = 0.5 * conjugation_factor  # 清除率常数，天^-1
        production_input = normal_production_rate * (1.0 - conjugation_factor)

        # 累积微分：dA/dt = production - k_clear × A
        # 解析解：A(t) = A(0)*exp(-k*t) + (P/k)*(1-exp(-k*t))
        if k_clear > 1e-6:
            new_accumulation = (
                self._bilirubin_accumulation * math.exp(-k_clear * dt_day)
                + (production_input / k_clear) * (1.0 - math.exp(-k_clear * dt_day))
            )
        else:
            # conjugation_factor=0 时，仅累积不清除
            new_accumulation = self._bilirubin_accumulation + production_input * dt_day
        new_accumulation = max(0.0, new_accumulation)
        self._bilirubin_accumulation = new_accumulation

        # 血胆红素 = 基准 + 累积贡献
        bilirubin_level = (
            _BILIRUBIN_AXIS_INTERCEPT
            + new_accumulation * _BILIRUBIN_SEVERITY_SLOPE
        )
        self._blood_write("bilirubin_mg_dL", max(0.1, min(15.0, bilirubin_level)))

        # 肝酶升高模拟（ALT, AST 反映肝细胞损伤）
        # ALP 反映胆汁淤积
        if conjugation_factor < 0.8:
            self._blood_write("ALT_U_L", 25.0 + (1.0 - conjugation_factor) * 150.0)
            self._blood_write("AST_U_L", 25.0 + (1.0 - conjugation_factor) * 200.0)
            self._blood_write("ALP_U_L", 30.0 + (1.0 - conjugation_factor) * 300.0)

    def _compute_cyp450_drug_metabolism(self, dt: float, drug_conc: float) -> float:
        """
        CYP450 Phase I 药物代谢（米氏动力学）

        肝脏代谢药物浓度，速率受代谢活性和 cyp450_activity 调制。
        肝血流量影响代谢效率。

        Args:
            dt: 时间步长（秒）
            drug_conc: 药物浓度（相对单位，mg/kg 等效）

        Returns:
            本步药物清除量（用于 pharmacology.py 应用到 Drug.concentration）
        """
        if drug_conc <= 0 or self.cyp450_activity <= 0:
            return 0.0

        # 肝血流量因子（低灌注时代谢下降）
        baseline_flow = 0.25 * base_cardiac_output_ml_min(self.w)
        hepatic_factor = min(1.0, self.hepatic_blood_flow / baseline_flow)

        # 米氏动力学
        Vmax_eff = (
            _CYP450_BASE_CAPACITY
            * self.metabolic_activity
            * self.cyp450_activity
            * hepatic_factor
        )
        metabolism_rate = Vmax_eff * drug_conc / (_CYP450_KM + drug_conc)

        # 限制最大清除速率（防止负浓度）
        max_clearance = drug_conc
        cleared = min(metabolism_rate, max_clearance)
        # 返回清除量（非速率），供调用方直接减 Drug.concentration
        return cleared * dt

    def _compute_lactate_metabolism(self, dt: float, lactate_conc: float) -> float:
        """
        Cori cycle：肝脏摄取乳酸 → 糖异生 → 葡萄糖释放

        生理：
        - 正常乳酸清除率 ≈ 0.5-1.0 mmol/L/min（肝脏占 60-70%）
        - 低灌注时乳酸产生↑，肝脏清除负担↑
        - 肝脏代谢活性下降时清除率下降

        米氏动力学：rate = Vmax * [Lactate] / (Km + [Lactate])

        Args:
            dt: 时间步长（秒）
            lactate_conc: 当前血乳酸 mmol/L

        Returns:
            本步消耗的乳酸量（mmol/L），用于监控
        """
        dt_min = dt / 60.0

        # 肝血流量因子（低灌注时清除能力下降）
        baseline_flow = 0.25 * base_cardiac_output_ml_min(self.w)
        hepatic_factor = min(1.0, self.hepatic_blood_flow / baseline_flow)

        # 米氏动力学摄取率
        if lactate_conc > 0.1:
            uptake_rate = (
                _CORI_VMAX_MMOL_L_MIN
                * self.metabolic_activity
                * hepatic_factor
                * lactate_conc
                / (_CORI_KM_MMOL_L + lactate_conc)
            )
        else:
            uptake_rate = 0.0

        lactate_consumed = uptake_rate * dt_min  # mmol/L per step

        # Cori cycle：2 lactate → 1 glucose（糖异生）
        glucose_from_lactate = lactate_consumed / 2.0
        if glucose_from_lactate > 0.001:
            glu_current = self._blood_read("glucose_mmol_L")
            self._blood_write("glucose_mmol_L", min(25.0, glu_current + glucose_from_lactate))

        return lactate_consumed

    def consume_lactate(self, dt: float) -> float:
        """
        Public API：供 simulation.py 调用，返回本步肝脏消耗的乳酸量 mmol/L

        此方法读取当前血乳酸浓度，执行 Cori cycle，更新血糖，
        返回本步净消耗量（供 caller 计算总清除率）。
        """
        lactate = self._blood_read("lactate_mmol_L")
        return self._compute_lactate_metabolism(dt, lactate)

    def compute_drug_clearance(self, dt: float, drug_conc: float) -> float:
        """
        Public API：供 pharmacology.py 调用，返回本步肝脏 CYP450 代谢清除量

        Args:
            dt: 时间步长（秒）
            drug_conc: 当前药物浓度

        Returns:
            药物清除量（与 drug.concentration 单位一致）
        """
        return self._compute_cyp450_drug_metabolism(dt, drug_conc)

    def _compute_coagulation_factors(self, dt: float) -> None:
        """
        凝血因子合成（肝脏合成 II, V, VII, IX, X 因子）

        简化建模：
        - 因子 VII 半衰期最短（约 6h），PT 最先反映肝功能
        - 因子 V 半衰期约 12h
        - 肝脏代谢活性调节合成速率

        PT（凝血酶原时间）估算：
        - 正常 PT ≈ 12s
        - 因子 VII 活性越低，PT 越长
        - INR = (PT / 正常 PT) ^ PT_factor
        """
        dt_hour = dt / 3600.0

        # 因子 VII 更新（一阶动力学）
        k_VII = 0.12
        base_synthesis_VII = 0.04  # 每天合成约 4% 总量（半衰期 6h≈24%/天）
        synthesis_factor = self.metabolic_activity * max(0.1, self.detox_capacity)
        target_VII = base_synthesis_VII * synthesis_factor
        vii_current = self._blood_read("coagulation_factor_VII")
        vii_new = vii_current + (target_VII - vii_current) * k_VII * dt_hour
        vii_new = max(0.05, min(1.0, vii_new))
        self._blood_write("coagulation_factor_VII", vii_new)

        # PT 估算：正常 12s，因子 VII 活性越低 PT 越长
        base_PT = 12.0
        PT_factor = 1.0 + (1.0 - vii_new) * 1.5
        PT_sec = base_PT * PT_factor
        INR = PT_sec / base_PT
        self._blood_write("PT_sec", PT_sec)
        self._blood_write("INR", INR)

    def compute(self, dt: float, gut_state: dict, cardiac_output: float) -> dict:
        """
        肝脏计算主函数

        Args:
            dt: 时间步长 秒
            gut_state: GutModule.compute() 返回的状态 dict
            cardiac_output: 心输出量 mL/min

        Returns:
            liver_state dict
        """
        # Step 1: 更新肝血流量
        self._update_hepatic_flow(cardiac_output)

        # Step 2: 葡萄糖稳态（使用 gut_state 中的吸收速率）
        glucose_output_g_min = self._compute_glucose_homeostasis(dt, gut_state)

        # 将肠道吸收的葡萄糖加入血液（gut 已经写了 blood.glucose，这里补充糖异生）
        if glucose_output_g_min > 0.05:
            dt_min = dt / 60.0
            plasma_ml = self.w * 86 * 0.55
            if plasma_ml > 0:
                glucose_mmol = (glucose_output_g_min * 1000 / 180)  # g → mmol
                glucose_increase = glucose_mmol / (plasma_ml / 1000)  # mmol/L per min
                glu_current = self._blood_read("glucose_mmol_L")
                self._blood_write("glucose_mmol_L",
                    max(1.0, min(25.0, glu_current + glucose_increase * dt_min)))

        # Step 3: 氨解毒（使用 gut_state 速率）
        ammonia_clearance = self._compute_ammonia_detox(dt, gut_state)

        # Step 4: 蛋白质合成
        albumin_synthesis = self._compute_protein_synthesis(dt)

        # Step 5: 胆红素代谢（时序 ODE）
        self._compute_bilirubin_metabolism(dt)

        # Step 6: CYP450 代谢
        drug_conc = self._blood_read("drug_concentration_mg_kg")
        cyp450_cleared = self._compute_cyp450_drug_metabolism(dt, drug_conc)
        if cyp450_cleared > 0 and drug_conc > 0:
            self._blood_write("drug_concentration_mg_kg", max(0.0, drug_conc - cyp450_cleared))

        # Step 7: 凝血因子合成（PT/INR）
        self._compute_coagulation_factors(dt)

        # 清除门户缓存（模拟肝脏对肠道吸收营养的摄取）
        gut_amino_rate = gut_state.get("absorption_amino_g_min", 0.0)
        dt_min = dt / 60.0
        amino_removed_g_L = gut_amino_rate * dt_min / (self.hepatic_blood_flow / 1000) if self.hepatic_blood_flow > 0 else 0.0
        if amino_removed_g_L > 0:
            amino_current = self._blood_read("amino_acids_g_L")
            self._blood_write("amino_acids_g_L", max(0.1, amino_current - amino_removed_g_L))

        # 累计输出追踪
        self.cumulative_glucose_production_g += glucose_output_g_min * dt_min
        self.cumulative_urea_production_mmol += ammonia_clearance * dt_min / 2.0

        return {
            "hepatic_blood_flow_ml_min": round(self.hepatic_blood_flow, 1),
            "metabolic_activity": round(self.metabolic_activity, 3),
            "detox_capacity": round(self.detox_capacity, 3),
            "cyp450_activity": round(self.cyp450_activity, 3),
            "glycogen_fraction": round(self.glycogen_fraction, 3),
            "bilirubin_conjugation": round(self.bilirubin_conjugation, 3),
            "glucose_output_g_min": round(glucose_output_g_min, 3),
            "ammonia_clearance_umol_min": round(ammonia_clearance, 1),
            "albumin_synthesis_g_day": round(albumin_synthesis, 2),
            "ALT_U_L": round(self._blood_read("ALT_U_L"), 1),
            "AST_U_L": round(self._blood_read("AST_U_L"), 1),
            "ALP_U_L": round(self._blood_read("ALP_U_L"), 1),
            "GGT_U_L": round(self._blood_read("GGT_U_L"), 1),
            "albumin_g_dL": round(self._blood_read("albumin_g_dL"), 2),
            "ammonia_umol_L": round(self._blood_read("ammonia_umol_L"), 1),
            "glucose_mmol_L": round(self._blood_read("glucose_mmol_L"), 2),
            "BUN_mg_dL": round(self._blood_read("bun_mg_dL"), 1),
            "lactate_consumed_mmol_L": 0.0,  # Cori cycle via consume_lactate() API
            "cyp450_drug_cleared": round(cyp450_cleared, 4),
            "PT_sec": round(self._blood_read("PT_sec"), 1),
            "INR": round(self._blood_read("INR"), 2),
            "coagulation_factor_VII": round(self._blood_read("coagulation_factor_VII"), 3),
        }

    def summary(self) -> dict:
        """返回肝脏状态摘要"""
        return {
            "metabolic_activity": round(self.metabolic_activity, 3),
            "detox_capacity": round(self.detox_capacity, 3),
            "cyp450_activity": round(self.cyp450_activity, 3),
            "glycogen": round(self.glycogen_fraction, 3),
            "hepatic_flow": round(self.hepatic_blood_flow, 1),
            "albumin": round(self._blood_read("albumin_g_dL"), 2),
            "ammonia": round(self._blood_read("ammonia_umol_L"), 1),
            "PT_sec": round(self._blood_read("PT_sec"), 1),
            "INR": round(self._blood_read("INR"), 2),
        }
