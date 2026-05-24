"""
Fluid Compartment — 三室体液模型

三个隔室：
  Vascular (血管内液)  ≈ 8% 体重
  ISF    (组织间液)    ≈ 15% 体重
  ICF    (细胞内液)    ≈ 40% 体重

Starling Forces 驱动 Vascular ↔ ISF 交换：
  NFP = (Pc - Pi) - (πc - πi)
  其中：
    Pc = 毛细血管静水压 ≈ 25 mmHg
    Pi = 组织静水压    ≈ -3 mmHg
    πc = 血浆胶体渗透压 ≈ 25 mmHg
    πi = 组织胶体渗透压 ≈ 5 mmHg

渗透压梯度驱动 ISF ↔ ICF 交换：
  水从低渗侧流向高渗侧，直到三室等渗
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from parameters import HCO3_EXTRACELLULAR_MEQ_L, HCO3_INTRACELLULAR_MEQ_L, PLASMA_COLLOID_OSMOTIC_MMHG

if TYPE_CHECKING:
    pass


# ── 生理常数 ────────────────────────────────────────────────────────────────

# 体液分布 (% 体重)
VASCULAR_FRACTION = 0.08    # 血管内液
ISF_FRACTION = 0.15         # 组织间液
ICF_FRACTION = 0.40         # 细胞内液
TBW_FRACTION = 0.60         # 总体液

# Starling 力量基准值
BASE_CAPILLARY_HYDROSTATIC_MMHG = 25.0    # Pc
BASE_TISSUE_HYDROSTATIC_MMHG = -3.0       # Pi
BASE_PLASMA_COLLOID_MMHG = PLASMA_COLLOID_OSMOTIC_MMHG  # πc（引用 parameters.py）
BASE_TISSUE_COLLOID_MMHG = 5.0            # πi

# 滤过系数
Kf_ML_MIN_MMHG = 0.5      # 毛细血管滤过系数 mL/min/mmHg
Kf_STARLING = 0.01         # 每步 Starling 交换系数（时间缩放）

# 渗透膜水通透性
LP_ISF_ICF = 0.002        # ISF↔ICF 水通透系数 mL/s/mOsm/kg

# 正常渗透压
NORMAL_OSMOLALITY = 295.0  # mOsm/kg

# 电解质分布
NA_EXTRACELLULAR = 145.0   # 细胞外 Na⁺ mEq/L
NA_INTRACELLULAR = 12.0    # 细胞内 Na⁺ mEq/L
K_EXTRACELLULAR = 4.2      # 细胞外 K⁺ mEq/L
K_INTRACELLULAR = 150.0    # 细胞内 K⁺ mEq/L
CL_EXTRACELLULAR = 105.0    # 细胞外 Cl⁻ mEq/L
CL_INTRACELLULAR = 4.0     # 细胞内 Cl⁻ mEq/L

# HCO₃⁻ 分布（引用 parameters.py 中的权威值）
HCO3_EXTRACELLULAR = HCO3_EXTRACELLULAR_MEQ_L
HCO3_INTRACELLULAR = HCO3_INTRACELLULAR_MEQ_L


class HendersonHasselbalch:
    """
    Henderson-Hasselbalch 酸碱缓冲系统

    pH = pKa + log10([HCO₃⁻] / (0.03 × PCO₂))
    其中 pKa = 6.1（碳酸解离常数）

    用于计算动脉血 pH，以及反向求解预期 HCO₃⁻ 或 PCO₂
    """

    PKa = 6.1
    CO2_SOLUBILITY = 0.03  # mmol/L/mmHg

    def __init__(self, hco3_meq_l: float, pco2_mmHg: float):
        self.hco3 = hco3_meq_l
        self.pco2 = pco2_mmHg
        self.ph = self._compute_ph()

    def _compute_ph(self) -> float:
        """计算 pH"""
        if self.pco2 <= 0:
            return 6.8  # 安全下限
        ratio = self.hco3 / (self.CO2_SOLUBILITY * self.pco2)
        if ratio <= 0:
            return 6.8
        raw = self.PKa + math.log10(ratio)
        return max(6.8, min(7.8, raw))

    def expected_pco2(self, hco3_meq_l: float, ph: float) -> float:
        """
        已知 HCO₃⁻ 和 pH，求预期 PCO₂

        PCO₂ = HCO₃⁻ / (0.03 × 10^(pH - pKa))
        """
        return hco3_meq_l / (self.CO2_SOLUBILITY * 10 ** (ph - self.PKa))

    def expected_hco3(self, pco2_mmHg: float, ph: float) -> float:
        """
        已知 PCO₂ 和 pH，求预期 HCO₃⁻

        HCO₃⁻ = 0.03 × PCO₂ × 10^(pH - pKa)
        """
        return self.CO2_SOLUBILITY * pco2_mmHg * 10 ** (ph - self.PKa)


class FluidCompartment:
    """
    三室体液模型：Vascular / ISF / ICF

    每步更新顺序：
      1. 计算 Starling forces → Vascular ↔ ISF 液体交换
      2. 计算渗透压梯度 → ISF ↔ ICF 水交换
      3. 更新电解质分布（简化：跟随水分布）
    """

    def __init__(self, weight_kg: float):
        self.w = weight_kg

        # ── 容量 (mL) ──
        self.vascular_volume_ml = VASCULAR_FRACTION * weight_kg * 1000.0
        self.isf_volume_ml = ISF_FRACTION * weight_kg * 1000.0
        self.icf_volume_ml = ICF_FRACTION * weight_kg * 1000.0
        self.total_body_water_ml = self.vascular_volume_ml + self.isf_volume_ml + self.icf_volume_ml

        # ── 渗透压 (mOsm/kg) — 初始等渗 ──
        self.vascular_osmolality = NORMAL_OSMOLALITY
        self.isf_osmolality = NORMAL_OSMOLALITY
        self.icf_osmolality = NORMAL_OSMOLALITY

        # ── Starling forces (mmHg) ──
        self.capillary_hydrostatic_mmHg = BASE_CAPILLARY_HYDROSTATIC_MMHG
        self.tissue_hydrostatic_mmHg = BASE_TISSUE_HYDROSTATIC_MMHG
        self.plasma_colloid_osmotic_mmHg = BASE_PLASMA_COLLOID_MMHG
        self.tissue_colloid_osmotic_mmHg = BASE_TISSUE_COLLOID_MMHG

        # ── 电解质 (mEq/L) ──
        self.vascular_na_meq_l = NA_EXTRACELLULAR
        self.vascular_k_meq_l = K_EXTRACELLULAR
        self.vascular_cl_meq_l = CL_EXTRACELLULAR
        self.vascular_hco3_meq_l = HCO3_EXTRACELLULAR

        self.isf_na_meq_l = NA_EXTRACELLULAR
        self.isf_k_meq_l = K_EXTRACELLULAR
        self.isf_cl_meq_l = CL_EXTRACELLULAR
        self.isf_hco3_meq_l = HCO3_EXTRACELLULAR

        self.icf_na_meq_l = NA_INTRACELLULAR
        self.icf_k_meq_l = K_INTRACELLULAR
        self.icf_cl_meq_l = CL_INTRACELLULAR
        self.icf_hco3_meq_l = HCO3_INTRACELLULAR

        # 累计
        self.cumulative_vascular_input_ml = 0.0
        self.cumulative_vascular_loss_ml = 0.0

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: vascular_volume, isf_volume, icf_volume
    # 输出端口（供其他模块）: starling_flow, osmotic_shift, nfp

    def derivatives(self, dt: float, map_input: float = None) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Args:
            dt: 时间步长（秒）
            map_input: 平均动脉压 mmHg（影响毛细血管静水压，若为 None 则用当前值）

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数（mL/s）
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        if map_input is None:
            map_input = self.capillary_hydrostatic_mmHg

        # ── 1. Starling Forces（代数） ─────────────────────────────────────────
        hydrostatic_gradient = map_input - BASE_TISSUE_HYDROSTATIC_MMHG
        osmotic_gradient = BASE_PLASMA_COLLOID_MMHG - BASE_TISSUE_COLLOID_MMHG
        nfp = hydrostatic_gradient - osmotic_gradient

        # ── 2. ISF↔ICF 渗透压梯度（代数） ───────────────────────────────────
        isf_osm = 2.0 * self.isf_na_meq_l
        icf_osm = 2.0 * self.icf_k_meq_l
        osmotic_gradient_isf_icf = isf_osm - icf_osm

        # ── 3. 交换量（导数 = 速率，不乘 dt） ────────────────────────────────
        # Starling: exchange_mL/min = Kf × NFP
        starling_rate_ml_min = Kf_ML_MIN_MMHG * nfp
        # 转换为 mL/s
        starling_rate_ml_s = starling_rate_ml_min / 60.0

        # 限幅（稳定区域，速率上限 mL/s）
        max_rate = min(abs(self.vascular_volume_ml), abs(self.isf_volume_ml)) * 0.05
        starling_rate_ml_s = max(-max_rate, min(max_rate, starling_rate_ml_s))

        # Osmotic: shift_mL/s = LP × osmotic_gradient
        osmotic_rate_ml_s = LP_ISF_ICF * osmotic_gradient_isf_icf
        max_osm_rate = min(self.isf_volume_ml, self.icf_volume_ml) * 0.02
        osmotic_rate_ml_s = max(-max_osm_rate, min(max_osm_rate, osmotic_rate_ml_s))

        dV_vascular = -starling_rate_ml_s
        dV_isf = starling_rate_ml_s - osmotic_rate_ml_s
        dV_icf = osmotic_rate_ml_s

        dydt = {
            "V_vascular": dV_vascular,
            "V_isf": dV_isf,
            "V_icf": dV_icf,
        }

        outputs = {
            "starling_flow_mL_min": starling_rate_ml_min,
            "osmotic_shift_mL_min": osmotic_rate_ml_s * 60.0,
            "nfp_mmHg": nfp,
            "vascular_osmolality": self.vascular_osmolality,
            "isf_osmolality": isf_osm,
            "icf_osmolality": icf_osm,
        }

        return dydt, outputs

    # ── 外部操作 ────────────────────────────────────────────────────────────

    def add_vascular_fluid(self, volume_ml: float) -> None:
        """外部输液：直接增加血管内液"""
        self.vascular_volume_ml += volume_ml
        self.cumulative_vascular_input_ml += volume_ml

    def remove_vascular_fluid(self, volume_ml: float) -> None:
        """外部抽血/失血：减少血管内液"""
        actual = min(volume_ml, self.vascular_volume_ml)
        self.vascular_volume_ml -= actual
        self.cumulative_vascular_loss_ml += actual

    def add_vascular_sodium(self, mEq: float) -> None:
        """向血管内添加钠（模拟高渗盐水）"""
        self.vascular_na_meq_l += mEq / self.vascular_volume_ml * 1000.0

    # ── Starling Forces ─────────────────────────────────────────────────────

    def compute_net_filtration_pressure(self) -> float:
        """
        净滤过压 NFP = (Pc - Pi) - (πc - πi)

        NFP > 0: 液体从血管滤出到 ISF
        NFP < 0: 液体从 ISF 重吸收回血管
        """
        hydrostatic_gradient = (
            self.capillary_hydrostatic_mmHg - self.tissue_hydrostatic_mmHg
        )
        osmotic_gradient = (
            self.plasma_colloid_osmotic_mmHg - self.tissue_colloid_osmotic_mmHg
        )
        return hydrostatic_gradient - osmotic_gradient

    def _compute_starling_exchange(self, dt: float) -> float:
        """
        计算 Starling 液体交换量 (mL)

        Args:
            dt: 时间步长（秒）

        Returns:
            正值 = 血管→ISF（滤出），负值 = ISF→血管（重吸收）
        """
        nfp = self.compute_net_filtration_pressure()
        # 交换量 = Kf × NFP × dt(min)
        exchange_ml = Kf_ML_MIN_MMHG * nfp * (dt / 60.0)
        # 限制：不能超过隔室可用液体的 5%（防止数值不稳定）
        max_out = self.vascular_volume_ml * 0.05
        max_in = self.isf_volume_ml * 0.05
        exchange_ml = max(-max_in, min(max_out, exchange_ml))
        return exchange_ml

    def _exchange_electrolytes_starling(self, flow_ml: float) -> None:
        """
        Starling 交换时，血管↔ISF 之间的小分子电解质（Na⁺、Cl⁻、HCO₃⁻）跟随水流动。
        K⁺ 不通透（细胞内为主），不参与 Starling 交换。

        对流运输：溶质从源室移动到目标室，浓度为源室浓度。
        质量平衡：运输后浓度 = (原总量 ± 运输量) / (原体积 ± 流量)
        """
        if abs(flow_ml) < 1e-9:
            return
        flow_l = flow_ml / 1000.0
        abs_flow_l = abs(flow_l)

        if flow_ml > 0:
            # 血管 → ISF
            src_vol_l = self.vascular_volume_ml / 1000.0
            dst_vol_l = self.isf_volume_ml / 1000.0
            src_na = self.vascular_na_meq_l
            src_cl = self.vascular_cl_meq_l
            src_hco3 = self.vascular_hco3_meq_l
            # 运输溶质量 = 滤过液量 × 血浆浓度
            t_na = abs_flow_l * src_na
            t_cl = abs_flow_l * src_cl
            t_hco3 = abs_flow_l * src_hco3
            # 新浓度 = (原总量 - 运输量) / (原体积 - 流量)
            new_src_vol = src_vol_l - flow_l
            new_dst_vol = dst_vol_l + flow_l
            if new_src_vol > 1e-9:
                self.vascular_na_meq_l = (src_na * src_vol_l - t_na) / new_src_vol
                self.vascular_cl_meq_l = (src_cl * src_vol_l - t_cl) / new_src_vol
                self.vascular_hco3_meq_l = (src_hco3 * src_vol_l - t_hco3) / new_src_vol
            if new_dst_vol > 1e-9:
                self.isf_na_meq_l = (self.isf_na_meq_l * dst_vol_l + t_na) / new_dst_vol
                self.isf_cl_meq_l = (self.isf_cl_meq_l * dst_vol_l + t_cl) / new_dst_vol
                self.isf_hco3_meq_l = (self.isf_hco3_meq_l * dst_vol_l + t_hco3) / new_dst_vol
        else:
            # ISF → 血管
            src_vol_l = self.isf_volume_ml / 1000.0
            dst_vol_l = self.vascular_volume_ml / 1000.0
            src_na = self.isf_na_meq_l
            src_cl = self.isf_cl_meq_l
            src_hco3 = self.isf_hco3_meq_l
            t_na = abs_flow_l * src_na
            t_cl = abs_flow_l * src_cl
            t_hco3 = abs_flow_l * src_hco3
            new_src_vol = src_vol_l - abs_flow_l
            new_dst_vol = dst_vol_l + abs_flow_l
            if new_src_vol > 1e-9:
                self.isf_na_meq_l = (src_na * src_vol_l - t_na) / new_src_vol
                self.isf_cl_meq_l = (src_cl * src_vol_l - t_cl) / new_src_vol
                self.isf_hco3_meq_l = (src_hco3 * src_vol_l - t_hco3) / new_src_vol
            if new_dst_vol > 1e-9:
                self.vascular_na_meq_l = (self.vascular_na_meq_l * dst_vol_l + t_na) / new_dst_vol
                self.vascular_cl_meq_l = (self.vascular_cl_meq_l * dst_vol_l + t_cl) / new_dst_vol
                self.vascular_hco3_meq_l = (self.vascular_hco3_meq_l * dst_vol_l + t_hco3) / new_dst_vol

    # ── 渗透压平衡 ─────────────────────────────────────────────────────────

    def _update_osmolality(self) -> None:
        """
        根据容量和溶质计算各室渗透压

        简化：渗透压 ∝ 溶质总量 / 液体量
        基准：正常 295 mOsm/kg 对应正常容量
        """
        # 血管渗透压（主要由 Na⁺ 和 Cl⁻ 决定）
        # Posm ≈ 2×[Na] + [BUN]/2.8 + [Glucose]/18
        # 简化：Posm = 2 × Na⁺（细胞外液主要渗透活性物质）
        self.vascular_osmolality = 2.0 * self.vascular_na_meq_l
        self.isf_osmolality = 2.0 * self.isf_na_meq_l
        # ICF 渗透压：由 K⁺ 主导
        self.icf_osmolality = 2.0 * self.icf_k_meq_l

    def _compute_osmotic_water_shift(self, dt: float) -> float:
        """
        渗透压梯度驱动的 ISF ↔ ICF 水交换

        水从低渗侧流向高渗侧，直到等渗

        Args:
            dt: 时间步长（秒）

        Returns:
            正值 = ISF→ICF，负值 = ICF→ISF
        """
        osmotic_gradient = self.isf_osmolality - self.icf_osmolality
        shift_ml = LP_ISF_ICF * osmotic_gradient * dt
        # 限制：不能超过隔室可用液体的 2%
        max_shift = min(self.isf_volume_ml, self.icf_volume_ml) * 0.02
        shift_ml = max(-max_shift, min(max_shift, shift_ml))
        return shift_ml

    def _exchange_electrolytes_osmotic(self, shift_ml: float) -> None:
        """
        ISF↔ICF 水交换时的电解质再分布。

        ISF 侧：Na⁺、Cl⁻、HCO₃⁻ 跟随水移动（稀释/浓缩效应）
        ICF 侧：K⁺ 跟随水移动

        注意：渗透压平衡只移动水，不主动转运溶质。
        但由于水移动导致体积变化，浓度会被动变化。
        """
        if abs(shift_ml) < 1e-9:
            return
        shift_l = shift_ml / 1000.0
        abs_shift_l = abs(shift_l)

        if shift_ml > 0:
            # 水从 ISF → ICF
            isf_vol_l = self.isf_volume_ml / 1000.0
            icf_vol_l = self.icf_volume_ml / 1000.0
            # ISF 失去水 → Na⁺/Cl⁻/HCO₃⁻ 浓缩（总量不变，体积减小）
            new_isf_vol = isf_vol_l - shift_l
            if new_isf_vol > 1e-9:
                self.isf_na_meq_l = self.isf_na_meq_l * isf_vol_l / new_isf_vol
                self.isf_cl_meq_l = self.isf_cl_meq_l * isf_vol_l / new_isf_vol
                self.isf_hco3_meq_l = self.isf_hco3_meq_l * isf_vol_l / new_isf_vol
            # ICF 获得水 → K⁺ 稀释
            new_icf_vol = icf_vol_l + shift_l
            if new_icf_vol > 1e-9:
                self.icf_k_meq_l = self.icf_k_meq_l * icf_vol_l / new_icf_vol
        else:
            # 水从 ICF → ISF
            isf_vol_l = self.isf_volume_ml / 1000.0
            icf_vol_l = self.icf_volume_ml / 1000.0
            # ICF 失去水 → K⁺ 浓缩
            new_icf_vol = icf_vol_l - abs_shift_l
            if new_icf_vol > 1e-9:
                self.icf_k_meq_l = self.icf_k_meq_l * icf_vol_l / new_icf_vol
            # ISF 获得水 → Na⁺/Cl⁻/HCO₃⁻ 稀释
            new_isf_vol = isf_vol_l + abs_shift_l
            if new_isf_vol > 1e-9:
                self.isf_na_meq_l = self.isf_na_meq_l * isf_vol_l / new_isf_vol
                self.isf_cl_meq_l = self.isf_cl_meq_l * isf_vol_l / new_isf_vol
                self.isf_hco3_meq_l = self.isf_hco3_meq_l * isf_vol_l / new_isf_vol

    # ── 主计算 ─────────────────────────────────────────────────────────────

    def compute(self, dt: float) -> dict:
        """
        推进三室模型一个时间步

        Args:
            dt: 时间步长（秒）

        Returns:
            状态 dict
        """
        # Step 1: Starling exchange (Vascular ↔ ISF)
        starling_flow = self._compute_starling_exchange(dt)
        self._exchange_electrolytes_starling(starling_flow)
        self.vascular_volume_ml -= starling_flow
        self.isf_volume_ml += starling_flow

        # Step 2: 更新渗透压
        self._update_osmolality()

        # Step 3: 渗透压平衡 (ISF ↔ ICF)
        osmotic_shift = self._compute_osmotic_water_shift(dt)
        self._exchange_electrolytes_osmotic(osmotic_shift)
        self.isf_volume_ml -= osmotic_shift
        self.icf_volume_ml += osmotic_shift

        # Step 4: 重新计算渗透压（水移动后）
        self._update_osmolality()

        # 更新总液体量
        self.total_body_water_ml = (
            self.vascular_volume_ml + self.isf_volume_ml + self.icf_volume_ml
        )

        return {
            "vascular_ml": round(self.vascular_volume_ml, 1),
            "isf_ml": round(self.isf_volume_ml, 1),
            "icf_ml": round(self.icf_volume_ml, 1),
            "starling_flow_ml": round(starling_flow, 3),
            "osmotic_shift_ml": round(osmotic_shift, 3),
            "nfp_mmHg": round(self.compute_net_filtration_pressure(), 2),
        }

    # ── 输出 ───────────────────────────────────────────────────────────────

    def summary(self) -> dict:
        return {
            "vascular_ml": round(self.vascular_volume_ml, 1),
            "isf_ml": round(self.isf_volume_ml, 1),
            "icf_ml": round(self.icf_volume_ml, 1),
            "total_water_ml": round(self.total_body_water_ml, 1),
            "osmolality_vascular": round(self.vascular_osmolality, 1),
            "osmolality_icf": round(self.icf_osmolality, 1),
        }
