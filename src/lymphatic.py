"""
Lymphatic / Spleen Module - 淋巴/脾脏系统
建模淋巴循环 + 脾脏储血功能:

  1. 间质液回流：血浆漏出 → 淋巴重吸收（维持血浆容量）
  2. 脾脏储血：应急时动员（失血、休克时释放）
  3. 免疫细胞运输：白细胞/淋巴细胞循环池
  4. 脂质吸收：肠道吸收的脂肪通过淋巴运送

FactorCommand 目标: blood.plasma_volume_mL, blood.platelet_K_uL,
                    blood.splenic_reserve_mL
Step: 4.75 (endocrine之后, neuro之前)
"""

from src.common_types import FactorCommand


class LymphaticModule:

    # ── Phase 5: I/O contract (declarative, no behavior change) ────────
    INPUTS: tuple[str, ...] = ('map_input', 'hr_input', 'cytokine_input', 'gut_fat_absorption', 'isf_input')
    OUTPUTS: tuple[str, ...] = ('splenic_reserve_mL', 'lymph_flow_rate', 'interstitial_fluid_mL')
    READS_BLOOD: tuple[str, ...] = ('MAP_mmHg', 'heart_rate_bpm', 'cytokine_level', 'splenic_reserve_mL', 'lymph_flow_mL_min', 'interstitial_fluid_mL')
    WRITES_BLOOD: tuple[str, ...] = ('splenic_reserve_mL', 'lymph_flow_mL_min', 'interstitial_fluid_mL')
    """
    淋巴/脾脏模块: 淋巴循环 + 脾脏储血

    设计原则:
      - 状态存储于 self.blood.* (共享读写)
      - FactorCommand 用于写入其他模块(立即apply)
      - Step 4.75 (endocrine之后, neuro之前)
      - 脾脏作为血液储备，应急时动员
    """

    # 脾脏最大储血量 (mL/kg)
    _SPLENIC_RESERVE_MAX_ML_KG = 5.0   # ~5 mL/kg
    # 脾脏动员阈值（平均动脉压 mmHg）
    _SPLENIC_MOBILIZATION_MAP_THRESHOLD = 60.0
    # 正常淋巴回流速率 (mL/min)
    _BASELINE_LYMPH_FLOW = 3.0

    def __init__(self, weight_kg: float, blood):
        self.w = weight_kg
        self.blood = blood  # BloodCompartment 引用

        # 脾脏储血量 (mL)
        self.splenic_reserve_mL = min(100.0, self.w * self._SPLENIC_RESERVE_MAX_ML_KG)

        # 淋巴回流速率 (mL/min)
        self.lymph_flow_rate = self._BASELINE_LYMPH_FLOW

        # 间质液总量 (mL)
        self.interstitial_fluid_mL = self.w * 40.0  # ≈40 mL/kg

        # 免疫细胞储备 (×10³/μL 当量)
        self.immune_cell_reserve = 5.0

        # 脾脏动员状态
        self._splenic_mobilizing = False
        self._splenic_mobilization_rate = 0.0

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: splenic_reserve_mL, interstitial_fluid_mL
    # 输出端口（供其他模块）: splenic_reserve_mL, lymph_flow_rate, interstitial_fluid_mL, immune_cell_reserve

    def derivatives(self, dt: float, map_input: float = None, hr_input: float = None, cytokine_input: float = None, gut_fat_absorption: bool = False) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        dt_min = dt / 60.0

        # ── 脾脏储血动力学 ─────────────────────────────────────────────────
        # 低灌注/休克 → 脾脏动员释放储血；恢复期缓慢充盈
        map_mmHg = map_input if map_input is not None else self.blood.MAP_mmHg
        hr = hr_input if hr_input is not None else self.blood.heart_rate_bpm

        if map_mmHg < self._SPLENIC_MOBILIZATION_MAP_THRESHOLD:
            deficit = self._SPLENIC_MOBILIZATION_MAP_THRESHOLD - map_mmHg
            mobilization_rate = deficit / 40.0 * 10.0  # 最大 ~10 mL/min
            self._splenic_mobilizing = True
            self._splenic_mobilization_rate = mobilization_rate
        elif hr > 120:
            excess = hr - 120
            mobilization_rate = excess / 60.0 * 5.0  # 最大 ~5 mL/min
            self._splenic_mobilizing = True
            self._splenic_mobilization_rate = mobilization_rate
        else:
            self._splenic_mobilizing = False
            self._splenic_mobilization_rate = 0.0

        max_reserve = self.w * self._SPLENIC_RESERVE_MAX_ML_KG

        if self._splenic_mobilizing and self.splenic_reserve_mL > 10.0:
            # 动员储血 → 血浆容量补充
            dSplenic = -self._splenic_mobilization_rate * dt_min
        elif not self._splenic_mobilizing and self.splenic_reserve_mL < max_reserve * 0.9:
            # 恢复期：脾脏缓慢充盈（恢复最多至基准的 90%）
            refill_rate = 0.5  # mL/min
            dSplenic = refill_rate * dt_min
        else:
            dSplenic = 0.0

        new_splenic = max(0.0, min(max_reserve, self.splenic_reserve_mL + dSplenic))
        dSplenic_final = (new_splenic - self.splenic_reserve_mL) / 1.0
        self.splenic_reserve_mL = new_splenic

        # ── 淋巴回流速率（代数） ───────────────────────────────────────────
        cytokine = cytokine_input if cytokine_input is not None else self.blood.cytokine_level
        lymph_flow = self._BASELINE_LYMPH_FLOW

        if cytokine > 0.4:
            capillary_leak_extra = (cytokine - 0.4) / 0.6 * 5.0
            lymph_flow += capillary_leak_extra

        if gut_fat_absorption:
            lymph_flow += 2.0

        self.lymph_flow_rate = max(0.5, min(20.0, lymph_flow))
        self.blood.lymph_flow_mL_min = self.lymph_flow_rate

        # ── 间质液动力学 ───────────────────────────────────────────────────
        capillary_leak = 0.0
        if cytokine > 0.4:
            leak_rate = (cytokine - 0.4) / 0.6 * 20.0
            capillary_leak = leak_rate * dt_min

        lymph_drainage = self.lymph_flow_rate * dt_min
        dISF = capillary_leak - lymph_drainage

        max_isf = self.w * 60.0
        # Soft floor: compute dISF but clamp it so derivative doesn't explode at dt=1e-9
        # At dt=1e-9, dISF/dt = (dISF/dt) would be enormous; instead compute per-second rate
        raw_dISF = dISF  # mL change in this call (already in mL units)
        if raw_dISF < 0 and self.interstitial_fluid_mL + raw_dISF < 1000.0:
            # Would hit floor — clamp dISF to avoid discontinuity at dt=1e-9
            raw_dISF = 1000.0 - self.interstitial_fluid_mL - 0.01  # allow tiny negative room
        new_isf = max(1000.0, min(max_isf, self.interstitial_fluid_mL + raw_dISF))
        dISF_final = (new_isf - self.interstitial_fluid_mL) / 60.0  # per-second rate (not /dt)
        self.interstitial_fluid_mL = new_isf

        self.blood.interstitial_fluid_mL = self.interstitial_fluid_mL
        self.blood.splenic_reserve_mL = self.splenic_reserve_mL

        dydt = {
            "splenic_reserve_mL": dSplenic_final,
            "interstitial_fluid_mL": dISF_final,
        }

        outputs = {
            "splenic_reserve_mL": self.splenic_reserve_mL,
            "lymph_flow_rate": self.lymph_flow_rate,
            "interstitial_fluid_mL": self.interstitial_fluid_mL,
            "immune_cell_reserve": self.immune_cell_reserve,
        }

        return dydt, outputs

    def _compute_splenic_reserve_change(self, dt: float, heart_state: dict) -> float:
        """
        计算脾脏储血变化。

        脾脏储血动员触发条件：
        1. MAP < 60 mmHg（休克/低灌注）→ 脾脏收缩释放储血
        2. 心动过速（HR > 120）→ 交感激活 → 脾脏收缩

        Returns:
            脾脏储血变化量 (mL/步)
        """
        map_mmHg = heart_state.get("MAP_mmHg", 90.0)
        hr = heart_state.get("heart_rate_bpm", 80.0)

        # 低灌注 → 脾脏动员（释放储血）
        if map_mmHg < self._SPLENIC_MOBILIZATION_MAP_THRESHOLD:
            deficit = self._SPLENIC_MOBILIZATION_MAP_THRESHOLD - map_mmHg
            mobilization_rate = deficit / 40.0 * 10.0  # 最大 ~10 mL/min
            self._splenic_mobilizing = True
            self._splenic_mobilization_rate = mobilization_rate
        elif hr > 120:
            excess = hr - 120
            mobilization_rate = excess / 60.0 * 5.0  # 最大 ~5 mL/min
            self._splenic_mobilizing = True
            self._splenic_mobilization_rate = mobilization_rate
        else:
            self._splenic_mobilizing = False
            self._splenic_mobilization_rate = 0.0

        dt_min = dt / 60.0
        reserve_change = 0.0

        if self._splenic_mobilizing and self.splenic_reserve_mL > 10.0:
            # 动员储血 → 血浆容量补充
            reserve_change = -self._splenic_mobilization_rate * dt_min
        elif not self._splenic_mobilizing and self.splenic_reserve_mL < self.w * self._SPLENIC_RESERVE_MAX_ML_KG:
            # 恢复期：脾脏缓慢充盈（恢复最多至基准的 90%）
            refill_rate = 0.5  # mL/min
            reserve_change = refill_rate * dt_min

        return reserve_change

    def _compute_lymph_flow(self, dt: float, gut_state: dict, immune_state: dict) -> float:
        """
        计算淋巴回流速率。

        影响因素：
        1. 基础淋巴流（骨骼肌泵驱动）
        2. 毛细血管漏（cytokine > 0.4 → 间质液 ↑ → 淋巴流 ↑）
        3. 肠道脂质吸收（脂肪以乳糜形式经淋巴运送）

        Returns:
            淋巴回流速率 (mL/min)
        """
        dt_min = dt / 60.0

        # 1. 基础淋巴流
        flow = self._BASELINE_LYMPH_FLOW

        # 2. 炎症/毛细血管漏 → 淋巴流代偿性增加
        cytokine = self.blood.cytokine_level
        if cytokine > 0.4:
            capillary_leak_extra = (cytokine - 0.4) / 0.6 * 5.0  # 最多 +5 mL/min
            flow += capillary_leak_extra

        # 3. 肠道脂质吸收 → 乳糜流增加
        fat_absorption = gut_state.get("fat_absorption_active", False)
        if fat_absorption:
            flow += 2.0  # 餐后乳糜流增加

        return max(0.5, min(20.0, flow))

    def _compute_interstitial_fluid(self, dt: float) -> float:
        """
        计算间质液变化。

        间质液来源：
        1. 毛细血管漏出液（血浆 → 间质）
        2. 毛细血管再吸收（间质 → 血浆，受淋巴泵驱动）

        Returns:
            间质液体积变化 (mL/步)
        """
        dt_min = dt / 60.0

        # 毛细血管漏（炎症驱动）
        cytokine = self.blood.cytokine_level
        capillary_leak = 0.0
        if cytokine > 0.4:
            leak_rate = (cytokine - 0.4) / 0.6 * 20.0  # 最多 20 mL/min
            capillary_leak = leak_rate * dt_min

        # 淋巴回流带走间质液（生理排出途径）
        lymph_drainage = self.lymph_flow_rate * dt_min

        net_change = capillary_leak - lymph_drainage
        return net_change

    def compute(self, dt: float, gut_state: dict, immune_state: dict) -> dict:
        """
        计算淋巴/脾脏状态和FactorCommand

        Args:
            dt: 时间步长 (秒)
            gut_state: gut.compute() 返回的 dict
            immune_state: immune.compute() 返回的 dict (当前未使用，保留接口)

        Returns:
            dict包含所有状态变量 + factor_commands列表
        """
        # 获取当前心率用于脾脏动员判断
        # heart_state 通过 gut_state 间接获得（gut.compute 接收了 CO）
        heart_state = gut_state.get("_heart_state", {"MAP_mmHg": 90.0, "heart_rate_bpm": 80.0})

        # ── 1. 脾脏储血 ────────────────────────────────────────────────
        splenic_change = self._compute_splenic_reserve_change(dt, heart_state)
        self.splenic_reserve_mL += splenic_change
        max_reserve = self.w * self._SPLENIC_RESERVE_MAX_ML_KG
        self.splenic_reserve_mL = max(0.0, min(max_reserve, self.splenic_reserve_mL))
        self.blood.splenic_reserve_mL = self.splenic_reserve_mL

        # ── 2. 淋巴回流 ────────────────────────────────────────────────
        self.lymph_flow_rate = self._compute_lymph_flow(dt, gut_state, immune_state)
        self.blood.lymph_flow_mL_min = self.lymph_flow_rate

        # ── 3. 间质液 ────────────────────────────────────────────────
        isf_change = self._compute_interstitial_fluid(dt)
        self.interstitial_fluid_mL += isf_change
        max_isf = self.w * 60.0  # 最大间质液
        self.interstitial_fluid_mL = max(1000.0, min(max_isf, self.interstitial_fluid_mL))
        self.blood.interstitial_fluid_mL = self.interstitial_fluid_mL

        # ── 4. FactorCommands ─────────────────────────────────────────
        factor_commands = []

        return {
            "splenic_reserve_mL": round(self.splenic_reserve_mL, 1),
            "lymph_flow_rate": round(self.lymph_flow_rate, 2),
            "interstitial_fluid_mL": round(self.interstitial_fluid_mL, 0),
            "immune_cell_reserve": round(self.immune_cell_reserve, 2),
            "factor_commands": factor_commands,
        }

    def summary(self) -> dict:
        """返回淋巴/脾脏状态摘要(用于历史记录)"""
        return {
            "splenic_reserve_mL": round(self.splenic_reserve_mL, 1),
            "lymph_flow_rate": round(self.lymph_flow_rate, 2),
            "interstitial_fluid_mL": round(self.interstitial_fluid_mL, 0),
            "immune_cell_reserve": round(self.immune_cell_reserve, 2),
        }