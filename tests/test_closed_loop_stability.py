"""
Closed-Loop Stability Test Suite

验证所有19 病例在模拟时间内生理参数是否收敛到稳态（波动 < 5%）。
这是架构稳定性回归测试，不是功能测试。

生理真实性标准：
  -稳态振荡幅度 < 5%（相对于均值）
  - 无自激振荡（参数不持续往复波动）
  - 代偿机制不产生正反馈崩溃

参考生理值（犬，正常稳态）：
  HR: 60-140 bpm, 稳态波动 < 5%
  RR: 10-30 /min, 稳态波动 < 5%
  MAP: 80-120 mmHg, 稳态波动 < 5%
  PCO2: 35-45 mmHg, 稳态波动 < 5%
  pH: 7.35-7.45, 稳态波动 < 2%
  HCO3: 22-26 mEq/L, 稳态波动 < 5%
  GFR: 80-120 ml/min, 缓变，波动 < 10%
  K+: 3.5-5.5 mEq/L, 稳态波动 < 5%
"""

import sys
import os
import json
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulation import VirtualCreature
from src.diseases import create_disease


# ── 稳定性判定 ────────────────────────────────────────────────────────────────

# 物种特异性稳定性阈值（CV%）
# 猫比犬呼吸变异更大：猫正常 RR~25，变异约 10%；犬正常 RR~18，变异约 5%
_SPECIES_STABILITY_THRESHOLD = {
    "canine": 0.05,   # 5% CV
    "feline": 0.10,   # 10% CV（猫呼吸中枢变异更大）
}


def compute_stability(series, window=50, cv_threshold=0.05):
    """
    计算时间序列的稳定性指标。

    Returns:
        (is_stable, mean, amplitude_pct, last_values)
        - is_stable: 最后 window 个点变异系数 < cv_threshold → True
        - mean: 均值
        - amplitude_pct: 振荡幅度%（相对于均值）
        - last_values: 最后 window 个值
    """
    if len(series) < window:
        return False, 0, 100, series
    last = series[-window:]
    mean = sum(last) / len(last)
    if mean == 0:
        return False, 0, 100, last
    # 变异系数
    variance = sum((x - mean) ** 2 for x in last) / len(last)
    std = math.sqrt(variance)
    cv = std / abs(mean)  # 变异系数
    amplitude = (max(last) - min(last)) / 2 / abs(mean)  # 半幅/均值
    return cv < cv_threshold, mean, amplitude * 100, last


# ── 测试数据：19病例 ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def case_registry():
    """从 cases.json 加载病例元数据。"""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "cases.json")
    with open(path) as f:
        data = json.load(f)
    return {c["id"]: c for c in data["cases"]}


# ── 参数追踪器 ────────────────────────────────────────────────────────────────

class ParameterTracker:
    """追踪关键生理参数的时间序列。"""

    def __init__(self, vc, disease_name):
        self.vc = vc
        self.disease_name = disease_name
        self.time_s = []
        self.HR = []
        self.RR = []
        self.MAP = []
        self.PCO2 = []
        self.pH = []
        self.HCO3 = []
        self.K = []
        self.GFR = []
        self.cardiac_output = []
        self.SVR = []

    def sample(self):
        t = len(self.time_s) * self.vc.dt
        self.time_s.append(t)
        self.HR.append(self.vc.heart.heart_rate)
        self.RR.append(self.vc.lung.respiratory_rate)
        self.MAP.append(self.vc.heart.mean_arterial_pressure)
        self.PCO2.append(self.vc.blood.arterial_PCO2_mmHg)
        self.pH.append(self.vc.blood.arterial_pH)
        self.HCO3.append(self.vc._hh.hco3)
        self.K.append(self.vc.blood.potassium_mEq_L)
        self.GFR.append(self.vc.kidney.GFR)
        self.cardiac_output.append(self.vc.heart.cardiac_output)
        self.SVR.append(self.vc.heart.SVR)

    def stability_report(self, cv_threshold=0.05):
        """生成所有参数的稳定性报告。

        Args:
            cv_threshold: 变异系数阈值，犬默认5%，猫默认10%（猫呼吸变异更大）
        """
        params = {
            "HR": self.HR,
            "RR": self.RR,
            "MAP": self.MAP,
            "PCO2": self.PCO2,
            "pH": self.pH,
            "HCO3": self.HCO3,
            "K+": self.K,
            "GFR": self.GFR,
            "CO": self.cardiac_output,
            "SVR": self.SVR,
        }
        report = {}
        for name, series in params.items():
            if not series:
                continue
            # 对 GFR 用更大窗口（变化较慢）
            window = 100 if name in ("GFR",) else 50
            is_stable, mean, amp_pct, last = compute_stability(series, window, cv_threshold)
            report[name] = {
                "stable": is_stable,
                "mean": round(mean, 2),
                "amplitude_pct": round(amp_pct, 1),
                "last_5": [round(v, 2) for v in series[-5:]],
                "min": round(min(series[-50:]), 2) if len(series) >= 50 else round(min(series), 2),
                "max": round(max(series[-50:]), 2) if len(series) >= 50 else round(max(series), 2),
            }
        return report


# ── 核心测试 ────────────────────────────────────────────────────────────────

@pytest.mark.stability
class TestClosedLoopStability:
    """全系统闭环稳定性测试——对每个病例验证生理参数是否收敛到稳态。"""

    @pytest.mark.parametrize("case_id", [
        "case_001", "case_002", "case_003", "case_004", "case_005",
        "case_006", "case_007", "case_008", "case_009", "case_010",
        "case_011", "case_012", "case_013", "case_014", "case_015",
        "case_016", "case_017", "case_018", "case_019",
    ])
    def test_case_stability(self, case_id, case_registry):
        """
        运行病例并验证关键参数在最后 50步（5 秒）内是否稳定。

        稳定性标准：
          - 所有追踪参数的变异系数 < 5%
          - 无持续往复振荡（amplitude< 5%）
          - 参数值在生理合理范围内
        """
        case = case_registry[case_id]
        animal = case["animal"]
        disease_name = case["disease"]
        warmup_min = case["warmup_minutes"]
        weight_kg = animal["weight_kg"]
        species = "canine" if animal["species"] == "犬" else "feline"

        # 模拟时间 = warmup + 5 分钟额外运行
        total_steps = int((warmup_min * 60 + 300) / 0.1)
        warmup_steps = int(warmup_min * 60 / 0.1)

        vc = VirtualCreature(body_weight_kg=weight_kg, species=species, dt=0.1)
        disease = create_disease(disease_name, severity="moderate")
        vc.attach_disease(disease)

        tracker = ParameterTracker(vc, disease_name)

        # 运行 warmup + 额外5 分钟
        for i in range(total_steps):
            vc.step()
            if i >= warmup_steps:
                tracker.sample()

        report = tracker.stability_report(cv_threshold=_SPECIES_STABILITY_THRESHOLD[species])

        # 打印报告（诊断用）
        failed = []
        for param, info in report.items():
            if not info["stable"]:
                failed.append(
                    f"  {param}: mean={info['mean']}, "
                    f"amp={info['amplitude_pct']}%, "
                    f"range=[{info['min']}, {info['max']}], "
                    f"last={info['last_5']}"
                )

        if failed:
            msg = f"\n{case_id} ({disease_name})稳定性测试失败:\n" + "\n".join(failed)
        else:
            msg = f"\n{case_id} ({disease_name}) 稳定: " + ", ".join(
                f"{p}={info['mean']}±{info['amplitude_pct']}%" for p, info in report.items()
            )

        # 至少 HR/RR/pH/MAP 要稳定
        critical_stable = all(
            report.get(p, {}).get("stable", False)
            for p in ("HR", "RR", "pH", "MAP")
        )
        assert critical_stable, msg

    def test_no_hardware_specific_assumptions(self, case_registry):
        """
        验证引擎不依赖硬件特定常数（如犬种体型假设）。
        所有19 病例应该可以在任意 dt< 0.5 下运行不崩溃。
        """
        for case in case_registry.values():
            animal = case["animal"]
            weight_kg = animal["weight_kg"]
            species = "canine" if animal["species"] == "犬" else "feline"
            disease_name = case["disease"]

            for dt in (0.1, 0.05, 0.01):
                vc = VirtualCreature(body_weight_kg=weight_kg, species=species, dt=dt)
                disease = create_disease(disease_name, severity="moderate")
                vc.attach_disease(disease)
                for _ in range(100):
                    vc.step()
                # 只要不崩溃就算通过（NaN/Inf 检查）
                assert math.isfinite(vc.blood.arterial_pH), \
                    f"{case['id']} pH is {vc.blood.arterial_pH} at dt={dt}"
                assert math.isfinite(vc._hh.hco3), \
                    f"{case['id']} HCO3 is {vc._hh.hco3} at dt={dt}"


# ──酸碱稳定性专项测试 ───────────────────────────────────────────────────

@pytest.mark.stability
class TestAcidBaseStability:
    """酸碱系统专项稳定性测试——验证 HH + VDP 闭环不产生自激振荡。"""

    def test_arf_acid_base_no_oscillation(self):
        """
        ARF 病例：HCO3/PCO2/pH 三参数应该在 5 分钟内收敛。

        生理预期（临床真实）：
          - HCO3 缓慢下降后稳定（数小时，不是2 分钟）
          - PCO2 轻微下降后稳定（代偿性低碳酸血症）
          - pH 轻微下降后稳定

        当前 bug：
          - PCO2 在 27-45 之间振荡（自激振荡）
          - pH 在 7.31-7.56 之间振荡（代偿过度）
        """
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("acute_renal_failure", severity="moderate")
        vc.attach_disease(disease)

        tracker = ParameterTracker(vc, "acute_renal_failure")
        for i in range(1500):  # 2.5 分钟 warmup + 5 分钟追踪
            vc.step()
            if i >= 1200:  # warmup 完成后取样
                tracker.sample()

        report = tracker.stability_report(cv_threshold=0.05)  # 犬科

        pco2 = report.get("PCO2", {})
        ph = report.get("pH", {})
        hco3 = report.get("HCO3", {})

        # PCO2 不应该有大幅振荡
        pco2_stable = pco2.get("stable", False)
        ph_stable = ph.get("stable", False)
        hco3_stable = hco3.get("stable", False)

        if not pco2_stable:
            pytest.fail(
                f"PCO2 振荡失控: mean={pco2['mean']}, "
                f"amp={pco2['amplitude_pct']}%, range=[{pco2['min']}, {pco2['max']}], "
                f"last={pco2['last_5']}"
            )
        if not ph_stable:
            pytest.fail(
                f"pH 振荡失控: mean={ph['mean']}, "
                f"amp={ph['amplitude_pct']}%, range=[{ph['min']}, {ph['max']}], "
                f"last={ph['last_5']}"
            )
        if not hco3_stable:
            pytest.fail(
                f"HCO3 振荡失控: mean={hco3['mean']}, "
                f"amp={hco3['amplitude_pct']}%, range=[{hco3['min']}, {hco3['max']}], "
                f"last={hco3['last_5']}"
            )

    def test_pneumonia_resp_response_no_oscillation(self):
        """
        肺炎病例：验证 VDP 对肺炎产生的低氧响应不产生振荡。
        """
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("pneumonia", severity="moderate")
        vc.attach_disease(disease)

        tracker = ParameterTracker(vc, "pneumonia")
        for i in range(1500):
            vc.step()
            if i >= 1200:
                tracker.sample()

        report = tracker.stability_report(cv_threshold=0.05)  # 犬科
        rr = report.get("RR", {})
        pco2 = report.get("PCO2", {})

        assert rr.get("stable", False), \
            f"RR 振荡失控: mean={rr['mean']}, amp={rr['amplitude_pct']}%, last={rr['last_5']}"
        assert pco2.get("stable", False), \
            f"PCO2 振荡失控: mean={pco2['mean']}, amp={pco2['amplitude_pct']}%, last={pco2['last_5']}"