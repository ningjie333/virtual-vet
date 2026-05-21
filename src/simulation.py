"""
Simulation Engine - 多系统耦合仿真引擎
整合心脏、肺部、肾脏模块，实现器官间耦合
"""

import logging
from dataclasses import dataclass
from typing import Literal

import numpy as np
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
from coagulation import CoagulationModule
from lymphatic import LymphaticModule
from lifecycle import LifecycleEngine
from parameters import (
    DT_SECONDS, SIMULATION_STEP_MS, T_MAX_MINUTES,
    PLASMA_VOLUME_FRACTION,
    total_blood_volume_ml, stroke_volume_ml, base_cardiac_output_ml_min,
    tidal_volume_ml, base_minute_ventilation,
    renal_blood_flow_ml_min, gfr_ml_min, baseline_urine_output_ml_min,
)

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
    "blood.sodium_mEq_L":         ("blood", "sodium_mEq_L"),
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
    "gut.microbiome_activity":    ("gut", "microbiome_activity"),
    # Liver
    "liver.metabolic_activity":   ("liver", "metabolic_activity"),
    "liver.detox_capacity":       ("liver", "detox_capacity"),
    "liver.cyp450_activity":      ("liver", "cyp450_activity"),
    "liver.glycogen_fraction":   ("liver", "glycogen_fraction"),
    "liver.bilirubin_conjugation": ("liver", "bilirubin_conjugation"),
    # Endocrine
    "endocrine.T3_factor":          ("endocrine", "T3_factor"),
    "endocrine.T4_factor":          ("endocrine", "T4_ug_dL"),
    "endocrine.metabolic_rate":     ("endocrine", "metabolic_rate"),
    "endocrine.T3_ng_dL":           ("endocrine", "T3_ng_dL"),
    "endocrine.T4_ug_dL":           ("endocrine", "T4_ug_dL"),
    "endocrine.insulin_factor":      ("endocrine", "insulin_factor"),
    "endocrine.glucagon_factor":    ("endocrine", "glucagon_factor"),
    "endocrine.insulin_uU_mL":       ("endocrine", "insulin_uU_mL"),
    "endocrine.glucagon_pg_mL":     ("endocrine", "glucagon_pg_mL"),
    "endocrine.cortisol_factor":     ("endocrine", "cortisol_factor"),
    "endocrine.cortisol_ug_dL":     ("endocrine", "cortisol_ug_dL"),
    "endocrine.HPA_axis":           ("endocrine", "HPA_axis"),
    "endocrine.epinephrine_pg_mL":  ("endocrine", "epinephrine_pg_mL"),
    "endocrine.norepinephrine_pg_mL": ("endocrine", "norepinephrine_pg_mL"),
    "endocrine.PTH_pg_mL":          ("endocrine", "PTH_pg_mL"),
    "endocrine.calcium_mg_dL":       ("endocrine", "calcium_mg_dL"),
    "endocrine.phosphate_mg_dL":    ("endocrine", "phosphate_mg_dL"),
    "endocrine.calcium_factor":     ("endocrine", "calcium_factor"),
    "endocrine.GH_ng_mL":           ("endocrine", "GH_ng_mL"),
    "endocrine.IGF1_nmol_L":        ("endocrine", "IGF1_nmol_L"),
    "endocrine.growth_factor":      ("endocrine", "growth_factor"),
    # Neuro
    "neuro.sympathetic_tone":        ("neuro", "sympathetic_tone"),
    "neuro.parasympathetic_tone":     ("neuro", "parasympathetic_tone"),
    "neuro.consciousness":           ("neuro", "consciousness"),
    "neuro.seizure":                 ("neuro", "seizure"),
    "neuro.pain_level":              ("neuro", "pain_level"),
    "neuro.chemoreceptor_drive":     ("neuro", "chemoreceptor_drive"),
    # Immune
    "immune.cytokine_level":         ("immune", "cytokine_level"),
    "immune.wbc_count":              ("immune", "wbc_count"),
    "immune.crp_level":             ("immune", "crp_level"),
    "immune.acute_phase_response":   ("immune", "acute_phase_response"),
    "immune.immune_suppression":     ("immune", "immune_suppression"),
    "immune.coagulation_state":      ("immune", "coagulation_state"),
    # Coagulation
    "coag.PT_sec":               ("blood", "PT_sec"),
    "coag.aPTT_sec":             ("blood", "aPTT_sec"),
    "coag.fibrinogen_mg_dL":     ("blood", "fibrinogen_mg_dL"),
    "coag.factor_VII":           ("coagulation", "factor_VII"),
    "coag.coagulation_state":    ("coagulation", "coagulation_state"),
    # Lymphatic
    "lymph.splenic_reserve_mL":  ("blood", "splenic_reserve_mL"),
    "blood.splenic_reserve_mL":  ("blood", "splenic_reserve_mL"),  # disease outputs use blood.*
    "lymph.lymph_flow":          ("lymphatic", "lymph_flow_rate"),
    "lymph.interstitial_fluid":  ("blood", "interstitial_fluid_mL"),
}


class VirtualCreature:
    """
    虚拟生物体：整合所有器官模块的耦合仿真

    模块耦合关系：
    ┌──────────────────────────────────────────────┐
    │  Heart → CO → 分配到各器官                    │
    │           ↓                                  │
    │  Lung ← CO（肺循环）← 心输出量                  │
    │   ↓↑                                       │
    │  Blood ←→ Gas exchange ←→ Alveolar gas       │
    │   ↓                                         │
    │  Kidney ← CO（RBF = 20% CO）← 心输出量        │
    │   ↓                                         │
    │  Urine output ←→ Fluid balance              │
    │   ↓                                         │
    │  Blood volume ←→ RAAS feedback              │
    └──────────────────────────────────────────────┘
    """

    def __init__(
        self,
        body_weight_kg: float = 20.0,
        species: str = "canine",
        age_days: float = 0.0,
        dt: float = None,
    ):
        self.w = body_weight_kg
        self.species = species

        # 根据实际体重计算 A 类参数
        _tbv = total_blood_volume_ml(body_weight_kg)
        _sv  = stroke_volume_ml(body_weight_kg)
        _co  = base_cardiac_output_ml_min(body_weight_kg)
        _tv  = tidal_volume_ml(body_weight_kg)
        _mv  = base_minute_ventilation(body_weight_kg)
        _rbf = renal_blood_flow_ml_min(body_weight_kg)
        _gfr = gfr_ml_min(body_weight_kg)
        _urine = baseline_urine_output_ml_min(body_weight_kg)

        # 初始化血液隔室（最先创建，所有器官共享）
        self.blood = BloodCompartment(
            total_volume_ml=_tbv,
            plasma_fraction=PLASMA_VOLUME_FRACTION
        )

        # 初始化器官模块（传入体重缩放后的参数）
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
        self.disease = None  # 疾病模块（由外部 attach_disease() 注入）

        # 三室体液模型
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
        self.coagulation = CoagulationModule(weight_kg=body_weight_kg, blood=self.blood)
        self.lymphatic = LymphaticModule(weight_kg=body_weight_kg, blood=self.blood)

        # 生命周期引擎（驱动生长/衰老/死亡）
        self.lifecycle = LifecycleEngine(species=species, initial_age_days=age_days)

        # 仿真时间
        self.current_time_s = 0.0
        self.dt = DT_SECONDS if dt is None else dt  # dt=None → 0.1s (production); dt=float → override (testing)

        # 事件系统
        self.events = []                            # 待处理事件列表
        self.event_log = []                         # 事件历史

        # 历史记录
        self.history = {
            "time_s": [],
            # 心血管
            "HR_bpm": [],
            "CO_ml_min": [],
            "MAP_mmHg": [],
            "CVP_mmHg": [],
            # 呼吸
            "RR": [],
            "art_PO2": [],
            "art_PCO2": [],
            "saturation": [],
            "pH": [],
            # 肾脏
            "GFR": [],
            "urine_ml_min": [],
            "BUN": [],
            "plasma_Na": [],
            # 代谢
            "glucose": [],
            "blood_volume_ml": [],
            # 毒理
            "contractility_factor": [],
            "svr_factor": [],
            # 衰竭
            "heart_health": [],
            "lung_health": [],
            "kidney_health": [],
            "liver_health": [],
            # 体液三室
            "fluid_vascular_ml": [],
            "fluid_isf_ml": [],
            "fluid_icf_ml": [],
            "fluid_nfp_mmHg": [],
            # 肝脏/肠道
            "liver_metabolic_activity": [],
            "liver_detox_capacity": [],
            "liver_glycogen": [],
            "gut_motility": [],
            "gut_barrier": [],
            "gut_microbiome": [],
            # 内分泌
            "T3_ng_dL": [],
            "insulin_uU_mL": [],
            "cortisol_ug_dL": [],
            "metabolic_rate": [],
            "core_temperature_C": [],
            # 神经
            "neuro_sympathetic": [],
            "neuro_consciousness": [],
            "neuro_seizure": [],
            "neuro_pain": [],
            "neuro_chemodrive": [],
            # 免疫
            "immune_cytokine": [],
            "immune_wbc": [],
            "immune_crp": [],
            "immune_coagulation": [],
            # 凝血
            "coag_PT": [],
            "coag_aPTT": [],
            "coag_fibrinogen": [],
            # 淋巴/脾脏
            "lymph_splenic_reserve": [],
            "lymph_lymph_flow": [],
        }

        # 场景事件
        self._scheduled_events = []  # [(time_s, event_type, params)]

    def schedule_event(self, time_s: float, event_type: str, params: dict):
        """
        注册一个场景事件

        event_type:
        - 'blood_loss': params = {'volume_ml': 200.0}
        - 'fluid_infusion': params = {'volume_ml': 500.0, 'type': 'saline'}
        - 'exercise': params = {'intensity': 0.8, 'duration_s': 300}
        - 'food_intake': params = {'glucose_grams': 50}
        """
        self._scheduled_events.append((time_s, event_type, params))

    def attach_disease(self, disease_module):
        """
        注入疾病模块。

        Args:
            disease_module: DiseaseModule 实例（如 PneumoniaModule）
        """
        self.disease = disease_module
        self.disease.activate(self.current_time_s)

    def apply_factor(self, cmd: FactorCommand) -> None:
        """
        统一因子写入接口 — 所有外部扰动（疾病、药物、事件）的唯一参数修改入口。

        根据 FactorCommand 中的 target 查找 _PARAM_PATHS，对对应模块的属性执行
        multiply / add / set 操作。未知 target 或 op 记录警告并静默返回。

        Args:
            cmd: FactorCommand 指令
        """
        path = _PARAM_PATHS.get(cmd.target)
        if path is None:
            logger.warning("apply_factor: unknown target '%s'", cmd.target)
            return

        module_name, attr_name = path
        module = getattr(self, module_name, None)
        if module is None:
            logger.warning("apply_factor: module '%s' not found", module_name)
            return

        current = getattr(module, attr_name, None)
        if current is None:
            logger.warning("apply_factor: attr '%s' not found on %s", attr_name, module_name)
            return

        if cmd.op == "multiply":
            new_value = current * cmd.value
        elif cmd.op == "add":
            new_value = current + cmd.value
        elif cmd.op == "set":
            new_value = cmd.value
        else:
            logger.warning("apply_factor: unknown op '%s'", cmd.op)
            return

        setattr(module, attr_name, new_value)
        logger.debug(
            "apply_factor: %s %s %.4f → %.4f",
            cmd.target, cmd.op, current, new_value,
        )

    def _process_events(self, t: float):
        """处理到达当前时间的事件"""
        triggered = []
        for i, (event_t, event_type, params) in enumerate(self._scheduled_events):
            if event_t <= t + 1e-6:
                triggered.append((event_type, params))

        for event_type, params in triggered:
            if event_type == "blood_loss":
                vol = params["volume_ml"]
                self.heart.blood_volume_change(-vol)
                self.event_log.append(f"[{t:.1f}s] 失血 {vol:.0f} mL")
            elif event_type == "fluid_infusion":
                vol = params["volume_ml"]
                self.heart.blood_volume_change(vol)
                self.event_log.append(f"[{t:.1f}s] 输液 {vol:.0f} mL")
            elif event_type == "food_intake":
                glucose = params.get("glucose_grams", 0)
                amino_g = params.get("amino_grams", 0)
                fat_g = params.get("fat_grams", 0)
                self.gut.add_food_intake(glucose, amino_g, fat_g)
                self.event_log.append(f"[{t:.1f}s] 进食 葡萄糖{glucose:.0f}g 氨基酸{amino_g:.0f}g 脂肪{fat_g:.0f}g")
            elif event_type == "cocaine":
                dose = params.get("dose_mg_kg", 3.0)
                self.toxicology.administer_cocaine(dose_mg_kg=dose)
                self.event_log.append(f"[{t:.1f}s] 注射可卡因 {dose:.1f} mg/kg")

        # 移除已处理的事件（只保留 event_t > t 的未来事件）
        # 容差 1e-6 处理浮点精度边界（如 300×0.1=29.99999≠30.0）
        self._scheduled_events = [
            (et, evt, p) for (et, evt, p) in self._scheduled_events if et > t + 1e-6
        ]

    def _handle_death(self, cause: str) -> None:
        """生命周期死亡处理：记录原因，终止仿真。"""
        self.death_reason = cause
        logger.info(
            "Creature died: %s at age %.1f days (phase=%s)",
            cause,
            self.lifecycle.state.age_days,
            self.lifecycle.state.phase.value,
        )

    def _update_venous_gas(self):
        """
        更新静脉血气（由组织代谢决定）
        简化：组织从动脉血提取 O2，释放 CO2
        """
        O2_extracted = self.heart.cardiac_output * (
            self.blood.get_arterial_O2_content() -
            self.blood.get_venous_O2_content()) / 100.0

        # CO2 产生量 = O2 消耗量 × 呼吸商（引用肺模块权威值）
        RQ = self.lung.respiratory_quotient
        CO2_released = O2_extracted * RQ

        # 更新静脉血气分压（简化）
        self.blood.venous_PO2_mmHg = max(20.0, 40.0 - 0.1 * O2_extracted)
        self.blood.venous_PCO2_mmHg = min(60.0, 46.0 + 0.2 * CO2_released)
        self.blood.venous_saturation = self.lung._oxygen_saturation_curve(
            self.blood.venous_PO2_mmHg)

    def _update_blood_metabolites(self, dt: float):
        """
        更新血液代谢物（由各器官共同影响）

        血糖：摄入 - 利用 + 糖异生
        乳酸：产生 - 清除
        """
        # 基础代谢消耗
        basal_glucose_utilization = 0.01 * self.w  # mg/kg/min → mmol/L/min
        basal_lactate_production = 0.002 * self.w    # mmol/L/min

        # 心输出量对代谢的影响
        CO_factor = self.heart.cardiac_output / base_cardiac_output_ml_min(self.w)
        if CO_factor < 0.8:
            # 低灌注 → 组织缺氧 → 乳酸产生增加
            self.blood.lactate_mmol_L += 0.001 * dt * (1.0 / CO_factor - 1.0)
            self.blood.lactate_mmol_L = min(10.0, self.blood.lactate_mmol_L)

        # 乳酸清除（肝脏 Cori cycle + 肾脏）
        hepatic_lactate_consumed = self.liver.consume_lactate(dt)  # Cori cycle
        renal_lactate_clearance = 0.002 * self.blood.lactate_mmol_L  # ~30% renal
        lactate_net = hepatic_lactate_consumed + renal_lactate_clearance
        self.blood.lactate_mmol_L = max(
            0.5, self.blood.lactate_mmol_L - lactate_net * dt
        )

    def step(self):
        """
        推进仿真一个时间步

        执行顺序（保证因果关系正确）：
        0. 处理事件（失血、输液、药物注射等）
        1. 毒理学（可卡因等药物效应 → contractility/SVR 因子）
        1.5. 药理学（治疗药物 PK/PD → 修改 contractility/SVR/尿量/血容量）
        2. 心脏循环（血容量 → CO、MAP）
        3. 肺部气体交换（CO → 血气）
        4. 肾脏泌尿（MAP/CO → GFR、尿量）
        5. 器官衰竭追踪 + 器官健康损伤应用
        5.5. 疾病模块（修改器官输出因子）
        6. 更新静脉血气（组织代谢）
        7. 血液代谢物
        7.5. 尿量导致的循环血量损失
        8. 记录历史
        """
        t = self.current_time_s
        dt = self.dt

        # Step 0: 事件处理（必须先于 tox.compute，确保药物注射立即生效）
        self._process_events(t)

        # Step 0.5: 生命周期因子应用（年龄调整后的基线参数）
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors(self)
            death_cause = self.lifecycle.death_check()
            if death_cause:
                self._handle_death(death_cause)
                return

        # Step 1: 毒理学（可卡因等药物效应）
        tox_state = self.toxicology.compute(dt)
        self.heart.contractility_factor = tox_state["contractility_factor"]
        svr_factor = tox_state["svr_factor"]

        # Step 1.5: 药理学（治疗药物 PK/PD 效应）
        # 药物通过 FactorCommand → apply_factor() 统一写入（与疾病模块同路径）
        pharma_effects: dict = {}
        if hasattr(self, "pharmacology") and self.pharmacology is not None:
            # 记录 tox 写入后的 SVR 基准值（pharma 的 multiply 基于此）
            svr_before_pharma = self.heart.SVR
            pharma_commands = self.pharmacology.compute(dt, self)
            for cmd in pharma_commands:
                self.apply_factor(cmd)
            # 同步 pharma 对 SVR 的修改到局部变量：
            # heart.compute() 会覆盖 self.SVR（baroreflex），所以 pharma 的 SVR 效果
            # 必须通过 svr_factor 局部变量传递（与 tox 相同的路径）
            svr_after_pharma = self.heart.SVR
            if svr_after_pharma != svr_before_pharma:
                # pharma 修改了 self.SVR，将变化比例应用到 svr_factor
                svr_factor *= (svr_after_pharma / svr_before_pharma)

        # Step 2: 心脏循环（输入：血容量 → 输出：CO、MAP）
        heart_state = self.heart.compute(dt, svr_factor=svr_factor)
        CVP = heart_state["CVP_mmHg"]
        CO = heart_state["cardiac_output_ml_min"]

        # Step 3: 肺部气体交换（输入：CO → 输出：血气）
        lung_state = self.lung.compute(dt, CO)

        # Step 4: 肾脏泌尿（输入：MAP、CO → 输出：GFR、尿量）
        kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], CVP, CO)

        # Step 4.5: 肠道吸收
        gut_state = self.gut.compute(dt, CO)

        # Step 4.6: 肝脏代谢
        liver_state = self.liver.compute(dt, gut_state, CO)

        # Step 4.7: 内分泌轴
        endocrine_state = self.endocrine.compute(dt)

        # Step 4.65: 凝血系统
        coagulation_state = self.coagulation.compute(dt, liver_state, {})
        for cmd in coagulation_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 4.75: 淋巴/脾脏系统
        lymphatic_state = self.lymphatic.compute(dt, gut_state, {})
        for cmd in lymphatic_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 4.8: 神经系统
        neuro_state = self.neuro.compute(dt, heart_state, lung_state)
        for cmd in neuro_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 4.9: 免疫/炎症系统
        immune_state = self.immune.compute(dt, endocrine_state)
        for cmd in immune_state.get("factor_commands", []):
            self.apply_factor(cmd)

        # Step 5: 器官衰竭追踪
        # 根据当前危险条件更新各器官健康状态
        self.organ_health.track(dt, heart_state, lung_state, kidney_state, liver_state)

        # 健康因子永久降低器官输出（不可逆）
        # 同时修改返回 dict 和模块内部状态，确保损伤有累积效应
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

        # Step 5.5: 疾病模块 — 通过 apply_factor() 统一写入
        if self.disease and self.disease.active:
            self.disease._current_time_s = t
            engine_state = {
                "heart": {
                    "heart_rate_bpm": heart_state["heart_rate_bpm"],
                    "MAP_mmHg": heart_state["MAP_mmHg"],
                    "cardiac_output_ml_min": heart_state["cardiac_output_ml_min"],
                },
                "lung": {"arterial_PO2": lung_state["arterial_PO2"]},
                "kidney": {"GFR_ml_min": kidney_state["GFR_ml_min"]},
            }
            commands = self.disease.compute(dt, engine_state)
            for cmd in commands:
                self.apply_factor(cmd)

            # 重新读取被疾病修改后的器官状态（用于后续器官健康追踪和历史记录）
            heart_state["heart_rate_bpm"] = self.heart.heart_rate
            heart_state["MAP_mmHg"] = self.heart.mean_arterial_pressure
            heart_state["CVP_mmHg"] = self.heart.central_venous_pressure
            heart_state["cardiac_output_ml_min"] = self.heart.cardiac_output
            lung_state["arterial_PO2"] = self.blood.arterial_PO2_mmHg
            kidney_state["GFR_ml_min"] = self.kidney.GFR
            kidney_state["urine_output_ml_min"] = self.kidney.urine_output

        # 从修改后的 dict 读取最终值（而非旧快照）
        final_MAP = heart_state["MAP_mmHg"]
        final_CO  = heart_state["cardiac_output_ml_min"]

        # Step 6: 更新静脉血气（组织代谢）
        self._update_venous_gas()

        # Step 7: 血液代谢物
        self._update_blood_metabolites(dt)

        # Step 7.5: 尿量导致的循环血量损失
        # 肾脏计算 blood_volume_loss_rate，此处应用到心脏血容量
        bv_loss = self.kidney.blood_volume_loss_rate * dt / 60.0  # mL/min × dt(s) / 60
        if bv_loss > 0:
            self.heart.circulating_volume_ml = max(0.0, self.heart.circulating_volume_ml - bv_loss)

        # Step 7.6: 三室体液交换 + Henderson-Hasselbalch pH
        fluid_state = self.fluid.compute(dt)
        # 用 HH 方程更新动脉血 pH（基于当前 HCO₃⁻ 和 PCO₂）
        self._hh.hco3 = self.fluid.vascular_hco3_meq_l
        self._hh.pco2 = self.blood.arterial_PCO2_mmHg
        self.blood.arterial_pH = self._hh._compute_ph()

        # Step 7.7: 保守血容量同步
        # HeartModule.circulating_volume_ml 是循环血量的权威来源。
        # blood.total_volume_ml 会在每步结束时与之一致，
        # 确保血液隔室的血容量始终反映真实的循环血量。
        self.blood.total_volume_ml = self.heart.circulating_volume_ml

        # Step 8: 记录（使用修改后的最终值）
        self.history["time_s"].append(t)
        self.history["HR_bpm"].append(heart_state["heart_rate_bpm"])
        self.history["CO_ml_min"].append(final_CO)
        self.history["MAP_mmHg"].append(final_MAP)
        self.history["CVP_mmHg"].append(CVP)
        self.history["RR"].append(lung_state["respiratory_rate"])
        self.history["art_PO2"].append(lung_state["arterial_PO2"])
        self.history["art_PCO2"].append(lung_state["arterial_PCO2"])
        self.history["saturation"].append(lung_state["arterial_saturation"])
        self.history["pH"].append(self.blood.arterial_pH)
        self.history["GFR"].append(kidney_state["GFR_ml_min"])
        self.history["urine_ml_min"].append(kidney_state["urine_output_ml_min"])
        self.history["BUN"].append(kidney_state["BUN_mg_dL"])
        self.history["plasma_Na"].append(self.blood.sodium_mEq_L)
        self.history["glucose"].append(self.blood.glucose_mmol_L)
        self.history["blood_volume_ml"].append(heart_state["blood_volume_ml"])
        self.history["contractility_factor"].append(heart_state["contractility_factor"])
        self.history["svr_factor"].append(svr_factor)
        self.history["heart_health"].append(self.organ_health.heart_health)
        self.history["lung_health"].append(self.organ_health.lung_health)
        self.history["kidney_health"].append(self.organ_health.kidney_health)
        self.history["liver_health"].append(self.organ_health.liver_health)
        # 体液三室
        self.history["fluid_vascular_ml"].append(fluid_state["vascular_ml"])
        self.history["fluid_isf_ml"].append(fluid_state["isf_ml"])
        self.history["fluid_icf_ml"].append(fluid_state["icf_ml"])
        self.history["fluid_nfp_mmHg"].append(fluid_state["nfp_mmHg"])
        # 肝脏/肠道
        self.history["liver_metabolic_activity"].append(liver_state["metabolic_activity"])
        self.history["liver_detox_capacity"].append(liver_state["detox_capacity"])
        self.history["liver_glycogen"].append(liver_state["glycogen_fraction"])
        self.history["gut_motility"].append(gut_state["gut_motility"])
        self.history["gut_barrier"].append(gut_state["barrier_integrity"])
        self.history["gut_microbiome"].append(gut_state["microbiome_activity"])
        # 内分泌
        self.history["T3_ng_dL"].append(endocrine_state["T3_ng_dL"])
        self.history["insulin_uU_mL"].append(endocrine_state["insulin_uU_mL"])
        self.history["cortisol_ug_dL"].append(endocrine_state["cortisol_ug_dL"])
        self.history["metabolic_rate"].append(endocrine_state["metabolic_rate"])
        self.history["core_temperature_C"].append(self.blood.core_temperature_C)
        # 神经
        self.history["neuro_sympathetic"].append(neuro_state["sympathetic_tone"])
        self.history["neuro_consciousness"].append(neuro_state["consciousness"])
        self.history["neuro_seizure"].append(neuro_state["seizure"])
        self.history["neuro_pain"].append(neuro_state["pain_level"])
        self.history["neuro_chemodrive"].append(neuro_state["chemoreceptor_drive"])
        # 免疫
        self.history["immune_cytokine"].append(immune_state["cytokine_level"])
        self.history["immune_wbc"].append(immune_state["wbc_count"])
        self.history["immune_crp"].append(immune_state["crp_level"])
        self.history["immune_coagulation"].append(immune_state["coagulation_state"])

        # 凝血
        self.history["coag_PT"].append(self.blood.PT_sec)
        self.history["coag_aPTT"].append(self.blood.aPTT_sec)
        self.history["coag_fibrinogen"].append(self.blood.fibrinogen_mg_dL)

        # 淋巴/脾脏
        self.history["lymph_splenic_reserve"].append(self.blood.splenic_reserve_mL)
        self.history["lymph_lymph_flow"].append(self.lymphatic.lymph_flow_rate)

        # 更新时间
        self.current_time_s += dt

        return {
            "heart": heart_state,
            "lung": lung_state,
            "kidney": kidney_state,
            "gut": gut_state,
            "liver": liver_state,
            "endocrine": self.endocrine.summary(),
            "neuro": self.neuro.summary(),
            "immune": self.immune.summary(),
            "coagulation": self.coagulation.summary(),
            "lymphatic": self.lymphatic.summary(),
            "blood": self.blood.summary(),
            "toxicology": tox_state,
            "pharmacology": pharma_effects if (hasattr(self, "pharmacology") and self.pharmacology is not None) else {},
        }

    def simulate(self, duration_minutes: float, verbose: bool = False):
        """
        运行仿真直到指定时长

        Args:
            duration_minutes: 仿真时长（分钟）
            verbose: 是否打印进度
        """
        total_steps = int(duration_minutes * 60.0 / self.dt)

        if verbose:
            print(f"开始仿真：{duration_minutes} min, {total_steps} steps")

        for i in range(total_steps):
            self.step()
            if verbose and i % 1000 == 0:
                t = self.current_time_s
                print(f"  t={t:.1f}s, HR={self.history['HR_bpm'][-1]:.0f}, "
                      f"MAP={self.history['MAP_mmHg'][-1]:.1f}, "
                      f"GFR={self.history['GFR'][-1]:.1f}")

    # ── solve_ivp Radau 引擎（Phase 2: 替换 Euler 求解器）────────────────────────

    def _build_ivp_state_map(self) -> dict[tuple[str, str], int]:
        """建立 (module_name, var_name) → y-array index 映射表。"""
        ivp_state_map: dict[tuple[str, str], int] = {}
        idx = 0
        for module_name in self._get_ivp_disease_modules():
            module = getattr(self, module_name)
            for var_name in module._state_vars:
                ivp_state_map[(module_name, var_name)] = idx
                idx += 1
        return ivp_state_map

    def _get_ivp_disease_modules(self) -> list[str]:
        """返回带有疾病 ODE 状态变量的模块名列表。"""
        # 疾病状态存在 disease 模块里
        modules = []
        if self.disease is not None and hasattr(self.disease, 'compute_derivatives'):
            modules.append('disease')
        return modules

    def _pack_disease_state(self) -> np.ndarray:
        """将当前疾病状态打包成 numpy 向量 y0。"""
        state_map = self._build_ivp_state_map()
        n = len(state_map)
        y0 = np.zeros(n)
        for (mname, vname), idx in state_map.items():
            if mname == 'disease':
                y0[idx] = self.disease._state_vars[vname]
        return y0

    def _unpack_disease_state(self, y: np.ndarray) -> None:
        """将 numpy 向量 y 分解到各疾病模块的 _state_vars。"""
        state_map = self._build_ivp_state_map()
        for (mname, vname), idx in state_map.items():
            if mname == 'disease':
                self.disease._state_vars[vname] = y[idx]

    def _get_engine_state(self) -> dict:
        """收集当前血液/器官状态（供导数计算用）。"""
        return {
            "heart": {
                "heart_rate_bpm": self.heart.heart_rate,
                "MAP_mmHg": self.heart.mean_arterial_pressure,
                "cardiac_output_ml_min": self.heart.cardiac_output,
            },
            "lung": {"arterial_PO2": self.blood.arterial_PO2_mmHg},
            "kidney": {"GFR_ml_min": self.kidney.GFR},
        }

    def _ivp_rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """ODE 右端函数（供 solve_ivp 调用）。"""
        self._unpack_disease_state(y)
        engine_state = self._get_engine_state()
        state_map = self._build_ivp_state_map()
        n = len(state_map)
        dydt = np.zeros(n)

        for (mname, vname), idx in state_map.items():
            if mname == 'disease':
                derivs = self.disease.compute_derivatives(engine_state)
                dydt[idx] = derivs.get(vname, 0.0)

        return dydt

    def run_ivp(self, t_end: float, dt_save: float = 1.0):
        """使用 Radau 隐式求解器跑 ODE 疾病子系统。

        Args:
            t_end: 仿真结束时间（秒）
            dt_save: 采样间隔（秒）

        Returns:
            solve_ivp result object with sol.t, sol.y
        """
        from scipy.integrate import solve_ivp

        y0 = self._pack_disease_state()
        t_eval = np.arange(0.0, t_end + dt_save, dt_save)

        sol = solve_ivp(
            self._ivp_rhs,
            [0.0, t_end],
            y0,
            method='Radau',
            rtol=1e-6,
            atol=1e-9,
            t_eval=t_eval,
            dense_output=True,
            vectorized=False,
        )
        return sol

    def run_scenario(self, scenario_name: str):
        """
        运行预设场景
        """
        scenarios = {
            "normal": self._scenario_normal,
            "blood_loss": self._scenario_blood_loss,
            "fluid_resuscitation": self._scenario_fluid_resuscitation,
            "exercise": self._scenario_exercise,
            "dehydration": self._scenario_dehydration,
            "cocaine": self._scenario_cocaine,
            "cocaine_high": self._scenario_cocaine_high,
        }

        if scenario_name not in scenarios:
            print(f"未知场景：{scenario_name}")
            print(f"可用场景：{list(scenarios.keys())}")
            return

        print(f"\n{'='*60}")
        print(f"  场景：{scenario_name}")
        print(f"{'='*60}")

        # 重置
        self.__init__(body_weight_kg=self.w)
        scenarios[scenario_name]()
        self.simulate(T_MAX_MINUTES, verbose=True)

        print(f"\n事件记录：")
        for event in self.event_log[-5:]:
            print(f"  {event}")

        self.print_summary()

    def _scenario_normal(self):
        """正常稳态"""
        pass

    def _scenario_blood_loss(self):
        """失血 200 mL"""
        self.schedule_event(60.0, "blood_loss", {"volume_ml": 200.0})

    def _scenario_fluid_resuscitation(self):
        """失血后输液复苏"""
        self.schedule_event(60.0, "blood_loss", {"volume_ml": 200.0})
        self.schedule_event(180.0, "fluid_infusion", {"volume_ml": 300.0, "type": "saline"})

    def _scenario_exercise(self):
        """运动应激"""
        self.schedule_event(30.0, "exercise", {"intensity": 0.8, "duration_s": 180})

    def _scenario_dehydration(self):
        """脱水（无饮水 12h）"""
        # 简化：相当于血容量下降 8%
        self.schedule_event(10.0, "blood_loss", {"volume_ml": total_blood_volume_ml(self.w) * 0.05})

    def _scenario_cocaine(self):
        """可卡因中毒（3 mg/kg IV）— 基于 Liu et al. 1993
        直接心脏抑制（短暂）+ 交感外周血管收缩（持续 ≥30 min）
        """
        self.schedule_event(30.0, "cocaine", {"dose_mg_kg": 3.0})

    def _scenario_cocaine_high(self):
        """可卡因高剂量（6 mg/kg IV）— 心脏抑制更明显"""
        self.schedule_event(30.0, "cocaine", {"dose_mg_kg": 6.0})

    def to_minimal_snapshot(self) -> dict:
        """
        Serialize the essential readable engine state for session persistence.

        Omits full history to save space.  Stores only the last value of each
        vital so that an instructor can review a completed session without
        replaying the full simulation.
        """
        h = self.history

        def _last(key: str, fallback):
            vals = h.get(key, [])
            return vals[-1] if vals else fallback

        return {
            # ── Simulation time ──────────────────────────────────────────
            "time_s": self.current_time_s,

            # ── Cardiovascular ───────────────────────────────────────────
            "HR_bpm": round(_last("HR_bpm", self.heart.heart_rate), 1),
            "MAP_mmHg": round(_last("MAP_mmHg", self.heart.mean_arterial_pressure), 1),
            "CO_ml_min": round(_last("CO_ml_min", self.heart.cardiac_output), 1),
            "CVP_mmHg": round(_last("CVP_mmHg", self.heart.central_venous_pressure), 1),
            "blood_volume_ml": round(
                _last("blood_volume_ml", self.heart.circulating_volume_ml), 1
            ),
            "contractility_factor": round(
                _last("contractility_factor", self.heart.contractility_factor), 3
            ),

            # ── Respiratory ─────────────────────────────────────────────
            "RR": round(_last("RR", self.lung.respiratory_rate), 1),
            "art_PO2": round(_last("art_PO2", self.blood.arterial_PO2_mmHg), 1),
            "art_PCO2": round(_last("art_PCO2", self.blood.arterial_PCO2_mmHg), 1),
            "saturation": round(_last("saturation", self.blood.arterial_saturation) * 100, 1),

            # ── Renal ───────────────────────────────────────────────────
            "GFR": round(_last("GFR", self.kidney.GFR), 1),
            "urine_ml_min": round(_last("urine_ml_min", self.kidney.urine_output), 3),
            "BUN": round(_last("BUN", self.blood.bun_mg_dL), 1),

            # ── Metabolic / Blood ──────────────────────────────────────
            "pH": round(_last("pH", self.blood.arterial_pH), 3),
            "glucose_mmol_L": round(_last("glucose", self.blood.glucose_mmol_L), 2),
            "lactate_mmol_L": round(self.blood.lactate_mmol_L, 2),
            "core_temperature_C": round(self.blood.core_temperature_C, 1),

            # ── Fluid compartments ───────────────────────────────────────
            "fluid_vascular_ml": round(
                _last("fluid_vascular_ml", self.fluid.vascular_volume_ml), 1
            ),
            "fluid_isf_ml": round(_last("fluid_isf_ml", self.fluid.isf_volume_ml), 1),
            "fluid_icf_ml": round(_last("fluid_icf_ml", self.fluid.icf_volume_ml), 1),

            # ── Organ health ────────────────────────────────────────────
            "heart_health": round(self.organ_health.heart_health, 3),
            "lung_health": round(self.organ_health.lung_health, 3),
            "kidney_health": round(self.organ_health.kidney_health, 3),

            # ── Lifecycle ───────────────────────────────────────────────
            "lifecycle": self.lifecycle.serialize(),

            # ── Disease state (readable summary) ────────────────────────
            "disease_state": self.disease.summary() if self.disease else None,
        }

    def print_summary(self):
        """打印当前状态摘要"""
        print(f"\n--- 当前状态 (t={self.current_time_s:.1f}s) ---")
        print(f"心血管: HR={self.heart.heart_rate:.0f} bpm, "
              f"CO={self.heart.cardiac_output:.0f} mL/min, "
              f"MAP={self.heart.mean_arterial_pressure:.1f} mmHg")
        print(f"  收缩力={self.heart.contractility_factor:.3f}, "
              f"SVR={self.heart.SVR:.2f} (factor={self.toxicology.svr_factor:.2f})")
        print(f"呼吸: RR={self.lung.respiratory_rate:.0f} /min, "
              f"PaO2={self.blood.arterial_PO2_mmHg:.0f} mmHg, "
              f"PaCO2={self.blood.arterial_PCO2_mmHg:.0f} mmHg")
        print(f"肾脏: GFR={self.kidney.GFR:.1f} mL/min, "
              f"尿量={self.kidney.urine_output:.3f} mL/min, "
              f"BUN={self.blood.bun_mg_dL:.1f} mg/dL")
        print(f"血液: 血糖={self.blood.glucose_mmol_L:.2f} mmol/L, "
              f"血容量={self.heart.circulating_volume_ml:.0f} mL, "
              f"pH={self.blood.arterial_pH:.3f}")
        hh = self.organ_health
        if hh.heart_health < 0.95 or hh.lung_health < 0.95 or hh.kidney_health < 0.95:
            print(f"器官健康: 心={hh.heart_health:.2f}  肺={hh.lung_health:.2f}  肾={hh.kidney_health:.2f}")
        print(f"肝脏: 代谢={self.liver.metabolic_activity:.2f}  解毒={self.liver.detox_capacity:.2f}  糖原={self.liver.glycogen_fraction:.2f}")
        print(f"肠道: 蠕动={self.gut.gut_motility:.2f}  屏障={self.gut.barrier_integrity:.2f}  菌群={self.gut.microbiome_activity:.2f}")


# 参数导入已移至文件顶部
