"""
Simulation Engine - 多系统耦合仿真引擎
整合心脏、肺部、肾脏模块，实现器官间耦合
"""

import logging
from typing import Callable, Optional

import numpy as np

from src.common_types import FactorCommand
from src.engine import CONNECTIONS
from src.engine.factor_pipeline import apply_factor as _apply_factor_impl, snapshot_baselines, clear_baselines
from src.engine.step_contract import (
    StepGuard,
    PHASE_PRE_DISPATCH,
    PHASE_TOX,
    PHASE_PHARMA,
    PHASE_HEART_COMPUTE,
    PHASE_DISEASE,
    PHASE_LUNG_COMPUTE,
    PHASE_KIDNEY_COMPUTE,
    PHASE_GUT_COMPUTE,
    PHASE_IMMUNE,
    PHASE_COUPLING_RESOLVE_1,
    PHASE_ORGAN_HEALTH_TRACK,
    PHASE_ORGAN_HEALTH_APPLY,
    PHASE_HISTORY,
    PHASE_TIME_ADVANCE,
    DIVERGENCE_IMMUNE_ORDER,
    DIVERGENCE_DISEASE_ORDER,
    DIVERGENCE_COUPLING_RESOLVE_COUNT,
    DIVERGENCE_CHEMORECEPTOR_LAG,
    DIVERGENCE_ORGAN_HEALTH_MECHANISM,
)
from src.engine.step_common import (
    run_pre_dispatch,
    run_post_dispatch,
    run_physiology_post,
    run_coupling,
    _apply_urine_blood_loss,
    _apply_fluid_and_ph,
    _sync_blood_volume,
    build_engine_state,
    run_organ_compute_chain,
    refresh_state_dicts,
)
from src.engine.solvers import SolverRegistry
from src.engine.solvers.radau import run_radau_step as _run_radau_step_fn
from src.engine.state_vector import (
    UNIFIED_MODULES,
    build_state_map as _build_state_map_fn,
    pack_state as _pack_state_fn,
    unpack_state as _unpack_state_fn,
    unified_rhs as _unified_rhs_fn,
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
from coagulation import CoagulationModule
from lymphatic import LymphaticModule
from lifecycle import LifecycleEngine, LifecycleMode
from src.organs.coupling import CouplingEngine, OrganContext
from parameters import (
    DT_SECONDS, SIMULATION_STEP_MS, T_MAX_MINUTES,
    PLASMA_VOLUME_FRACTION,
    total_blood_volume_ml, stroke_volume_ml, stroke_volume_ml_feline, stroke_volume_ml_equine,
    base_cardiac_output_ml_min,
    tidal_volume_ml, tidal_volume_ml_feline, tidal_volume_ml_equine, base_minute_ventilation,
    renal_blood_flow_ml_min, gfr_ml_min, baseline_urine_output_ml_min,
    DEFAULT_AGE_DAYS,
    HEART_RATE_REST_BPM, HEART_RATE_REST_BPM_FELINE, HEART_RATE_REST_BPM_EQUINE,
    HEART_RATE_STRESS_BPM, HEART_RATE_STRESS_BPM_FELINE, HEART_RATE_STRESS_BPM_EQUINE,
    HEART_RATE_HARD_MIN, HEART_RATE_HARD_MAX,
    ARTERIAL_PCO2_NORMAL, ARTERIAL_PCO2_NORMAL_FELINE, ARTERIAL_PCO2_NORMAL_EQUINE,
    RESPIRATORY_RATE_REST, RESPIRATORY_RATE_REST_FELINE, RESPIRATORY_RATE_REST_EQUINE,
)

logger = logging.getLogger(__name__)
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
        age_days: float = DEFAULT_AGE_DAYS,
        dt: float = None,
        solver: str = "euler",
        lifecycle_mode: str = "bypass",
        record_history: bool = True,
        legacy_clinical_signs_enabled: bool = False,
    ):
        self.w = body_weight_kg
        self.species = species
        # P1-3: solver plugin injection (SolverRegistry handles name→instance)
        self._solver = SolverRegistry.get(solver)

        # 根据物种选择特异性参数
        if species == "feline":
            _hr_rest = HEART_RATE_REST_BPM_FELINE      # 150 bpm
            _hr_stress = HEART_RATE_STRESS_BPM_FELINE  # 250 bpm
            _pco2_normal = ARTERIAL_PCO2_NORMAL_FELINE # 35 mmHg
        elif species == "equine":
            _hr_rest = HEART_RATE_REST_BPM_EQUINE      # 35 bpm
            _hr_stress = HEART_RATE_STRESS_BPM_EQUINE  # 70 bpm
            _pco2_normal = ARTERIAL_PCO2_NORMAL_EQUINE # 42 mmHg
        else:
            _hr_rest = HEART_RATE_REST_BPM              # 85 bpm
            _hr_stress = HEART_RATE_STRESS_BPM          # 180 bpm
            _pco2_normal = ARTERIAL_PCO2_NORMAL         # 40 mmHg

        # 根据实际体重计算 A 类参数（根据物种选择不同函数）
        _tbv = total_blood_volume_ml(body_weight_kg)
        if species == "feline":
            _sv  = stroke_volume_ml_feline(body_weight_kg)   # 猫：0.55 mL/kg
            _tv  = tidal_volume_ml_feline(body_weight_kg)    # 猫：7.5 mL/kg
            _rr  = RESPIRATORY_RATE_REST_FELINE              # 猫：25 /min
        elif species == "equine":
            _sv  = stroke_volume_ml_equine(body_weight_kg)   # 马：2.0 mL/kg
            _tv  = tidal_volume_ml_equine(body_weight_kg)    # 马：10 mL/kg
            _rr  = RESPIRATORY_RATE_REST_EQUINE              # 马：12 /min
        else:
            _sv  = stroke_volume_ml(body_weight_kg)          # 犬：1.0 mL/kg
            _tv  = tidal_volume_ml(body_weight_kg)           # 犬：12 mL/kg
            _rr  = RESPIRATORY_RATE_REST                     # 犬：18 /min
        _co  = _hr_rest * _sv                                # 心输出量 = HR × SV
        _mv  = _tv * _rr                                     # 分钟通气量 = TV × RR
        _rbf = 0.20 * _co                                    # 肾血流量 = 20% CO
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
            HR_rest=_hr_rest, HR_max=_hr_stress,
        )
        self.lung = LungModule(
            weight_kg=body_weight_kg, blood=self.blood,
            base_RR=_rr, tidal_vol_ml=_tv, base_minute_vent=_mv,
        )
        self.kidney = KidneyModule(
            weight_kg=body_weight_kg, blood=self.blood,
            base_gfr_ml_min=_gfr, base_rbf_ml_min=_rbf,
            base_urine_ml_min=_urine,
        )
        self.toxicology = ToxicologyModule(weight_kg=body_weight_kg)
        self.organ_health = OrganHealthTracker()
        self.diseases: list = []  # 疾病模块列表（支持多病叠加；Q1 + Q2 决策 2026-06-14）

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

        # ── 多器官耦合引擎 ─────────────────────────────────────────────
        # OrganContext: 每个器官模块的信号总线
        self._organ_contexts: dict[str, OrganContext] = {}
        for mod_name in ("heart", "lung", "kidney", "blood", "fluid", "liver"):
            self._organ_contexts[mod_name] = OrganContext(mod_name)
        self.coupling_engine = CouplingEngine()

        # ── 统一 ODE 求解器缓存（半隐式耦合）────────────────────────────
        # _cached_inputs[module_name][input_name] = value
        # 在 rhs(t,y) 调用时，用上一 rhs 调用的 outputs 填充 inputs
        self._cached_inputs: dict[str, dict[str, float]] = {}
        self._current_outputs: dict[str, dict[str, float]] = {}

        # ── 连续失血模型（A3：替代 schedule_event 用于 Radau）──────────
        # sigmoid 失血：dV/dt = -k * sigmoid((t-t_onset)/width)
        # k = blood_loss_total / duration  (mL/s)
        # 累积失血量通过 Radau 积分（每次 rhs 调用应用微小损失）
        self._blood_loss_config: dict[str, float] | None = None
        self._cumulative_blood_loss_ml: float = 0.0  # 累积失血量（每次 rhs 调用累加）

        # ── 生命周期引擎（驱动生长/衰老/死亡）──────────────────────────
        self.lifecycle = LifecycleEngine(
            species=species,
            initial_age_days=age_days,
            mode=LifecycleMode(lifecycle_mode),
        )
        # 捕获基准值（必须在 step() 之前调用）
        self.lifecycle.capture_baselines(self)

        # 仿真时间
        self.current_time_s = 0.0
        self.dt = DT_SECONDS if dt is None else dt  # dt=None → 0.1s (production); dt=float → override (testing)
        self._record_history_enabled = record_history
        self._legacy_clinical_signs_enabled = legacy_clinical_signs_enabled

        # 事件系统
        self.events = []                            # 待处理事件列表
        self.event_log = []                         # 事件历史

        # 求解器诊断（Step 0a: 让 twin-run harness 能检测 Radau fallback）
        self._solver_fallback_count = 0             # Radau 失败退化到 Euler 的次数
        self._solver_last_method_used = "primary"   # "primary" | "euler_fallback"

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

    def set_blood_loss_scenario(self, t_onset: float, total_ml: float, duration: float = 300.0, width: float = 5.0):
        """
        设置连续 ODE 失血场景（替代 schedule_event，用于 Radau/Euler 仿真）。

        失血模型：dV/dt = -k * sigmoid_on(t) * (1 - sigmoid_off(t))
                  bell curve 面积 = k * 3 * width
                  → k = total_ml / (3 * width)

        Args:
            t_onset:   失血开始时间（s）
            total_ml:  总失血量（mL）
            duration:  失血持续时间窗口（参考值，默认 300s）
            width:     sigmoid 上升沿/下降沿宽度（s），默认 5s
        """
        k = total_ml / (3.0 * width)
        self._blood_loss_config = {
            "t_onset": t_onset,
            "total_ml": total_ml,
            "duration": duration,
            "width": width,
            "k": k,
        }

    @property
    def disease(self):
        """向后兼容：返回第一个疾病（多数单病测试/调用点仍按 `engine.disease` 写）。

        多病场景请直接用 `self.diseases` (list)。Q1 (2026-06-14)。
        """
        return self.diseases[0] if self.diseases else None

    def attach_disease(self, disease_module):
        """
        注入疾病模块（支持多病叠加）。

        每次调用追加到 `self.diseases` 列表。所有 active 疾病的 FactorCommand
        在每步按 attach 顺序**chained-rebase** 合并（参见 Q2 决策 2026-06-14）：
        - `multiply` 链 = 复合效应（DCM 0.7 × 肺炎 0.8 = 0.56）
        - `add` 链 = 累加（+5 + +10 = +15）
        - `set` 链 = 后写者赢（最近 attach 的疾病语义最相关）

        Args:
            disease_module: DiseaseModule 实例（如 PneumoniaModule）
        """
        self.diseases.append(disease_module)
        disease_module.activate(self.current_time_s)
        if self._legacy_clinical_signs_enabled:
            self._ensure_legacy_clinical_signs_engine()

    def detach_disease(self, disease_module) -> bool:
        """R5 Stage 2: 从引擎移除疾病模块（仅在 RESOLVED/DEAD 状态可移除）。

        之前没有 detach 机制 — 治愈的疾病对象永远留在 self.diseases 列表中，
        导致列表单调增长。现在允许在疾病进入终态（RESOLVED/DEAD）后移除。

        Args:
            disease_module: 要移除的 DiseaseModule 实例

        Returns:
            True 若移除成功，False 若疾病未在列表中或仍处于 ACTIVE 状态
        """
        from src.diseases import DiseaseState
        if disease_module not in self.diseases:
            return False
        if disease_module.state == DiseaseState.ACTIVE:
            return False  # 必须先 deactivate() 或 mark_dead()
        self.diseases.remove(disease_module)
        logger.info("Disease detached from engine: %s", disease_module.name)
        return True

    def restore_diseases(self, disease_state_full: list[dict]) -> None:
        """R5 Stage 4: 从持久化快照恢复疾病状态。

        重新创建疾病实例并恢复其完整状态（severity、state、_state_vars、activated_at_s）。
        之前没有恢复机制 — 跨 session 疾病进度丢失。

        Args:
            disease_state_full: to_persistence_snapshot()["disease_state_full"] 列表，
                每项是 disease.full_state() 的输出
        """
        from src.diseases import create_disease
        self.diseases.clear()
        for ds in disease_state_full:
            name = ds.get("name")
            severity = ds.get("severity", "moderate")
            try:
                d = create_disease(name, severity=severity)
            except KeyError:
                logger.warning("Cannot restore disease '%s' — not registered", name)
                continue
            d.restore_state(ds)
            self.diseases.append(d)
            if self._legacy_clinical_signs_enabled and d.active:
                self._ensure_legacy_clinical_signs_engine()
            logger.info("Disease restored: %s (state=%s)", name, d.state.value)

    def _ensure_legacy_clinical_signs_engine(self):
        """R6: legacy seam deprecated. Interpretation objects must be created
        by the outer composition layer via `build_external_interpretation_bundle`
        (game/runtime_composition.py). This method is now a no-op stub kept
        only to avoid breaking old callers that still set
        `legacy_clinical_signs_enabled=True`; the engine no longer constructs
        ClinicalSignsEngine internally.
        """
        return None

    def _refresh_legacy_clinical_signs(self) -> None:
        """R6: legacy seam deprecated. Refresh of interpretation state must
        be driven by the outer GameRuntime (`runtime.refresher.refresh(engine)`).
        This method is now a no-op stub kept only for backward compatibility.
        """
        return

    def apply_factor(self, cmd: FactorCommand) -> None:
        """
        统一因子写入接口 — 所有外部扰动（疾病、药物、事件）的唯一参数修改入口。

        根据 FactorCommand 中的 target 查找 _PARAM_PATHS，对对应模块的属性执行
        multiply / add / set 操作。未知 target 或 op 记录警告并静默返回。

        Phase 4 refactor: thin wrapper delegating to
        `src.engine.factor_pipeline.apply_factor`. Logic is unchanged.

        Args:
            cmd: FactorCommand 指令
        """
        _apply_factor_impl(cmd, self)

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

        # 更新静脉血气分压 (Phase 2 #7: 简化 Hb 校正占位)
        # REF: Siggaard-Andersen 1971 — Hb 浓度影响 O2 含量
        # 完整公式: PvO2 = 40 - 0.05 * O2_extracted * (12 / max(Hb, 6))
        # 暂用原公式 (当前模型无 Hb 字段, 留扩展点)
        hb_correction = 1.0  # 正常 12 g/dL 时为 1.0
        self.blood.venous_PO2_mmHg = max(20.0, 40.0 - 0.05 * O2_extracted * hb_correction)
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
        推进仿真一个时间步。

        Delegates to the injected SolverPlugin (self._solver).
        Default: EulerSolver (explicit, O(dt)).
        Activate Radau: solver='radau' or RADAU_ENABLED=1.
        """
        return self._solver.step(self)

    def _step_euler(self):
        """
        Euler 求解器路径 — 推进仿真一个时间步

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

        R3: StepGuard enforces ordering contracts at runtime.
        Documented divergences from Radau path are recorded via
        guard.divergence_ok() so they are explicit and auditable.
        """
        t = self.current_time_s
        dt = self.dt

        # R3: create per-step guard. Enabled by default; tests can
        # construct a disabled guard via StepGuard(enabled=False).
        guard = StepGuard(label="euler")
        # Document intentional divergences from Radau path (not violations).
        guard.divergence_ok(
            DIVERGENCE_IMMUNE_ORDER,
            "Euler: immune.compute() runs BEFORE coupling (Step 4.9). "
            "Radau: runs AFTER coupling (Step 7b). Euler needs immune's "
            "factor_commands applied before coupling sees them."
        )
        guard.divergence_ok(
            DIVERGENCE_DISEASE_ORDER,
            "Euler: disease runs BEFORE organ compute (Step 2.5). "
            "Radau: disease runs AFTER coupling (Step 7). Euler needs "
            "disease factors in place before organ compute() reads them."
        )
        guard.divergence_ok(
            DIVERGENCE_COUPLING_RESOLVE_COUNT,
            "Euler: 2-substep Gauss-Seidel relaxation — substep 1 at Step 4.95 "
            "(PHASE_COUPLING_RESOLVE_1, reads lagged signals) + substep 2 at "
            "Step 8 (PHASE_COUPLING_RESOLVE_2, reads fresh signals). "
            "Radau: intra-step Newton iteration on _cached_inputs (no explicit "
            "substeps). Twin-run tests proved the 2-substep relaxation is "
            "required for Euler stability."
        )
        guard.divergence_ok(
            DIVERGENCE_CHEMORECEPTOR_LAG,
            "Euler: chemoreceptor_drive read from previous step's "
            "neuro.compute() (Gauss-Seidel 1-step lag, O(dt) error). "
            "Radau: neuro integrated in solve_ivp, no lag."
        )
        guard.divergence_ok(
            DIVERGENCE_ORGAN_HEALTH_MECHANISM,
            "Euler: organ_health factor applied via direct setattr "
            "(self.heart.MAP *= factor). Radau: via apply_factor "
            "'multiply'. Euler bypasses baseline since factor is "
            "applied once per step to current value."
        )

        # Step 0-0.5: 事件处理 + 连续失血 + lifecycle（shared with Radau）
        if run_pre_dispatch(self, guard=guard):
            return

        # Step 1: 毒理学（可卡因等药物效应）
        tox_state = self.toxicology.compute(dt)
        self.apply_factor(FactorCommand("heart.contractility_factor", "set", tox_state["contractility_factor"]))
        svr_factor = tox_state["svr_factor"]
        guard.mark(PHASE_TOX)

        # Step 1.1: 在毒理学之后重新应用生命周期因子
        # 毒理学会覆盖 contractility_factor，需要将生命周期因子乘回去
        if not self.lifecycle.is_dead():
            self.lifecycle.apply_age_factors_post_tox(self)

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
            guard.mark(PHASE_PHARMA)

        # Step 2: 心脏循环（输入：血容量 → 输出：CO、MAP）
        # chemoreceptor_drive 来自上一时间步的 neuro 状态（Gauss-Seidel 一阶滞后，
        # 产生 O(dt) 误差，随 dt 细化收敛，不产生 O(1) 偏差）
        neuro_chemo = self.neuro.chemoreceptor_drive if hasattr(self, "neuro") else 0.0
        heart_state = self.heart.compute(dt, svr_factor=svr_factor,
                                         chemoreceptor_drive=neuro_chemo)
        CVP = heart_state["CVP_mmHg"]
        CO = heart_state["cardiac_output_ml_min"]
        guard.mark(PHASE_HEART_COMPUTE)

        # Step 2.5: 疾病模块 — 在器官 compute() 之前执行一次
        # 这样 diffusion_coefficient / GFR multiplier 等本轮即可影响下游器官，
        # 同时避免同一 dt 内重复推进 disease state。
        # Q1 (2026-06-14)：支持多病叠加——所有 active 疾病按 attach 顺序计算
        # 各自的 FactorCommand，统一走 apply_factor 的 chained-rebase 合并。
        # P0.2: snapshot baselines before diseases so multiply/add ops are
        # idempotent across steps (relative to post-heart baseline).
        snapshot_baselines(self, guard=guard)
        if self.diseases:
            active_diseases = [d for d in self.diseases if d.active]
            if active_diseases:
                engine_state = build_engine_state(self)
                for d in active_diseases:
                    d._current_time_s = self.current_time_s
                    for cmd in d.compute(dt, engine_state):
                        self.apply_factor(cmd)

            # 生理 clamp：防止疾病累积效应把参数推到非生理范围
            # P0(2026-06-13): 通过 apply_factor 写入，保持 FactorCommand 审计链完整性
            hr_clamped = max(HEART_RATE_HARD_MIN, min(HEART_RATE_HARD_MAX, self.heart.heart_rate))
            self.apply_factor(FactorCommand("heart.heart_rate", "set", hr_clamped))
            map_clamped = max(30.0, min(200.0, self.heart.mean_arterial_pressure))
            self.apply_factor(FactorCommand("heart.MAP", "set", map_clamped))
            guard.mark(PHASE_DISEASE)

        # Step 3: 肺部气体交换（输入：CO → 输出：血气）
        lung_state = self.lung.compute(dt, CO)
        guard.mark(PHASE_LUNG_COMPUTE)

        # Step 4: 肾脏泌尿（输入：MAP、CO → 输出：GFR、尿量）
        kidney_state = self.kidney.compute(dt, heart_state["MAP_mmHg"], CVP, CO)
        guard.mark(PHASE_KIDNEY_COMPUTE)

        # Step 4.5: 肠道吸收
        gut_state = self.gut.compute(dt, CO)
        guard.mark(PHASE_GUT_COMPUTE)

        # Step 4.6-4.8: organ compute chain (liver→endocrine→coagulation→lymphatic→neuro)
        # P1.2: unified with Radau path via run_organ_compute_chain
        organ_states = run_organ_compute_chain(
            self, dt, gut_state, heart_state, lung_state, guard=guard
        )
        liver_state = organ_states["liver"]
        endocrine_state = organ_states["endocrine"]
        neuro_state = organ_states["neuro"]

        # Step 4.9: 免疫/炎症系统（Euler 特有：在 coupling 之前执行）
        immune_state = self.immune.compute(dt, endocrine_state)
        for cmd in immune_state.get("factor_commands", []):
            self.apply_factor(cmd)
        guard.mark(PHASE_IMMUNE)

        # ── Step 4.95: coupling substep 1 (lagged resolve) ────────────────────
        # R4: This is the FIRST substep of the Euler path's 2-substep Gauss-Seidel
        # relaxation. It reads the PREVIOUS step's published signals (lagged by
        # one step) from `_organ_contexts` and resolves coupling rules against
        # them. The SECOND substep runs in `run_coupling` (Step 8, via
        # `run_post_dispatch`) and publishes FRESH signals before resolving.
        #
        # This is NOT a bug to remove casually — twin-run harness
        # (tests/test_twin_run.py) empirically proved that the 2-substep
        # relaxation is required for Euler stability (removing this substep
        # flips blood_loss_severe from PASS to FAIL, GFR error 0.066 → 0.142).
        # See docs/coupling_inventory.md "double-resolve" and the
        # DIVERGENCE_COUPLING_RESOLVE_COUNT contract marker below.
        #
        # P0.2: re-snapshot baselines after all organ compute() calls so
        # coupling multiply/add ops use post-organ values as baseline.
        snapshot_baselines(self, guard=guard)
        coupling_cmds = self.coupling_engine.resolve(self._organ_contexts, dt)
        for cmd in coupling_cmds:
            self.apply_factor(cmd)
        guard.mark(PHASE_COUPLING_RESOLVE_1)

        # Step 5.1: 器官衰竭追踪
        # 保存 pre-degradation 值用于 stress 判断，避免 feedback 振荡
        heart_state_pre = {
            "MAP_mmHg": heart_state["MAP_mmHg"],
            "heart_rate_bpm": heart_state["heart_rate_bpm"],
        }
        lung_state_pre = dict(lung_state)

        # 器官健康因子应用前的心肺原始状态（用于 stress 检测）
        # 在 Step 5 疾病模块之后捕获，疾病效应已体现在 state 中
        self.organ_health.track(
            dt, heart_state, lung_state, kidney_state, liver_state,
            heart_state_pre=heart_state_pre,
            lung_state_pre=lung_state_pre,
        )
        guard.mark(PHASE_ORGAN_HEALTH_TRACK)

        # 健康因子永久降低器官输出（不可逆）
        # NOTE(C6): 一次性应用（不是乘法链）。organ_health.factor 由 track() 根据
        # 当前 stress 计算，每 step 独立。不会产生 base×0.95×0.90 的累积效应。
        # R1: 只修改实例属性 — dict 由 refresh_state_dicts 统一刷新
        if self.organ_health.heart_factor < 1.0:
            self.heart.mean_arterial_pressure *= self.organ_health.heart_factor
            self.heart.cardiac_output *= self.organ_health.heart_factor
        if self.organ_health.lung_factor < 1.0:
            self.lung.diffusion_coefficient *= self.organ_health.lung_factor
        if self.organ_health.kidney_factor < 1.0:
            self.kidney.GFR *= self.organ_health.kidney_factor
        guard.mark(PHASE_ORGAN_HEALTH_APPLY)

        # R1: 无条件从实例属性刷新 state dicts（替代 Step 5.5 条件同步）
        # 实例属性是单一权威源 — dict 是快照，在 disease/organ_health/coupling
        # 修改实例属性后必须刷新以保持一致。
        refresh_state_dicts(self, heart_state, lung_state, kidney_state, guard=guard)

        # Step 6: 更新静脉血气（组织代谢）
        self._update_venous_gas()

        # Step 7: 血液代谢物
        self._update_blood_metabolites(dt)

        # Steps 7.5-8.5: shared post-dispatch (blood loss + fluid + coupling + legacy refresh)
        # signal_time = t (before +=dt) — Euler publishes at pre-step time
        fluid_state = run_post_dispatch(self, dt, signal_time=t, guard=guard)

        # Post-coupling safety clamp: RAAS coupling rule multiplies heart.SVR
        # every step (factor = 1 + 0.2 * renin). Over many steps this compounds
        # even with baroreceptor_feedback trying to reduce SVR. Clamp to a
        # physiological maximum to prevent SVR runaway. (Pre-existing issue,
        # surfaced by decompensation spiral testing, 2026-06-15.)
        svr_phys_max = self.heart.SVR_baseline * 4.0  # 4× baseline ≈ 5.6 PRU
        self.heart.SVR = min(self.heart.SVR, svr_phys_max)

        # Step 8: history recording (shared with Radau via _record_history)
        # P0 0b: was inline divergence with Radau; now single source of truth
        if self._record_history_enabled:
            self._record_history(
                dt, t=t,
                heart_state=heart_state, lung_state=lung_state,
                kidney_state=kidney_state, gut_state=gut_state,
                liver_state=liver_state, endocrine_state=endocrine_state,
                neuro_state=neuro_state, immune_state=immune_state,
                fluid_state=fluid_state, svr_factor=svr_factor,
            )
        guard.mark(PHASE_HISTORY)

        # 更新时间
        self.current_time_s += dt
        guard.mark(PHASE_TIME_ADVANCE)

        # P0.2: clear per-step baselines to prevent stale state leaking
        # into tests that don't call step().
        clear_baselines(guard=guard)

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

    def _step_radau(self):
        """
        Radau 隐式求解器路径 — 单步推进。

        Step 3 (solver-refactor-roadmap-v3): implementation extracted verbatim to
        src/engine/solvers/radau.run_radau_step. This is a thin forwarder for
        backward compatibility (RadauSolver.step + experiments/tools call
        engine._step_radau). Full data-flow docstring lives in the new module.
        """
        return _run_radau_step_fn(self)

    def _record_history(self, dt: float, t: float = None,
                        heart_state: dict = None, lung_state: dict = None,
                        kidney_state: dict = None, gut_state: dict = None,
                        liver_state: dict = None, endocrine_state: dict = None,
                        neuro_state: dict = None, immune_state: dict = None,
                        fluid_state: dict = None, svr_factor: float = 1.0):
        """
        Record current engine state to history dict.

        Single source of truth for history schema (P0 0b fix: was divergent
        between Euler inline and Radau _record_history; now both call this).

        Args:
            dt: timestep
            t: timestamp (defaults to self.current_time_s)
            *_state: per-organ state dicts from this step's compute() calls.
                     If None, falls back to reading self.module.X directly
                     (used by Radau which doesn't pass per-step dicts).
        """
        t = t if t is not None else self.current_time_s

        # Cardio
        self.history["time_s"].append(t)
        self.history["HR_bpm"].append(
            heart_state["heart_rate_bpm"] if heart_state else self.heart.heart_rate)
        self.history["CO_ml_min"].append(
            heart_state["cardiac_output_ml_min"] if heart_state else self.heart.cardiac_output)
        self.history["MAP_mmHg"].append(
            heart_state["MAP_mmHg"] if heart_state else self.heart.mean_arterial_pressure)
        self.history["CVP_mmHg"].append(
            heart_state["CVP_mmHg"] if heart_state else self.heart.central_venous_pressure)

        # Respiratory
        self.history["RR"].append(
            lung_state["respiratory_rate"] if lung_state else self.lung.respiratory_rate)
        self.history["art_PO2"].append(
            lung_state["arterial_PO2"] if lung_state else self.blood.arterial_PO2_mmHg)
        self.history["art_PCO2"].append(
            lung_state["arterial_PCO2"] if lung_state else self.blood.arterial_PCO2_mmHg)
        self.history["saturation"].append(
            lung_state["arterial_saturation"] if lung_state else self.blood.arterial_saturation)
        self.history["pH"].append(self.blood.arterial_pH)

        # Renal
        self.history["GFR"].append(
            kidney_state["GFR_ml_min"] if kidney_state else self.kidney.GFR)
        self.history["urine_ml_min"].append(
            kidney_state["urine_output_ml_min"] if kidney_state else self.kidney.urine_output)
        self.history["BUN"].append(
            kidney_state["BUN_mg_dL"] if kidney_state else self.blood.bun_mg_dL)
        self.history["plasma_Na"].append(self.blood.sodium_mEq_L)

        # Metabolic
        self.history["glucose"].append(self.blood.glucose_mmol_L)
        self.history["blood_volume_ml"].append(
            heart_state["blood_volume_ml"] if heart_state else self.heart.circulating_volume_ml)
        self.history["contractility_factor"].append(
            heart_state["contractility_factor"] if heart_state else self.heart.contractility_factor)
        self.history["svr_factor"].append(svr_factor)

        # Organ health
        self.history["heart_health"].append(self.organ_health.heart_health)
        self.history["lung_health"].append(self.organ_health.lung_health)
        self.history["kidney_health"].append(self.organ_health.kidney_health)
        self.history["liver_health"].append(self.organ_health.liver_health)

        # Fluid compartments
        if fluid_state:
            self.history["fluid_vascular_ml"].append(fluid_state["vascular_ml"])
            self.history["fluid_isf_ml"].append(fluid_state["isf_ml"])
            self.history["fluid_icf_ml"].append(fluid_state["icf_ml"])
            self.history["fluid_nfp_mmHg"].append(fluid_state["nfp_mmHg"])
        else:
            self.history["fluid_vascular_ml"].append(self.fluid.vascular_volume_ml)
            self.history["fluid_isf_ml"].append(self.fluid.isf_volume_ml)
            self.history["fluid_icf_ml"].append(self.fluid.icf_volume_ml)
            self.history["fluid_nfp_mmHg"].append(0.0)  # not stored on FluidCompartment

        # Liver / Gut
        self.history["liver_metabolic_activity"].append(
            liver_state["metabolic_activity"] if liver_state else self.liver.metabolic_activity)
        self.history["liver_detox_capacity"].append(
            liver_state["detox_capacity"] if liver_state else self.liver.detox_capacity)
        self.history["liver_glycogen"].append(
            liver_state["glycogen_fraction"] if liver_state else self.liver.glycogen_fraction)
        self.history["gut_motility"].append(
            gut_state["gut_motility"] if gut_state else self.gut.gut_motility)
        self.history["gut_barrier"].append(
            gut_state["barrier_integrity"] if gut_state else self.gut.barrier_integrity)
        self.history["gut_microbiome"].append(
            gut_state["microbiome_activity"] if gut_state else self.gut.microbiome_activity)

        # Endocrine
        if endocrine_state:
            self.history["T3_ng_dL"].append(endocrine_state["T3_ng_dL"])
            self.history["insulin_uU_mL"].append(endocrine_state["insulin_uU_mL"])
            self.history["cortisol_ug_dL"].append(endocrine_state["cortisol_ug_dL"])
            self.history["metabolic_rate"].append(endocrine_state["metabolic_rate"])
        else:
            endo = self.endocrine.summary()
            self.history["T3_ng_dL"].append(endo.get("T3_ng_dL", 0.0))
            self.history["insulin_uU_mL"].append(endo.get("insulin_uU_mL", 0.0))
            self.history["cortisol_ug_dL"].append(endo.get("cortisol_ug_dL", 0.0))
            self.history["metabolic_rate"].append(endo.get("metabolic_rate", 0.0))

        # Core temperature (single canonical key: core_temperature_C)
        self.history["core_temperature_C"].append(self.blood.core_temperature_C)

        # Neuro (NO bare 'sympathetic' key — was colliding with neuro_sympathetic in old Radau path)
        if neuro_state:
            self.history["neuro_sympathetic"].append(neuro_state["sympathetic_tone"])
            self.history["neuro_consciousness"].append(neuro_state["consciousness"])
            self.history["neuro_seizure"].append(neuro_state["seizure"])
            self.history["neuro_pain"].append(neuro_state["pain_level"])
            self.history["neuro_chemodrive"].append(neuro_state["chemoreceptor_drive"])
        else:
            neuro = self.neuro.summary()
            self.history["neuro_sympathetic"].append(neuro.get("sympathetic_tone", 0.0))
            self.history["neuro_consciousness"].append(neuro.get("consciousness", 0.0))
            self.history["neuro_seizure"].append(neuro.get("seizure", 0.0))
            self.history["neuro_pain"].append(neuro.get("pain_level", 0.0))
            self.history["neuro_chemodrive"].append(neuro.get("chemoreceptor_drive", 0.0))

        # Immune
        if immune_state:
            self.history["immune_cytokine"].append(immune_state["cytokine_level"])
            self.history["immune_wbc"].append(immune_state["wbc_count"])
            self.history["immune_crp"].append(immune_state["crp_level"])
            self.history["immune_coagulation"].append(immune_state["coagulation_state"])
        else:
            imm = self.immune.summary()
            self.history["immune_cytokine"].append(imm.get("cytokine_level", 0.0))
            self.history["immune_wbc"].append(imm.get("wbc_count", 0.0))
            self.history["immune_crp"].append(imm.get("crp_level", 0.0))
            self.history["immune_coagulation"].append(imm.get("coagulation_state", 0.0))

        # Coagulation
        self.history["coag_PT"].append(self.blood.PT_sec)
        self.history["coag_aPTT"].append(self.blood.aPTT_sec)
        self.history["coag_fibrinogen"].append(self.blood.fibrinogen_mg_dL)

        # Lymphatic / splenic
        self.history["lymph_splenic_reserve"].append(self.blood.splenic_reserve_mL)
        self.history["lymph_lymph_flow"].append(self.lymphatic.lymph_flow_rate)

        # NOTE: time advancement is handled by the caller (_step_euler or _step_radau),
        # not here. This avoids double-advancement when Euler calls _record_history
        # and then also increments current_time_s.

    def advance_seconds(self, duration_seconds: float, verbose: bool = False,
                        progress_callback: Optional[Callable[[int, int], None]] = None):
        """
        运行仿真直到指定物理时长。

        Args:
            duration_seconds: 仿真时长（秒）
            verbose: 是否打印进度
            progress_callback: 可选进度回调 (current_step, total_steps)，每 100 步触发
        """
        total_steps = int(duration_seconds / self.dt)

        if verbose:
            logger.info("开始仿真：%.1f s, %s steps", duration_seconds, total_steps)

        for i in range(total_steps):
            self.step()
            if progress_callback is not None and i % 100 == 0:
                progress_callback(i + 1, total_steps)
            if verbose and i % 1000 == 0:
                t = self.current_time_s
                if self._record_history_enabled and self.history["HR_bpm"]:
                    hr = self.history["HR_bpm"][-1]
                    map_val = self.history["MAP_mmHg"][-1]
                    gfr = self.history["GFR"][-1]
                else:
                    hr = self.heart.heart_rate
                    map_val = self.heart.mean_arterial_pressure
                    gfr = self.kidney.GFR
                logger.info("  t=%.1fs, HR=%s, MAP=%s, GFR=%s", t, hr, map_val, gfr)

    def simulate(self, duration_minutes: float, verbose: bool = False):
        """
        兼容旧接口：按分钟推进仿真。

        Args:
            duration_minutes: 仿真时长（分钟）
            verbose: 是否打印进度
        """
        self.advance_seconds(duration_minutes * 60.0, verbose=verbose)

    # ── solve_ivp Radau 引擎（Phase 2: 替换 Euler 求解器）────────────────────────

    # 统一 ODE 状态映射（器官 + 疾病）。
    # Step 1（solver-refactor-roadmap-v3）：实现已抽到 src/engine/state_vector.py，
    # 这里保留类属性名做向后兼容（experiments/tools 通过 vc._UNIFIED_MODULES 访问）。
    _UNIFIED_MODULES = UNIFIED_MODULES

    def _build_unified_state_map(self) -> dict[tuple[str, str], int]:
        """建立 (module_name, var_name) → y-array index 映射表（器官 + 疾病）。

        Step 1: 转发到 src/engine/state_vector.build_state_map。零行为变化。
        """
        return _build_state_map_fn(self)

    def _pack_unified_state(self) -> np.ndarray:
        """将所有器官 + 疾病状态打包成 numpy 向量 y0。

        Step 1: 转发到 src/engine/state_vector.pack_state。零行为变化。
        """
        return _pack_state_fn(self)

    def _unpack_unified_state(self, y: np.ndarray) -> None:
        """将 numpy 向量 y 分解到各模块的实例属性。

        Step 1: 转发到 src/engine/state_vector.unpack_state。零行为变化。
        """
        _unpack_state_fn(self, y)

    def _unified_rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """
        统一 ODE 右端函数（供 solve_ivp Radau 调用）。

        半隐式耦合策略：
        - 在 rhs(t,y) 调用时，用上一 rhs 调用的 outputs 路由为当前 inputs
        - 每个模块的 derivatives() 只读 inputs（不读其他模块的当前状态）
        - Radau 的 Newton 迭代会自动收敛到耦合解

        Step 1: 转发到 src/engine/state_vector.unified_rhs。零行为变化。
        完整数据流文档见 src/engine/state_vector.py。
        """
        return _unified_rhs_fn(self, t, y)

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
        """返回所有 active 疾病的 namespaced module 名列表。

        用 `disease.{name}` 形式给每个疾病独立命名空间，避免多病 state var
        名字冲突。Q1 (2026-06-14) 多病叠加支持。
        """
        return [
            f"disease.{d.name}" for d in self.diseases
            if d.active and hasattr(d, "compute_derivatives")
        ]

    def _disease_for_mname(self, mname: str):
        """根据 'disease.{name}' namespace 找到对应 DiseaseModule 实例。"""
        assert mname.startswith("disease."), f"unexpected mname {mname!r}"
        disease_name = mname[len("disease."):]
        for d in self.diseases:
            if d.name == disease_name:
                return d
        raise KeyError(f"no disease named {disease_name!r} in self.diseases")

    def _pack_disease_state(self) -> np.ndarray:
        """将当前所有疾病状态打包成 numpy 向量 y0。"""
        state_map = self._build_ivp_state_map()
        n = len(state_map)
        y0 = np.zeros(n)
        for (mname, vname), idx in state_map.items():
            if mname.startswith("disease."):
                d = self._disease_for_mname(mname)
                y0[idx] = d._state_vars[vname]
        return y0

    def _unpack_disease_state(self, y: np.ndarray) -> None:
        """将 numpy 向量 y 分解到各疾病模块的 _state_vars。"""
        state_map = self._build_ivp_state_map()
        for (mname, vname), idx in state_map.items():
            if mname.startswith("disease."):
                d = self._disease_for_mname(mname)
                d._state_vars[vname] = y[idx]

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
            "immune": {"antibiotic_effect": self.immune.antibiotic_effect},
        }

    def _ivp_rhs(self, t: float, y: np.ndarray) -> np.ndarray:
        """ODE 右端函数（供 solve_ivp 调用）。Q1 (2026-06-14): 遍历所有 active 疾病。"""
        self._unpack_disease_state(y)
        engine_state = self._get_engine_state()
        state_map = self._build_ivp_state_map()
        n = len(state_map)
        dydt = np.zeros(n)

        # Cache derivatives per disease to avoid redundant calls
        per_disease_derivs: dict = {}
        for (mname, vname), idx in state_map.items():
            if mname.startswith("disease."):
                if mname not in per_disease_derivs:
                    d = self._disease_for_mname(mname)
                    per_disease_derivs[mname] = d.compute_derivatives(engine_state)
                dydt[idx] = per_disease_derivs[mname].get(vname, 0.0)

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

    def run_unified_ivp(self, t_end: float, dt_save: float = 1.0):
        """使用 Radau 隐式求解器跑统一 ODE 系统（所有器官 + 疾病）。

        半隐式耦合：_cached_inputs 在每次 rhs 调用时从上一输出的 outputs 填充。
        Radau 的 Newton 迭代会收敛耦合解。

        Args:
            t_end: 仿真结束时间（秒）
            dt_save: 采样间隔（秒）

        Returns:
            solve_ivp result object with sol.t, sol.y
        """
        from scipy.integrate import solve_ivp

        # 初始化缓存（启动时为空，使用模块默认值）
        self._cached_inputs.clear()

        y0 = self._pack_unified_state()
        state_map = self._build_unified_state_map()

        # 预热：调用一次 rhs 以初始化 _cached_inputs
        if len(y0) > 0:
            _ = self._unified_rhs(0.0, y0)

        t_eval = np.arange(0.0, t_end + dt_save, dt_save)
        t_eval = t_eval[t_eval <= t_end]  # clip to t_span

        sol = solve_ivp(
            self._unified_rhs,
            [0.0, t_end],
            y0,
            method='Radau',
            rtol=1e-5,
            atol=1e-8,
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
            logger.warning("未知场景：%s", scenario_name)
            logger.warning("可用场景：%s", list(scenarios.keys()))
            return

        logger.info("%s", f"{'='*60}")
        logger.info("  场景：%s", scenario_name)
        logger.info("%s", f"{'='*60}")

        # 重置
        self.__init__(body_weight_kg=self.w)
        scenarios[scenario_name]()
        self.simulate(T_MAX_MINUTES, verbose=True)

        logger.info("事件记录：")
        for event in self.event_log[-5:]:
            logger.info("  %s", event)

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

    def to_persistence_snapshot(self) -> dict:
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
            # Q1 (2026-06-14): 多病叠加 — list 形式，每个 disease 一个 summary
            "disease_state": [d.summary() for d in self.diseases if d.active] or None,
            # R5 Stage 4: 完整精度疾病状态（供恢复用，包含所有疾病不止 active 的）
            "disease_state_full": [d.full_state() for d in self.diseases] or None,
        }

    def to_minimal_snapshot(self) -> dict:
        """R6 Layer B: deprecated legacy alias for `to_persistence_snapshot()`.

        Prefer the outer-layer adapter `game.persistence_adapter.build_persistence_snapshot`
        — session persistence is an application concern, not a kernel concern.
        This alias is kept only to avoid breaking old callers and tests.
        """
        return self.to_persistence_snapshot()

    def print_summary(self):
        """打印当前状态摘要"""
        logger.info("--- 当前状态 (t=%.1fs) ---", self.current_time_s)
        logger.info("心血管: HR=%.0f bpm, CO=%.0f mL/min, MAP=%.1f mmHg",
                    self.heart.heart_rate, self.heart.cardiac_output, self.heart.mean_arterial_pressure)
        logger.info("  收缩力=%.3f, SVR=%.2f (factor=%.2f)",
                    self.heart.contractility_factor, self.heart.SVR, self.toxicology.svr_factor)
        logger.info("呼吸: RR=%.0f /min, PaO2=%.0f mmHg, PaCO2=%.0f mmHg",
                    self.lung.respiratory_rate, self.blood.arterial_PO2_mmHg, self.blood.arterial_PCO2_mmHg)
        logger.info("肾脏: GFR=%.1f mL/min, 尿量=%.3f mL/min, BUN=%.1f mg/dL",
                    self.kidney.GFR, self.kidney.urine_output, self.blood.bun_mg_dL)
        logger.info("血液: 血糖=%.2f mmol/L, 血容量=%.0f mL, pH=%.3f",
                    self.blood.glucose_mmol_L, self.heart.circulating_volume_ml, self.blood.arterial_pH)
        hh = self.organ_health
        if hh.heart_health < 0.95 or hh.lung_health < 0.95 or hh.kidney_health < 0.95:
            logger.info("器官健康: 心=%.2f  肺=%.2f  肾=%.2f",
                        hh.heart_health, hh.lung_health, hh.kidney_health)
        logger.info("肝脏: 代谢=%.2f  解毒=%.2f  糖原=%.2f",
                    self.liver.metabolic_activity, self.liver.detox_capacity, self.liver.glycogen_fraction)
        logger.info("肠道: 蠕动=%.2f  屏障=%.2f  菌群=%.2f",
                    self.gut.gut_motility, self.gut.barrier_integrity, self.gut.microbiome_activity)


# 参数导入已移至文件顶部
