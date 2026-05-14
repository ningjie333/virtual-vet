"""
OrganHealthTracker — 多器官衰竭追踪系统

追踪心脏/肺/肾脏/肝脏在危重期间遭受的不可逆损伤。
损伤累积后永久改变器官基线参数，无法通过任何治疗逆转。

设计原则：
  - 玩家看不到损伤数值
  - 损伤通过体征变化间接体现
  - S型曲线：短时间耐受好 → 超过临界点后急剧恶化
"""
import math


class OrganHealthTracker:
    """
    四个器官的健康基线追踪器。
    初始: 每个器官 health = 1.0 (100% 健康)
    衰竭: 持续暴露于危险条件 → health 下降
    最终: health 接近 0 → 该器官无法维持基本功能 → 死亡
    """

    # ── 衰竭阈值 (秒) — 低灌注/缺氧累积超过此值开始产生不可逆损伤 ──
    HEART_THRESHOLD_S = 180
    LUNG_THRESHOLD_S = 180
    KIDNEY_THRESHOLD_S = 240
    LIVER_THRESHOLD_S = 240

    # ── 衰竭速率 (health/s) — 超阈值后的线性退化速率 ──
    HEART_DEGRADE_RATE = 0.002
    LUNG_DEGRADE_RATE = 0.002
    KIDNEY_DEGRADE_RATE = 0.0025
    LIVER_DEGRADE_RATE = 0.002

    # — 完全衰竭 health 值 — 低于此值器官无法维持基本功能 ──
    HEART_FAILURE_AT = 0.3
    LUNG_FAILURE_AT = 0.2
    KIDNEY_FAILURE_AT = 0.15
    LIVER_FAILURE_AT = 0.15

    def __init__(self):
        # ===== 器官健康状态 (1.0 = 完全健康, 0.0 = 衰竭) =====
        self.heart_health = 1.0
        self.lung_health = 1.0
        self.kidney_health = 1.0
        self.liver_health = 1.0

        # ===== 暴露时间追踪 (秒) =====
        self._heart_exposure = 0.0   # MAP < 65 或 HR > 160 的累计秒数
        self._lung_exposure = 0.0    # PaO2 < 65 的累计秒数
        self._kidney_exposure = 0.0  # MAP < 65 的累计秒数
        self._liver_exposure = 0.0   # MAP < 65 或肝代谢活性 < 0.3 累计秒数

        # 阈值和速率引用类级常数
        self._heart_threshold = self.HEART_THRESHOLD_S
        self._lung_threshold = self.LUNG_THRESHOLD_S
        self._kidney_threshold = self.KIDNEY_THRESHOLD_S
        self._liver_threshold = self.LIVER_THRESHOLD_S
        self._heart_degrade_rate = self.HEART_DEGRADE_RATE
        self._lung_degrade_rate = self.LUNG_DEGRADE_RATE
        self._kidney_degrade_rate = self.KIDNEY_DEGRADE_RATE
        self._liver_degrade_rate = self.LIVER_DEGRADE_RATE
        self._heart_failure_at = self.HEART_FAILURE_AT
        self._lung_failure_at = self.LUNG_FAILURE_AT
        self._kidney_failure_at = self.KIDNEY_FAILURE_AT
        self._liver_failure_at = self.LIVER_FAILURE_AT

    def track(
        self,
        dt: float,
        heart_state: dict,
        lung_state: dict,
        kidney_state: dict,
        liver_state: dict | None = None,
    ):
        MAP = heart_state["MAP_mmHg"]
        PaO2 = lung_state["arterial_PO2"]
        HR = heart_state["heart_rate_bpm"]

        # --- 心脏衰竭条件 ---
        heart_under_stress = (MAP < 65) or (HR > 160)
        if heart_under_stress:
            self._heart_exposure += dt
            excess = max(0, self._heart_exposure - self._heart_threshold)
            if excess > 0:
                accelerate = self._sigmoid_acceleration(excess / self._heart_threshold)
                degrade = self._heart_degrade_rate * dt * accelerate
                self.heart_health = max(self._heart_failure_at, self.heart_health - degrade)
        elif self._heart_exposure > 0:
            self._heart_exposure = max(0, self._heart_exposure - dt * 2.0)

        # --- 肺衰竭条件 ---
        lung_under_stress = (PaO2 < 65)
        if lung_under_stress:
            self._lung_exposure += dt
            excess = max(0, self._lung_exposure - self._lung_threshold)
            if excess > 0:
                accelerate = self._sigmoid_acceleration(excess / self._lung_threshold)
                degrade = self._lung_degrade_rate * dt * accelerate
                self.lung_health = max(self._lung_failure_at, self.lung_health - degrade)
        elif self._lung_exposure > 0:
            self._lung_exposure = max(0, self._lung_exposure - dt * 2.0)

        # --- 肾衰竭条件 ---
        if MAP < 65:
            self._kidney_exposure += dt
            excess = max(0, self._kidney_exposure - self._kidney_threshold)
            if excess > 0:
                accelerate = self._sigmoid_acceleration(excess / self._kidney_threshold)
                degrade = self._kidney_degrade_rate * dt * accelerate
                self.kidney_health = max(
                    self._kidney_failure_at, self.kidney_health - degrade
                )
        elif self._kidney_exposure > 0:
            self._kidney_exposure = max(0, self._kidney_exposure - dt * 2.0)

        # --- 肝衰竭条件 ---
        # 触发：MAP < 65 (低灌注) 或 代谢活性严重下降
        if liver_state is not None:
            metabolic_activity = liver_state.get("metabolic_activity", 1.0)
            liver_under_stress = (MAP < 65) or (metabolic_activity < 0.3)
            if liver_under_stress:
                self._liver_exposure += dt
                excess = max(0, self._liver_exposure - self._liver_threshold)
                if excess > 0:
                    accelerate = self._sigmoid_acceleration(
                        excess / self._liver_threshold
                    )
                    degrade = self._liver_degrade_rate * dt * accelerate
                    self.liver_health = max(
                        self._liver_failure_at, self.liver_health - degrade
                    )
            elif self._liver_exposure > 0:
                self._liver_exposure = max(0, self._liver_exposure - dt * 2.0)

    # ========== 查询接口 ==========

    @property
    def heart_factor(self):
        return self.heart_health

    @property
    def lung_factor(self):
        return self.lung_health

    @property
    def kidney_factor(self):
        return self.kidney_health

    @property
    def liver_factor(self):
        return self.liver_health

    @property
    def any_failure(self):
        return (
            self.heart_health <= self._heart_failure_at
            or self.lung_health <= self._lung_failure_at
            or self.kidney_health <= self._kidney_failure_at
            or self.liver_health <= self._liver_failure_at
        )

    # ========== S型加速曲线 ==========

    @staticmethod
    def _sigmoid_acceleration(ratio):
        """S型加速：刚超阈值退化慢，超标50%后急剧恶化"""
        if ratio <= 0:
            return 1.0
        x = (ratio - 0.3) * 12
        return 1.0 + 9.0 / (1.0 + math.exp(-x))

    # ========== 调试 ==========

    def summary(self):
        return {
            "heart_health": round(self.heart_health, 3),
            "lung_health": round(self.lung_health, 3),
            "kidney_health": round(self.kidney_health, 3),
            "liver_health": round(self.liver_health, 3),
            "heart_exposure_s": round(self._heart_exposure, 0),
            "lung_exposure_s": round(self._lung_exposure, 0),
            "kidney_exposure_s": round(self._kidney_exposure, 0),
            "liver_exposure_s": round(self._liver_exposure, 0),
            "any_failure": self.any_failure,
        }
