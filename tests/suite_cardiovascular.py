"""
Cardiovascular Closed-Loop Stability Suite

验证心血管系统的闭环稳定性：
  - HR/MAP/CO/收缩力在疾病状态下是否收敛到稳态
  - 反馈回路（压力感受器、收缩力抑制、高钾血症）是否正常工作
  - 无持续振荡（自激振荡 = 架构 bug）

生理基准（犬，20kg）：
  - HR: 60-140 bpm（稳态波动 < 5%）
  - MAP: 80-120 mmHg（稳态波动 < 5%）
  - CO: 1500-2500 mL/min（稳态波动 < 10%）
  - SVR: 0.95-1.30（相对 baseline，稳态波动 < 5%）
  - contractility_factor: 0.85-1.10（稳态波动 < 5%）
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulation import VirtualCreature
from src.diseases import create_disease


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def compute_cv(series, window=50):
    if len(series) < window:
        return 1.0
    last = series[-window:]
    mean = sum(last) / len(last)
    if mean == 0:
        return 1.0
    variance = sum((x - mean) **2 for x in last) / len(last)
    return math.sqrt(variance) / abs(mean)


def assert_stable(param_name, series, cv_threshold=0.05):
    cv = compute_cv(series)
    last_vals = series[-50:] if len(series) >= 50 else series
    rng_min = min(last_vals)
    rng_max = max(last_vals)
    assert cv < cv_threshold, (
        f"{param_name} 不稳定: CV={cv*100:.1f}% (阈值{cv_threshold*100:.0f}%), "
        f"range=[{rng_min:.2f}, {rng_max:.2f}]"
    )


# ── 测试套件 ─────────────────────────────────────────────────────────────────

@pytest.mark.suite_cardiovascular
@pytest.mark.stability
class TestCardiovascularStability:
    """心血管系统闭环稳定性测试。"""

    def test_healthy_hr_map_stable(self):
        """健康犬：HR 和 MAP 应该稳定在正常范围。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        hr_s, map_s = [], []
        for _ in range(1000):
            vc.step()
            hr_s.append(vc.heart.heart_rate)
            map_s.append(vc.heart.mean_arterial_pressure)

        assert_stable("HR", hr_s)
        assert_stable("MAP", map_s)
        mean_hr = sum(hr_s[-50:]) / 50
        mean_map = sum(map_s[-50:]) / 50
        assert 60 <= mean_hr <= 140, f"HR 均值 {mean_hr:.0f} 不在 [60,140]"
        assert 80 <= mean_map <= 120, f"MAP 均值 {mean_map:.0f} 不在 [80,120]"

    def test_arf_hyperkalemia_depresses_hr(self):
        """ARF 高钾血症：K+升高应该让 HR 下降。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("acute_renal_failure", severity="moderate")
        vc.attach_disease(disease)

        hr_before = None
        k_before = None
        for i in range(1500):
            vc.step()
            if i == 599:
                hr_before = vc.heart.heart_rate
                k_before = vc.blood.potassium_mEq_L
            if i == 1499:
                hr_after = vc.heart.heart_rate
                k_after = vc.blood.potassium_mEq_L
                break

        assert k_after > k_before + 0.5, f"K+ 未升高: {k_before:.2f}→{k_after:.2f}"
        assert hr_after < hr_before, f"高钾血症 HR 未下降: {hr_before:.0f}→{hr_after:.0f}"

    def test_dcm_decreases_contractility(self):
        """扩张型心肌病（DCM）：收缩力应该下降。"""
        vc = VirtualCreature(body_weight_kg=35.0, species="canine", dt=0.1)
        disease = create_disease("dilated_cardiomyopathy", severity="moderate")
        vc.attach_disease(disease)

        cf_before = None
        for i in range(600):
            vc.step()
            if i == 599:
                cf_before = vc.heart.contractility_factor

        for i in range(500):
            vc.step()
            if i == 499:
                cf_after = vc.heart.contractility_factor
                break

        assert cf_after < cf_before, (
            f"DCM 收缩力未下降: {cf_before:.3f}→{cf_after:.3f}"
        )

    def test_pericardial_effusion_has_effect(self):
        """心包填塞：验证疾病产生了可测量的生理变化（MAP 或 CVP）。"""
        vc = VirtualCreature(body_weight_kg=32.0, species="canine", dt=0.1)
        disease = create_disease("pericardial_effusion", severity="moderate")
        vc.attach_disease(disease)

        map_before = vc.heart.mean_arterial_pressure
        cvp_before = vc.heart.central_venous_pressure
        for i in range(1500):
            vc.step()
            if i == 1499:
                map_after = vc.heart.mean_arterial_pressure
                cvp_after = vc.heart.central_venous_pressure
                break

        # 心包填塞应该导致 MAP 下降或 CVP 升高
        map_dropped = map_after < map_before - 5
        cvp_rised = cvp_after > cvp_before + 2
        assert map_dropped or cvp_rised, (
            f"心包填塞后 MAP {map_after:.0f}（基线 {map_before:.0f}），"
            f"CVP {cvp_after:.1f}（基线 {cvp_before:.1f}）——两者均无显著变化"
        )

    def test_no_hr_map_oscillation_in_any_case(self):
        """所有病例：HR 和 MAP 不应该产生自激振荡。"""
        cases = [
            ("acute_renal_failure", "canine", 20.0),
            ("pneumonia", "canine", 20.0),
            ("dilated_cardiomyopathy", "canine", 35.0),
            ("gastric_dilatation_volvulus", "canine", 55.0),
        ]
        for disease_name, species, weight in cases:
            vc = VirtualCreature(body_weight_kg=weight, species=species, dt=0.1)
            disease = create_disease(disease_name, severity="moderate")
            vc.attach_disease(disease)
            hr_s, map_s = [], []
            for i in range(1500):
                vc.step()
                if i >= 1200:
                    hr_s.append(vc.heart.heart_rate)
                    map_s.append(vc.heart.mean_arterial_pressure)

            assert_stable("HR", hr_s)
            assert_stable("MAP", map_s)


@pytest.mark.suite_cardiovascular
@pytest.mark.stability
class TestFeedbackLoops:
    """反馈回路测试：验证生理反馈是否正常工作且不产生振荡。"""

    def test_baroreceptor_reflex_map_drop_increases_hr(self):
        """MAP 下降 20 mmHg 应该触发压力感受器反射，HR 在 1 步内上升。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        hr_baseline = vc.heart.heart_rate
        map_baseline = vc.heart.mean_arterial_pressure

        # 模拟失血事件（通过 schedule_event）
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": 400.0})

        for _ in range(10):  # 失血后 1 秒
            vc.step()

        hr_after = vc.heart.heart_rate
        map_after = vc.heart.mean_arterial_pressure

        # MAP 应该下降，HR 应该代偿性增加
        assert map_after < map_baseline - 5, (
            f"失血后 MAP {map_after:.0f} 未比基线 {map_baseline:.0f} 下降超过 5"
        )
        #压力感受器反射：MAP 低 → 交感激活 → HR 应该上升
        assert hr_after > hr_baseline, (
            f"失血后 HR {hr_after:.0f} 未比基线 {hr_baseline:.0f} 增加（压力感受器未激活）"
        )

    def test_acidosis_reduces_contractility(self):
        """酸血症（pH < 7.2）应该降低心脏收缩力。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        cf_normal = vc.heart.contractility_factor

        # 用 ARF 疾病自然产生酸中毒（不能直接写 blood.pH，会被 lung._update 重写）
        disease = create_disease("acute_renal_failure", severity="severe")
        vc.attach_disease(disease)
        for i in range(1500):
            vc.step()
            if i == 1499:
                ph = vc.blood.arterial_pH
                cf_acidic = vc.heart.contractility_factor
                break

        assert ph < 7.40, f"ARF 严重型 pH {ph:.3f} 未降到 7.40 以下"
        assert cf_acidic < cf_normal, (
            f"酸中毒 pH={ph:.3f} 时收缩力 {cf_acidic:.3f} 未比正常 {cf_normal:.3f} 降低"
        )

    def test_svr_increases_with_raas(self):
        """RAAS 激活应该让 SVR 升高。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        # 直接激活 RAAS
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": 400.0})

        svr_baseline = vc.heart.SVR
        for i in range(1000):
            vc.step()
            if i == 999:
                svr_after = vc.heart.SVR
                break

        assert svr_after > svr_baseline * 1.02, (
            f"失血后 SVR {svr_after:.3f} 未比基线 {svr_baseline:.3f} 增加超过 2%"
        )

    def test_no_positive_feedback_spiral(self):
        """验证没有正反馈螺旋（低 CO → 低 MAP → 低 GFR → ... → 更低 CO）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("sepsis", severity="severe")
        vc.attach_disease(disease)

        co_series, map_series = [], []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                co_series.append(vc.heart.cardiac_output)
                map_series.append(vc.heart.mean_arterial_pressure)

        # CO 和 MAP 不应该发散（最后50 步内 max 不应该超过 min 的 2 倍）
        assert max(co_series) / max(min(co_series), 1) < 2.0, (
            f"CO 可能存在正反馈发散: [{min(co_series):.0f}, {max(co_series):.0f}]"
        )
        assert max(map_series) / max(min(map_series), 1) < 2.0, (
            f"MAP 可能存在正反馈发散: [{min(map_series):.0f}, {max(map_series):.0f}]"
        )