"""
PhysiologyEngine — 多系统耦合生理仿真核心引擎

设计原则（来自 Bioflow 参考）：
- 纯函数式 ODE 积分：无随机性、无全局状态、无时间相关副作用
- 硬失败参数验证：R ≤ 0, C ≤ 0, V ≤ 0 → ValueError
- 保守血容量更新：总血量守恒，不存在静默截断
- 生理层与游戏层隔离：PhysiologyEngine 不知晓疾病、事件、药剂概念

外部接口：
- 输入：FactorCommand 列表（由疾病/药剂模块生成）
- 输出：生理变量更新（通过 apply_factor 写回各器官模块）
"""

import logging
from dataclasses import dataclass, field
from typing import Literal

import numpy as np

from parameters import (
    DT_SECONDS,
    PLASMA_VOLUME_FRACTION,
    total_blood_volume_ml, stroke_volume_ml, base_cardiac_output_ml_min,
    tidal_volume_ml, base_minute_ventilation,
    renal_blood_flow_ml_min, gfr_ml_min, baseline_urine_output_ml_min,
)

from blood import BloodCompartment
from heart import HeartModule
from lung import LungModule
from kidney import KidneyModule
from toxicology import ToxicologyModule
from organ_health import OrganHealthTracker
from fluid import FluidCompartment, HendersonHasselbalch
from gut import GutModule
from liver import LiverModule
from endocrine import EndocrineModule
from neuro import NeuroModule
from immune import ImmuneModule

logger = logging.getLogger(__name__)


# ── FactorCommand 指令结构体 ─────────────────────────────────────────────────

@dataclass(frozen=True)
class FactorCommand:
    """
    单条因子指令：声明式地描述"对哪个参数执行什么操作"。

    Attributes:
        target: 参数路径，格式 "module.attr"（如 "heart.heart_rate"）
        op: 操作类型 — "multiply"（乘因子）/ "add"（加偏移）/ "set"（设绝对值）
        value: 操作数值
    """
    target: str
    op: Literal["multiply", "add", "set"]
    value: float


# ── 参数路径映射表 ───────────────────────────────────────────────────────────
# 所有可被子系统（疾病、药物、事件）修改的引擎参数，必须在此注册。
# 格式: "module.attr" → (engine_module_name, attribute_name)

_PARAM_PATHS: dict[str, tuple[str, str]] = {
    # 心脏
    "heart.heart_rate":           ("heart", "heart_rate"),
    "heart.contractility_factor": ("heart", "contractility_factor"),
    "heart.SVR":                  ("heart", "SVR"),
    "heart.MAP":                  ("heart", "mean_arterial_pressure"),
    "heart.CVP":                  ("heart", "central_venous_pressure"),
    "heart.blood_volume":         ("heart", "circulating_volume_ml"),
    "heart.stroke_volume":        ("heart", "stroke_volume"),
    # 肺
    "lung.diffusion_coefficient": ("lung", "diffusion_coefficient"),
    "lung.PaO2":                  ("lung", "alveolar_PO2"),
    "lung.PaCO2":                 ("lung", "alveolar_PCO2"),
    "lung.VQ_ratio":              ("lung", "VQ_ratio"),
    "lung.respiratory_rate":      ("lung", "respiratory_rate"),
    # 肾脏
    "kidney.GFR":                    ("kidney", "GFR"),
    "kidney.urine_output":           ("kidney", "urine_output"),
    "kidney.renal_blood_flow":       ("kidney", "renal_blood_flow"),
    "kidney._disease_gfr_multiplier": ("kidney", "_disease_gfr_multiplier"),
    # 血液
    "blood.potassium":            ("blood", "potassium_mEq_L"),
    "blood.pH":                   ("blood", "arterial_pH"),
    "blood.temperature":          ("blood", "core_temperature_C"),
    "blood.BUN":                  ("blood", "bun_mg_dL"),
    "blood.HCO3":                 ("fluid", "vascular_hco3_meq_l"),
    "blood.glucose":              ("blood", "glucose_mmol_L"),
    "blood.lactate":              ("blood", "lactate_mmol_L"),
    "blood.creatinine":           ("blood", "creatinine_mg_dL"),
    "blood.red_cell_volume_ml":   ("blood", "red_cell_volume_ml"),
    "blood.bilirubin_mg_dL":      ("blood", "bilirubin_mg_dL"),
    "blood.ketone_mmol_L":        ("blood", "ketone_mmol_L"),
    "blood.PLT":                  ("blood", "PLT"),
    # Liver/gut blood markers
    "blood.ALT":                  ("blood", "ALT_U_L"),
    "blood.AST":                  ("blood", "AST_U_L"),
    "blood.ALP":                  ("blood", "ALP_U_L"),
    "blood.GGT":                  ("blood", "GGT_U_L"),
    "blood.albumin":              ("blood", "albumin_g_dL"),
    "blood.ammonia":              ("blood", "ammonia_umol_L"),
    "blood.bile_acids":           ("blood", "bile_acids_umol_L"),
    "blood.amino_acids":         ("blood", "amino_acids_g_L"),
    "blood.fatty_acids":         ("blood", "fatty_acids_mmol_L"),
    # Gut
    "gut.motility":               ("gut", "gut_motility"),
    "gut.barrier_integrity":      ("gut", "barrier_integrity"),
    "gut.microbiome_activity":     ("gut", "microbiome_activity"),
    # Liver
    "liver.metabolic_activity":   ("liver", "metabolic_activity"),
    "liver.detox_capacity":        ("liver", "detox_capacity"),
    "liver.cyp450_activity":       ("liver", "cyp450_activity"),
    "liver.glycogen_fraction":    ("liver", "glycogen_fraction"),
    "liver.bilirubin_conjugation": ("liver", "bilirubin_conjugation"),
    # Endocrine
    "endocrine.T3_factor":         ("endocrine", "T3_factor"),
    "endocrine.metabolic_rate":    ("endocrine", "metabolic_rate"),
    "endocrine.T3_ng_dL":         ("endocrine", "T3_ng_dL"),
    "endocrine.insulin_factor":    ("endocrine", "insulin_factor"),
    "endocrine.glucagon_factor":   ("endocrine", "glucagon_factor"),
    "endocrine.cortisol_factor":   ("endocrine", "cortisol_factor"),
    "endocrine.cortisol_ug_dL":   ("endocrine", "cortisol_ug_dL"),
    "endocrine.HPA_axis":          ("endocrine", "HPA_axis"),
    "endocrine.epinephrine_pg_mL": ("endocrine", "epinephrine_pg_mL"),
    "endocrine.PTH_pg_mL":        ("endocrine", "PTH_pg_mL"),
    "endocrine.calcium_mg_dL":     ("endocrine", "calcium_mg_dL"),
    # Neuro
    "neuro.sympathetic_tone":        ("neuro", "sympathetic_tone"),
    "neuro.parasympathetic_tone":     ("neuro", "parasympathetic_tone"),
    "neuro.consciousness":           ("neuro", "consciousness"),
    "neuro.seizure":                ("neuro", "seizure"),
    "neuro.pain_level":             ("neuro", "pain_level"),
    "neuro.chemoreceptor_drive":    ("neuro", "chemoreceptor_drive"),
    # Immune
    "immune.cytokine_level":        ("immune", "cytokine_level"),
    "immune.wbc_count":             ("immune", "wbc_count"),
    "immune.crp_level":             ("immune", "crp_level"),
    "immune.acute_phase_response":  ("immune", "acute_phase_response"),
    "immune.immune_suppression":    ("immune", "immune_suppression"),
    "immune.coagulation_state":     ("immune", "coagulation_state"),
}

# 导出供外部使用
PARAM_PATHS = _PARAM_PATHS


@dataclass(frozen=True)
class PhysiologyInputs:
    """
    传递给 PhysiologyEngine.compute() 的外部输入。

    所有场外效应（毒理、药剂、疾病）通过 FactorCommand 表达，
    由 engine 在 step 开始前应用到对应模块。
    """
    svr_factor: float = 1.0          # ToxicologyModule 输出的外周阻力倍数
    factor_commands: list[FactorCommand] = field(default_factory=list)


class PhysiologyEngine:
    """
    纯生理计算引擎。

    给定当前器官状态和外部输入（FactorCommand），推进一个 dt 的 ODE 积分。

    与 Bioflow Phase 4.1 等价的 Virtual Vet 实现：
    - 保守体积更新（血量守恒）
    - 纯代数/ODE 耦合（无心率随机性）
    - 硬失败参数验证

    不包含：事件调度、疾病逻辑、药剂生成、日志记录
    """

    def __init__(self, body_weight_kg: float = 20.0):
        self.w = body_weight_kg

        # 计算体重缩放参数
        _tbv = total_blood_volume_ml(body_weight_kg)
        _sv  = stroke_volume_ml(body_weight_kg)
        _co  = base_cardiac_output_ml_min(body_weight_kg)
        _tv  = tidal_volume_ml(body_weight_kg)
        _mv  = base_minute_ventilation(body_weight_kg)
        _rbf = renal_blood_flow_ml_min(body_weight_kg)
        _gfr = gfr_ml_min(body_weight_kg)
        _urine = baseline_urine_output_ml_min(body_weight_kg)

        # 初始化血液隔室
        self.blood = BloodCompartment(
            total_volume_ml=_tbv,
            plasma_fraction=PLASMA_VOLUME_FRACTION
        )

        # 初始化器官模块
        self.heart = HeartModule(
            weight_kg=body_weight_kg, blood=self.blood,
            sv_ml=_sv, base_co_ml_min=_co,
        )
        self.lung = LungModule(
            weight_kg=body_weight_kg, blood=self.blood,
            tidal_vol_ml=_tv, base_minute_vent=_mv,
        )
        self.kidney = KidneyModule(
            weight_kg=body_weight_kg, blood=self.blood,
            base_gfr_ml_min=_gfr, base_rbf_ml_min=_rbf,
            base_urine_ml_min=_urine,
        )
        self.toxicology = ToxicologyModule(weight_kg=body_weight_kg)
        self.organ_health = OrganHealthTracker()
        self.fluid = FluidCompartment(weight_kg=body_weight_kg)
        self._hh = HendersonHasselbalch(
            hco3_meq_l=self.fluid.vascular_hco3_meq_l,
            pco2_mmHg=self.blood.arterial_PCO2_mmHg,
        )
        self.gut = GutModule(weight_kg=body_weight_kg, blood=self.blood)
        self.liver = LiverModule(weight_kg=body_weight_kg, blood=self.blood)
        self.endocrine = EndocrineModule(weight_kg=body_weight_kg, blood=self.blood)
        self.neuro = NeuroModule(weight_kg=body_weight_kg, blood=self.blood)
        self.immune = ImmuneModule(weight_kg=body_weight_kg, blood=self.blood, endocrine=self.endocrine)

        self.dt = DT_SECONDS

    def validate_parameters(self) -> None:
        """
        硬失败参数验证（Bioflow 模式）。

        对所有物理参数进行范围检查，无效时抛出 ValueError。
        与 Bioflow 的 "R ≤ 0 → ValueError" 原则一致。
        """
        # 心脏
        if not (0 < self.heart.heart_rate <= 300):
            raise ValueError(f"heart.heart_rate out of range: {self.heart.heart_rate}")
        if not (0 < self.heart.stroke_volume <= 500):
            raise ValueError(f"heart.stroke_volume out of range: {self.heart.stroke_volume}")
        if self.heart.SVR <= 0:
            raise ValueError(f"heart.SVR must be positive: {self.heart.SVR}")
        if self.heart.circulating_volume_ml <= 0:
            raise ValueError(f"heart.circulating_volume_ml must be positive: {self.heart.circulating_volume_ml}")
        if not (0 <= self.heart.contractility_factor <= 3.0):
            raise ValueError(f"heart.contractility_factor out of range: {self.heart.contractility_factor}")

        # 肺
        if self.lung.diffusion_coefficient < 0:
            raise ValueError(f"lung.diffusion_coefficient must be non-negative: {self.lung.diffusion_coefficient}")
        if self.lung.respiratory_rate <= 0:
            raise ValueError(f"lung.respiratory_rate must be positive: {self.lung.respiratory_rate}")
        if not (0 < self.lung.tidal_volume <= 2000):
            raise ValueError(f"lung.tidal_volume_ml out of range: {self.lung.tidal_volume}")

        # 肾脏
        if self.kidney.GFR < 0:
            raise ValueError(f"kidney.GFR must be non-negative: {self.kidney.GFR}")
        if self.kidney.urine_output < 0:
            raise ValueError(f"kidney.urine_output must be non-negative: {self.kidney.urine_output}")
        if self.kidney.renal_blood_flow < 0:
            raise ValueError(f"kidney.renal_blood_flow must be non-negative: {self.kidney.renal_blood_flow}")

        # 血液
        if self.blood.total_volume_ml <= 0:
            raise ValueError(f"blood.total_volume_ml must be positive: {self.blood.total_volume_ml}")

        # Fluid
        if self.fluid.vascular_volume_ml < 0:
            raise ValueError(f"fluid.vascular_volume_ml must be non-negative: {self.fluid.vascular_volume_ml}")
        if self.fluid.isf_volume_ml < 0:
            raise ValueError(f"fluid.isf_volume_ml must be non-negative: {self.fluid.isf_volume_ml}")
        if self.fluid.icf_volume_ml < 0:
            raise ValueError(f"fluid.icf_volume_ml must be non-negative: {self.fluid.icf_volume_ml}")

        # Gut
        if not (0 <= self.gut.gut_motility <= 1.0):
            raise ValueError(f"gut.gut_motility out of range: {self.gut.gut_motility}")
        if not (0 <= self.gut.barrier_integrity <= 1.0):
            raise ValueError(f"gut.barrier_integrity out of range: {self.gut.barrier_integrity}")
        if not (0 <= self.gut.microbiome_activity <= 1.0):
            raise ValueError(f"gut.microbiome_activity out of range: {self.gut.microbiome_activity}")

        # Liver
        if not (0 < self.liver.metabolic_activity <= 1.0):
            raise ValueError(f"liver.metabolic_activity out of range: {self.liver.metabolic_activity}")
        if not (0 <= self.liver.detox_capacity <= 1.0):
            raise ValueError(f"liver.detox_capacity out of range: {self.liver.detox_capacity}")
        if not (0 <= self.liver.cyp450_activity <= 1.0):
            raise ValueError(f"liver.cyp450_activity out of range: {self.liver.cyp450_activity}")
        if not (0 <= self.liver.glycogen_fraction <= 1.0):
            raise ValueError(f"liver.glycogen_fraction out of range: {self.liver.glycogen_fraction}")
        if not (0 <= self.liver.bilirubin_conjugation <= 1.0):
            raise ValueError(f"liver.bilirubin_conjugation out of range: {self.liver.bilirubin_conjugation}")

        # Neuro
        if not (0 <= self.neuro.sympathetic_tone <= 1.0):
            raise ValueError(f"neuro.sympathetic_tone out of range: {self.neuro.sympathetic_tone}")
        if not (0 <= self.neuro.parasympathetic_tone <= 1.0):
            raise ValueError(f"neuro.parasympathetic_tone out of range: {self.neuro.parasympathetic_tone}")
        if not (0 <= self.neuro.consciousness <= 1.0):
            raise ValueError(f"neuro.consciousness out of range: {self.neuro.consciousness}")
        if not (0 <= self.neuro.seizure <= 1.0):
            raise ValueError(f"neuro.seizure out of range: {self.neuro.seizure}")
        if not (0 <= self.neuro.pain_level <= 10.0):
            raise ValueError(f"neuro.pain_level out of range: {self.neuro.pain_level}")

        # Immune
        if not (0 <= self.immune.cytokine_level <= 1.0):
            raise ValueError(f"immune.cytokine_level out of range: {self.immune.cytokine_level}")
        if not (0 <= self.immune.immune_suppression <= 1.0):
            raise ValueError(f"immune.immune_suppression out of range: {self.immune.immune_suppression}")
        if not (0 <= self.immune.coagulation_state <= 1.0):
            raise ValueError(f"immune.coagulation_state out of range: {self.immune.coagulation_state}")

    def apply_factor(self, cmd: FactorCommand) -> None:
        """
        统一因子写入接口 — 所有外部扰动（疾病、药物）的唯一参数修改入口。

        与 VirtualCreature.apply_factor() 完全相同的逻辑，
        但 PhysiologyEngine 专用：只写生理参数，不管游戏逻辑。

        未知 target 或 op 记录警告并静默返回（不抛异常，保留向后兼容）。
        """
        path = PARAM_PATHS.get(cmd.target)
        if path is None:
            logger.warning("PhysiologyEngine.apply_factor: unknown target '%s'", cmd.target)
            return

        module_name, attr_name = path
        module = getattr(self, module_name, None)
        if module is None:
            logger.warning("PhysiologyEngine.apply_factor: module '%s' not found", module_name)
            return

        current = getattr(module, attr_name, None)
        if current is None:
            logger.warning("PhysiologyEngine.apply_factor: attr '%s' not found on %s", attr_name, module_name)
            return

        if cmd.op == "multiply":
            new_value = current * cmd.value
        elif cmd.op == "add":
            new_value = current + cmd.value
        elif cmd.op == "set":
            new_value = cmd.value
        else:
            logger.warning("PhysiologyEngine.apply_factor: unknown op '%s'", cmd.op)
            return

        setattr(module, attr_name, new_value)
        logger.debug(
            "PhysiologyEngine.apply_factor: %s %s %.4f → %.4f",
            cmd.target, cmd.op, current, new_value,
        )

    def _update_venous_gas(self):
        """
        更新静脉血气（由组织代谢决定）。
        简化：组织从动脉血提取 O2，释放 CO2。
        """
        O2_extracted = self.heart.cardiac_output * (
            self.blood.get_arterial_O2_content() -
            self.blood.get_venous_O2_content()) / 100.0

        RQ = self.lung.respiratory_quotient
        CO2_released = O2_extracted * RQ

        self.blood.venous_PO2_mmHg = max(20.0, 40.0 - 0.1 * O2_extracted)
        self.blood.venous_PCO2_mmHg = min(60.0, 46.0 + 0.2 * CO2_released)
        self.blood.venous_saturation = self.lung._oxygen_saturation_curve(
            self.blood.venous_PO2_mmHg)

    def _update_blood_metabolites(self, dt: float):
        """
        更新血液代谢物（由各器官共同影响）。
        """
        basal_glucose_utilization = 0.01 * self.w
        basal_lactate_production = 0.002 * self.w

        CO_factor = self.heart.cardiac_output / base_cardiac_output_ml_min(self.w)
        if CO_factor < 0.8:
            self.blood.lactate_mmol_L += 0.001 * dt * (1.0 / CO_factor - 1.0)
            self.blood.lactate_mmol_L = min(10.0, self.blood.lactate_mmol_L)

        lactate_clearance = 0.005 * self.blood.lactate_mmol_L
        self.blood.lactate_mmol_L = max(0.5, self.blood.lactate_mmol_L - lactate_clearance * dt)

    def compute(self, inputs: PhysiologyInputs) -> dict:
        """
        推进生理仿真一个时间步。

        这是纯函数：给定当前状态和输入，返回新的生理状态。
        无事件调度、无疾病逻辑、无日志记录。

        计算顺序：
        0. validate_parameters
        1. apply_factor (FactorCommand)
        2. toxicology
        3. heart → CO/MAP/CVP
        4. lung → gas exchange
        5. kidney → GFR/urine
        5.5. gut → portal absorption
        5.6. liver → metabolism/detox
        4.7. endocrine → hormone axes
        4.8. neuro → autonomic/CNS/chemoreceptor
        4.9. immune → cytokine/inflammation
        6. organ_health.track
        7. _update_venous_gas
        8. _update_blood_metabolites
        9. urine blood loss
        10. fluid + HH_pH
        11. blood_volume_sync

        Args:
            inputs: PhysiologyInputs，包含 svr_factor 和 factor_commands

        Returns:
            dict，含各器官状态快照和血液状态
        """
        # ── Step 0: 硬失败参数验证（Bioflow 模式）──────────────────────────────
        # 在任何计算之前验证参数范围，无效时立即失败而非静默截断。
        self.validate_parameters()

        dt = self.dt

        # ── Step 1: 应用外部因子（毒理/药剂/疾病）──────────────────────────────
        for cmd in inputs.factor_commands:
            self.apply_factor(cmd)

        # ── Step 2: 毒理学 ─────────────────────────────────────────────────
        tox_state = self.toxicology.compute(dt)
        # svr_factor 来自外部（tox/pharma 合并后的结果）
        svr_factor = inputs.svr_factor
        # Note: contractility_factor 由 FactorCommand 控制，不在这里覆盖。
        # ToxicologyModule 通过 tox_state["svr_factor"] 影响 SVR（通过 svr_factor 传递），
        # 而不是直接修改 contractility_factor（那是药理学/疾病模块的职责）。

        # ── Step 3: 心脏循环 ────────────────────────────────────────────────
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)
        CVP = heart_state["CVP_mmHg"]
        CO = heart_state["cardiac_output_ml_min"]

        # ── Step 4: 肺部气体交换 ────────────────────────────────────────────
        lung_state = self.lung.compute(dt, CO)

        # ── Step 5: 肾脏泌尿 ────────────────────────────────────────────────
        kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], CVP, CO)

        # ── Step 5.5: 肠道吸收 ───────────────────────────────────────────
        gut_state = self.gut.compute(dt, CO)

        # ── Step 5.6: 肝脏代谢 ───────────────────────────────────────────
        liver_state = self.liver.compute(dt, gut_state, CO)

        # ── Step 4.7: 内分泌轴 ───────────────────────────────────────────
        endocrine_state = self.endocrine.compute(dt)

        # ── Step 4.8: 神经系统 ───────────────────────────────────────────
        neuro_state = self.neuro.compute(dt, heart_state, lung_state)
        for cmd in neuro_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # ── Step 4.9: 免疫/炎症系统 ─────────────────────────────────────────
        immune_state = self.immune.compute(dt, endocrine_state)
        for cmd in immune_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # ── Step 6: 器官衰竭追踪 ────────────────────────────────────────────
        self.organ_health.track(dt, heart_state, lung_state, kidney_state)

        # 健康因子永久降低器官输出
        if self.organ_health.heart_factor < 1.0:
            heart_state["cardiac_output_ml_min"] *= self.organ_health.heart_factor
            heart_state["MAP_mmHg"] *= self.organ_health.heart_factor
            self.heart.mean_arterial_pressure *= self.organ_health.heart_factor
            self.heart.cardiac_output *= self.organ_health.heart_factor
        if self.organ_health.lung_factor < 1.0:
            lung_state["arterial_PO2"] *= self.organ_health.lung_factor
            self.lung.diffusion_coefficient *= self.organ_health.lung_factor
        if self.organ_health.kidney_factor < 1.0:
            kidney_state["GFR_ml_min"] *= self.organ_health.kidney_factor
            self.kidney.GFR *= self.organ_health.kidney_factor

        # 从修改后的 dict 读取最终值
        final_MAP = heart_state["MAP_mmHg"]
        final_CO  = heart_state["cardiac_output_ml_min"]

        # ── Step 7: 静脉血气（组织代谢）────────────────────────────────────
        self._update_venous_gas()

        # ── Step 8: 血液代谢物 ──────────────────────────────────────────────
        self._update_blood_metabolites(dt)

        # ── Step 9: 尿量导致的循环血量损失 ─────────────────────────────────
        bv_loss = self.kidney.blood_volume_loss_rate * dt / 60.0
        if bv_loss > 0:
            self.heart.circulating_volume_ml = max(
                0.0, self.heart.circulating_volume_ml - bv_loss)

        # ── Step 10: 三室体液交换 + Henderson-Hasselbalch pH ─────────────
        fluid_state = self.fluid.compute(dt)
        self._hh.hco3 = self.fluid.vascular_hco3_meq_l
        self._hh.pco2 = self.blood.arterial_PCO2_mmHg
        self.blood.arterial_pH = self._hh._compute_ph()

        # ── Step 11: 保守血容量同步 ────────────────────────────────────────
        # HeartModule.circulating_volume_ml 是循环血量的权威来源。
        self.blood.total_volume_ml = self.heart.circulating_volume_ml

        return {
            "heart": heart_state,
            "lung": lung_state,
            "kidney": kidney_state,
            "gut": gut_state,
            "liver": liver_state,
            "endocrine": self.endocrine.summary(),
            "neuro": self.neuro.summary(),
            "immune": self.immune.summary(),
            "blood": self.blood.summary(),
            "toxicology": tox_state,
            "fluid": fluid_state,
        }
