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
    "blood.potassium":            ("blood", "potassium_mEq_L"),
    "blood.pH":                   ("blood", "arterial_pH"),
    "blood.temperature":          ("blood", "core_temperature_C"),
    "blood.BUN":                  ("blood", "bun_mg_dL"),
    "blood.HCO3":                 ("fluid", "vascular_hco3_meq_l"),
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

    def __init__(self, body_weight_kg: float = 20.0):
        self.w = body_weight_kg

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

        # 仿真时间
        self.current_time_s = 0.0
        self.dt = DT_SECONDS                       # 积分步长（秒）

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
            # 体液三室
            "fluid_vascular_ml": [],
            "fluid_isf_ml": [],
            "fluid_icf_ml": [],
            "fluid_nfp_mmHg": [],
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
                glucose = params.get("glucose_grams", 0) * 1000 / self.w  # mg/kg
                self.blood.glucose_mmol_L += glucose / 18.0  # mg/dL → mmol/L
                self.event_log.append(f"[{t:.1f}s] 进食葡萄糖 {glucose:.0f} mg/kg")
            elif event_type == "cocaine":
                dose = params.get("dose_mg_kg", 3.0)
                self.toxicology.administer_cocaine(dose_mg_kg=dose)
                self.event_log.append(f"[{t:.1f}s] 注射可卡因 {dose:.1f} mg/kg")

        # 移除已处理的事件（只保留 event_t > t 的未来事件）
        # 容差 1e-6 处理浮点精度边界（如 300×0.1=29.99999≠30.0）
        self._scheduled_events = [
            (et, evt, p) for (et, evt, p) in self._scheduled_events if et > t + 1e-6
        ]

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

        # 乳酸清除（肝脏 + 肾脏）
        lactate_clearance = 0.005 * self.blood.lactate_mmol_L
        self.blood.lactate_mmol_L = max(0.5, self.blood.lactate_mmol_L - lactate_clearance * dt)

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

        # Step 5: 器官衰竭追踪
        # 根据当前危险条件更新各器官健康状态
        self.organ_health.track(dt, heart_state, lung_state, kidney_state)

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
        # 体液三室
        self.history["fluid_vascular_ml"].append(fluid_state["vascular_ml"])
        self.history["fluid_isf_ml"].append(fluid_state["isf_ml"])
        self.history["fluid_icf_ml"].append(fluid_state["icf_ml"])
        self.history["fluid_nfp_mmHg"].append(fluid_state["nfp_mmHg"])

        # 更新时间
        self.current_time_s += dt

        return {
            "heart": heart_state,
            "lung": lung_state,
            "kidney": kidney_state,
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


# 参数导入已移至文件顶部
