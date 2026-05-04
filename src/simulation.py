"""
Simulation Engine - 多系统耦合仿真引擎
整合心脏、肺部、肾脏模块，实现器官间耦合
"""

import numpy as np
from blood import BloodCompartment
from heart import HeartModule
from lung import LungModule
from kidney import KidneyModule
from toxicology import ToxicologyModule
from organ_health import OrganHealthTracker
from parameters import (
    DT_SECONDS, SIMULATION_STEP_MS, T_MAX_MINUTES,
    PLASMA_VOLUME_FRACTION,
    total_blood_volume_ml, stroke_volume_ml, base_cardiac_output_ml_min,
    tidal_volume_ml, base_minute_ventilation,
    renal_blood_flow_ml_min, gfr_ml_min, baseline_urine_output_ml_min,
)


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

        # 简化：CO2 产生量约为 O2 消耗量的 RQ 倍
        RQ = 0.8
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
        # 在心脏循环之前应用，让药物系数参与 ODE 计算
        pharma_effects: dict = {}
        if hasattr(self, "pharmacology") and self.pharmacology is not None:
            pharma_effects = self.pharmacology.compute(dt, self)
            # 药物效应覆盖 toxicology 的 contractility_factor（治疗优先）
            if "contractility_multiplier" in pharma_effects:
                self.heart.contractility_factor *= pharma_effects["contractility_multiplier"]
            if "svr_multiplier" in pharma_effects:
                svr_factor *= pharma_effects["svr_multiplier"]

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

        # Step 5.5: 疾病模块 — 修改已计算的器官输出
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
            disease_factors = self.disease.compute(dt, engine_state)
            lung_factors = disease_factors.get("lung", {})
            heart_factors = disease_factors.get("heart", {})
            kidney_factors = disease_factors.get("kidney", {})
            # 肺：降低 PaO2（弥散障碍）
            if "diffusion_multiplier" in lung_factors:
                lung_state["arterial_PO2"] *= lung_factors["diffusion_multiplier"]
                lung_state["arterial_saturation"] *= lung_factors["diffusion_multiplier"]
            # 心脏：心率偏移（发热代偿 / DCM 失代偿）
            if "heart_rate_offset" in heart_factors:
                heart_state["heart_rate_bpm"] += heart_factors["heart_rate_offset"]
            # SVR：脓毒性血管扩张
            if "svr_multiplier" in heart_factors and heart_factors["svr_multiplier"] < 1.0:
                heart_state["MAP_mmHg"] *= heart_factors["svr_multiplier"]
            # DCM：收缩力降低（直接调制 contractility_factor）
            if "contractility_multiplier" in heart_factors:
                heart_state["contractility_factor"] *= heart_factors["contractility_multiplier"]
            # DCM：CVP 升高（静脉淤血）
            if "cvp_add" in heart_factors:
                heart_state["CVP_mmHg"] += heart_factors["cvp_add"]
            # DCM：血容量增加（水钠潴留）
            if "blood_volume_add_pct" in heart_factors:
                self.heart.circulating_volume_ml *= (1.0 + heart_factors["blood_volume_add_pct"])
            # 肾脏：GFR 下降（低灌注）+ BUN 累积 + 高钾 + 酸中毒
            if "gfr_multiplier" in kidney_factors:
                self.kidney._disease_gfr_multiplier = kidney_factors["gfr_multiplier"]
            # 注意：BUN 由 kidney.py 自己的 ODE 处理（GFR↓→BUN↑），不需要疾病模块传入
            if "potassium_add" in kidney_factors:
                # 血钾：每步覆盖为目标值（基线 4.2 + ARF 偏移），不累积
                self.blood.potassium_mEq_L = 4.2 + kidney_factors["potassium_add"]
            if "ph_effect" in kidney_factors:
                # pH 效应：覆盖式偏移
                self.blood.arterial_pH = 7.40 + kidney_factors["ph_effect"]

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
