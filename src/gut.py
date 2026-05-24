"""
Gut Module - 肠道吸收系统
建模肠道运动、营养吸收、门静脉血流、肠道菌群
"""

from parameters import *


class GutModule:
    """
    肠道模块：模拟肠道吸收功能和门静脉血流

    核心变量：
    - gut_motility: 肠道蠕动 (0-1, 影响吸收速率)
    - barrier_integrity: 肠道屏障完整性 (0-1, 1=健康)
    - microbiome_activity: 肠道菌群活性 (0-1)
    - portal_blood_flow: 门静脉血流量 mL/min (≈15% CO)

    数据流：
    compute(CO) → 更新门户吸收缓存 (blood.amino_acids_g_L, blood.fatty_acids_mmol_L)
                 →gut_state (返回给 liver)
    """

    def __init__(
        self,
        weight_kg: float,
        blood,
        base_absorption_rate: float = 0.95,
    ):
        self.w = weight_kg
        self.blood = blood  # 血液隔室引用

        # 肠道运动性 (0-1, 正常 ~0.8)
        self.gut_motility = 0.8

        # 肠道屏障完整性 (0-1, 正常 ~1.0)
        self.barrier_integrity = 1.0

        # 菌群活性 (0-1, 正常 ~0.6)
        self.microbiome_activity = 0.6

        # 基础吸收效率 (0-1)
        self.base_absorption_rate = base_absorption_rate

        # 门静脉血流量 (≈15% CO, 会随 CO 动态变化)
        self.portal_blood_flow = 0.15 * base_cardiac_output_ml_min(weight_kg)

        # 短链脂肪酸 (SCFA) 浓度 mmol/L
        self.SCFA_mmol_L = 0.2

        # 肠道营养吸收缓存（给 liver 的中间值）
        self._portal_glucose_absorption_g_min = 0.0
        self._portal_amino_absorption_g_min = 0.0
        self._portal_fat_absorption_g_min = 0.0

        # 肠腔营养池（来自进食事件的营养）
        self.lumen_glucose_g = 0.0      # 肠腔可吸收葡萄糖 g
        self.lumen_amino_g = 0.0         # 肠腔可吸收氨基酸 g
        self.lumen_fat_g = 0.0           # 肠腔可吸收脂肪 g

        # 时间常数（模拟分钟）
        self._TAU_GASTRIC_EMPTYING = 5.0   # 胃排空时间常数 min
        self._TAU_ABSORPTION = 3.0         # 吸收时间常数 min

    # ── derivatives() — 供 solve_ivp Radau 调用 ──────────────────────────────
    # 状态变量（进入统一 y 向量）: gut_motility, barrier_integrity, microbiome_activity
    # 输出端口（供其他模块）: portal_flow, amino_acids_g_L, fatty_acids_mmol_L

    def derivatives(self, dt: float, co_input: float) -> tuple[dict, dict]:
        """
        返回本模块所有状态变量的导数 + 输出端口（供统一 ODE 求解器）。

        Args:
            dt: 时间步长（秒）
            co_input: 心输出量 mL/min

        Returns:
            (dydt, outputs):
              dydt: dict[str, float] — 状态变量导数
              outputs: dict[str, float] — 供其他模块使用的输出端口
        """
        # ── 1. 门静脉血流（代数） ─────────────────────────────────────────────
        portal_flow = 0.15 * co_input

        # ── 2. 胃排空（代数，腔内营养作为缓存） ───────────────────────────────
        # 一阶衰减：dLumen/dt = -Lumen / tau（tau 已从分钟转为秒）
        tau_gastric_s = self._TAU_GASTRIC_EMPTYING * 60.0
        dLumen_glucose = -self.lumen_glucose_g / tau_gastric_s if self.lumen_glucose_g > 0 else 0.0
        dLumen_amino = -self.lumen_amino_g / tau_gastric_s if self.lumen_amino_g > 0 else 0.0
        dLumen_fat = -self.lumen_fat_g / tau_gastric_s if self.lumen_fat_g > 0 else 0.0

        # ── 3. 吸收（代数） ───────────────────────────────────────────────────
        efficiency = (
            self.base_absorption_rate
            * self.gut_motility
            * self.barrier_integrity
            * (0.5 + 0.5 * self.microbiome_activity)
        )
        glucose_rate = (self.lumen_glucose_g / self._TAU_ABSORPTION) if self.lumen_glucose_g > 0 else 0.0
        amino_rate = (self.lumen_amino_g / self._TAU_ABSORPTION) if self.lumen_amino_g > 0 else 0.0
        fat_rate = (self.lumen_fat_g / self._TAU_ABSORPTION) if self.lumen_fat_g > 0 else 0.0

        glucose_abs = min(self.lumen_glucose_g, glucose_rate * dt * efficiency)
        amino_abs = min(self.lumen_amino_g, amino_rate * dt * efficiency)
        fat_abs = min(self.lumen_fat_g, fat_rate * dt * efficiency)

        # ── 4. SCFA（慢动力学，τ=10s） ─────────────────────────────────────────
        target_scfa = self.microbiome_activity * 0.3
        tau_scfa = 10.0
        dSCFA = (target_scfa - self.SCFA_mmol_L) / tau_scfa

        # ── 5. 血液门静脉缓存（代数） ────────────────────────────────────────
        if portal_flow > 0:
            amino_conc_g_L = (amino_abs / portal_flow) * 1000.0
            fat_conc_mmol_L = (fat_abs / portal_flow) * 1000.0 / 0.885
            self.blood.amino_acids_g_L = max(0.0, amino_conc_g_L)
            self.blood.fatty_acids_mmol_L = max(0.0, fat_conc_mmol_L)
        else:
            self.blood.amino_acids_g_L = 0.0
            self.blood.fatty_acids_mmol_L = 0.0

        # ── 6. 存储吸收数据（供 liver 耦合） ─────────────────────────────────
        self._portal_glucose_absorption_g_min = glucose_abs / dt if dt > 0 else 0.0
        self._portal_amino_absorption_g_min = amino_abs / dt if dt > 0 else 0.0
        self._portal_fat_absorption_g_min = fat_abs / dt if dt > 0 else 0.0

        # 状态变量导数（慢变量，主要由外部因子驱动）
        # motility, barrier, microbiome 本身由疾病调制，这里设为其慢变导数为 0
        dydt = {
            "motility": 0.0,
            "barrier": 0.0,
            "microbiome": 0.0,
            "lumen_glucose": dLumen_glucose,
            "lumen_amino": dLumen_amino,
            "lumen_fat": dLumen_fat,
            "SCFA": dSCFA,
        }

        outputs = {
            "portal_blood_flow_mL_min": portal_flow,
            "amino_acids_g_L": self.blood.amino_acids_g_L,
            "fatty_acids_mmol_L": self.blood.fatty_acids_mmol_L,
            "glucose_absorption_g_min": self._portal_glucose_absorption_g_min,
            "amino_absorption_g_min": self._portal_amino_absorption_g_min,
            "fat_absorption_g_min": self._portal_fat_absorption_g_min,
        }

        return dydt, outputs

    def _update_portal_flow(self, CO: float):
        """更新门静脉血流量（≈15% CO）"""
        self.portal_blood_flow = 0.15 * CO

    def _compute_gastric_emptying(self, dt: float) -> float:
        """
        胃排空：一阶滞后系统

        d(Lumen)/dt = -Lumen / τ
        τ 的单位是分钟，dt 的单位是秒 → 需要 dt_min = dt / 60.0
        """
        dt_min = dt / 60.0
        if self.lumen_glucose_g > 0.0:
            rate = self.lumen_glucose_g / self._TAU_GASTRIC_EMPTYING
            self.lumen_glucose_g = max(0.0, self.lumen_glucose_g - rate * dt_min)
        if self.lumen_amino_g > 0.0:
            rate = self.lumen_amino_g / self._TAU_GASTRIC_EMPTYING
            self.lumen_amino_g = max(0.0, self.lumen_amino_g - rate * dt_min)
        if self.lumen_fat_g > 0.0:
            rate = self.lumen_fat_g / self._TAU_GASTRIC_EMPTYING
            self.lumen_fat_g = max(0.0, self.lumen_fat_g - rate * dt_min)

    def _compute_absorption(self, dt: float) -> tuple[float, float, float]:
        """
        计算肠道吸收率 (g/min)

        吸收效率 = 基础效率 × 蠕动 × 屏障 × 菌群
        """
        efficiency = (
            self.base_absorption_rate
            * self.gut_motility
            * self.barrier_integrity
            * (0.5 + 0.5 * self.microbiome_activity)
        )

        # 吸收率 = 可吸收量 / 时间常数
        glucose_rate = (self.lumen_glucose_g / self._TAU_ABSORPTION) if self.lumen_glucose_g > 0 else 0.0
        amino_rate = (self.lumen_amino_g / self._TAU_ABSORPTION) if self.lumen_amino_g > 0 else 0.0
        fat_rate = (self.lumen_fat_g / self._TAU_ABSORPTION) if self.lumen_fat_g > 0 else 0.0

        # 应用效率（吸收进入门静脉）
        glucose_absorbed = min(self.lumen_glucose_g, glucose_rate * dt * efficiency)
        amino_absorbed = min(self.lumen_amino_g, amino_rate * dt * efficiency)
        fat_absorbed = min(self.lumen_fat_g, fat_rate * dt * efficiency)

        return glucose_absorbed / dt, amino_absorbed / dt, fat_absorbed / dt

    def _compute_microbiome(self, dt: float):
        """
        肠道菌群：产生短链脂肪酸 (SCFA)

        SCFA 主要来自纤维发酵
        简化：SCFA 稳态 = microbiome_activity × 0.3 mmol/L
        """
        target_scfa = self.microbiome_activity * 0.3
        self.SCFA_mmol_L += (target_scfa - self.SCFA_mmol_L) * dt / 10.0

    def add_food_intake(self, glucose_g: float, amino_g: float, fat_g: float):
        """
        添加肠腔营养（来自进食事件）

        Args:
            glucose_g: 葡萄糖 g
            amino_g: 氨基酸 g
            fat_g: 脂肪 g
        """
        self.lumen_glucose_g += glucose_g
        self.lumen_amino_g += amino_g
        self.lumen_fat_g += fat_g

    def compute(self, dt: float, cardiac_output: float) -> dict:
        """
        肠道计算主函数

        Args:
            dt: 时间步长 min
            cardiac_output: 心输出量 mL/min

        Returns:
            gut_state dict
        """
        # Step 1: 更新门静脉血流
        self._update_portal_flow(cardiac_output)

        # Step 2: 胃排空（肠腔营养进入小肠）
        self._compute_gastric_emptying(dt)

        # Step 3: 肠道吸收（进入门静脉）
        glucose_abs, amino_abs, fat_abs = self._compute_absorption(dt)

        # Step 4: 肠道菌群 SCFA
        self._compute_microbiome(dt)

        # Step 5: 更新血液门静脉缓存（liver 会在下一步读取）
        # 门静脉缓存 = 吸收率 / 门静脉血流量 → 浓度
        if self.portal_blood_flow > 0:
            # 转换为 g/L（葡萄糖：180 g/mol，氨基酸：平均 110 g/mol，脂肪：885 g/mol）
            glucose_conc_g_L = (glucose_abs / self.portal_blood_flow) * 1000.0  # g/L
            amino_conc_g_L = (amino_abs / self.portal_blood_flow) * 1000.0
            fat_conc_mmol_L = (fat_abs / self.portal_blood_flow) * 1000.0 / 0.885  # mmol/L

            self.blood.amino_acids_g_L = max(0.0, amino_conc_g_L)
            self.blood.fatty_acids_mmol_L = max(0.0, fat_conc_mmol_L)
        else:
            self.blood.amino_acids_g_L = 0.0
            self.blood.fatty_acids_mmol_L = 0.0

        # 存储吸收数据（用于 liver 耦合）
        self._portal_glucose_absorption_g_min = glucose_abs
        self._portal_amino_absorption_g_min = amino_abs
        self._portal_fat_absorption_g_min = fat_abs

        return {
            "portal_blood_flow_ml_min": round(self.portal_blood_flow, 1),
            "gut_motility": round(self.gut_motility, 3),
            "barrier_integrity": round(self.barrier_integrity, 3),
            "microbiome_activity": round(self.microbiome_activity, 3),
            "SCFA_mmol_L": round(self.SCFA_mmol_L, 3),
            "absorption_glucose_g_min": round(glucose_abs, 4),
            "absorption_amino_g_min": round(amino_abs, 4),
            "absorption_fat_g_min": round(fat_abs, 4),
            "lumen_glucose_g": round(self.lumen_glucose_g, 3),
            "lumen_amino_g": round(self.lumen_amino_g, 3),
            "lumen_fat_g": round(self.lumen_fat_g, 3),
        }

    def summary(self) -> dict:
        """返回肠道状态摘要"""
        return {
            "motility": round(self.gut_motility, 3),
            "barrier": round(self.barrier_integrity, 3),
            "microbiome": round(self.microbiome_activity, 3),
            "SCFA": round(self.SCFA_mmol_L, 3),
            "portal_flow": round(self.portal_blood_flow, 1),
        }