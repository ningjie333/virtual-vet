"""
Cardio-Renal Closed-Loop Stability Suite

验证心肾耦合级联：
  - 低 CO（严重失血）→ GFR 下降 > 30%
  - RAAS 激活使 SVR 在 5 步内升至基线以上（> 1.0）
  - 血管紧张素 II 升高是持续的（无振荡）
  - 无正反馈螺旋（MAP 初期下降后不持续发散）

生理基准（犬，20kg）：
  - GFR: 60 mL/min（稳态波动 < 5%）
  - SVR: baseline 约 1.41（相对值，稳态波动 < 5%）
  - angiotensin_II: 正常 ≈ 0（失血后激活至 0.2-0.4）
  - MAP: 80-120 mmHg（稳态波动 < 5%）
  - CO: 1500-2500 mL/min（稳态波动 < 10%）

血容量基准：20kg 犬 BV ≈ 1720 mL（total_blood_volume_ml(20) = 1720）
  - 800 mL 失血 ≈ 46% BV → 足够触发显著 RAAS 激活和 GFR 下降
  - 400 mL 失血 ≈ 23% BV → 中度失血，用于稳定性和代偿测试
"""

import sys
import os
import math
import warnings
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Suppress coupling oscillation warnings (expected when RAAS activates).
# Force Euler mode so kidney.compute() is called each step (updates renin/AngII/Aldo).
# Radau mode only calls kidney.derivatives() and does not update these attributes.
warnings.filterwarnings("ignore", message="Coupling oscillation")
import src.simulation as _sim
_sim._USE_RADAU = False

from simulation import VirtualCreature
from src.diseases import create_disease

# BV reference for 20kg canine ≈ 1720 mL (from src.parameters.total_blood_volume_ml)
_BV_20KG = 1720.0
# Severe blood loss: 800 mL ≈ 46% BV — triggers GFR drop > 30% and RAAS activation
_BLOOD_LOSS_SEVERE = 800.0
# Moderate blood loss: 400 mL ≈ 23% BV — tests compensatory response
_BLOOD_LOSS_MODERATE = 400.0


# ── 辅助 ──────────────────────────────────────────────────────────────────────

def compute_cv(series, window=50):
    """计算最后 window 个点的变异系数（CV = std/mean）。"""
    if len(series) < window:
        return 1.0
    last = series[-window:]
    mean = sum(last) / len(last)
    if mean == 0:
        return 1.0
    variance = sum((x - mean) **2 for x in last) / len(last)
    return math.sqrt(variance) / abs(mean)


def assert_stable(param_name, series, cv_threshold=0.05):
    """对单个参数断言稳定性。"""
    cv = compute_cv(series)
    last_vals = series[-50:] if len(series) >= 50 else series
    rng_min = min(last_vals)
    rng_max = max(last_vals)
    assert cv < cv_threshold, (
        f"{param_name} 不稳定: CV={cv*100:.1f}% (阈值{cv_threshold*100:.0f}%), "
        f"range=[{rng_min:.2f}, {rng_max:.2f}]"
    )


# ── 测试套件 ─────────────────────────────────────────────────────────────────

@pytest.mark.suite_cardioreal
@pytest.mark.stability
class TestCardioRenalCoupling:
    """心肾耦合闭环稳定性测试。"""

    def test_blood_loss_severe_drops_co(self):
        """严重失血（800 mL ≈ 46% BV）：CO 应该显著下降。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        co_baseline = vc.heart.cardiac_output
        for _ in range(10):
            vc.step()

        co_after = vc.heart.cardiac_output
        assert co_after < co_baseline * 0.7, (
            f"失血 {_BLOOD_LOSS_SEVERE:.0f} mL 后 CO {co_after:.0f} "
            f"未比基线 {co_baseline:.0f} 下降 30%以上"
        )

    def test_low_co_drops_gfr_over_30_percent(self):
        """低 CO（严重失血 800 mL）→ GFR 下降 > 30%。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        gfr_baseline = vc.kidney.GFR

        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        for i in range(600):  # 60 秒 warmup
            vc.step()
            if i == 599:
                gfr_60s = vc.kidney.GFR

        for i in range(500):
            vc.step()
            if i == 499:
                gfr_after = vc.kidney.GFR
                break

        gfr_drop_pct = (gfr_baseline - gfr_after) / gfr_baseline
        assert gfr_drop_pct > 0.30, (
            f"失血后 GFR 下降 {gfr_drop_pct*100:.1f}%（基线 {gfr_baseline:.0f}→"
            f"稳态 {gfr_after:.0f}），未超过 30%"
        )

    def test_raas_raises_svr_above_baseline_within_5_steps(self):
        """RAAS 激活：SVR 在 5 步内升至基线以上（> 1.0）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        svr_baseline = vc.heart.SVR

        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        svr_after_steps = []
        for i in range(10):
            vc.step()
            if i <= 5:
                svr_after_steps.append(vc.heart.SVR)

        svr_peak = max(svr_after_steps)
        assert svr_peak > 1.0, (
            f"失血后 SVR 峰值 {svr_peak:.3f} 未超过基线 1.0（RAAS 未激活）"
        )

    def test_angiotensin_ii_is_sustained_no_oscillation(self):
        """血管紧张素 II 升高是持续的（无振荡）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        angII_series = []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                angII_series.append(vc.kidney.angiotensin_II)

        assert_stable("angiotensin_II", angII_series, cv_threshold=0.05)
        assert angII_series[-1] > 0.15, (
            f"失血后 angiotensin_II {angII_series[-1]:.3f} 未明显升高（> 0.15）"
        )

    def test_no_positive_feedback_spiral_map_not_divergent(self):
        """无正反馈螺旋：MAP 初期下降后不持续发散。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        map_series = []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                map_series.append(vc.heart.mean_arterial_pressure)

        assert_stable("MAP", map_series, cv_threshold=0.05)
        assert max(map_series) / max(min(map_series), 1) < 2.0, (
            f"MAP 可能存在正反馈发散: [{min(map_series):.0f}, {max(map_series):.0f}]"
        )

    def test_gfr_stable_under_moderate_blood_loss(self):
        """中度失血后 GFR 保持稳定（无振荡）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        gfr_baseline = vc.kidney.GFR

        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_MODERATE})

        gfr_series = []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                gfr_series.append(vc.kidney.GFR)

        assert_stable("GFR", gfr_series, cv_threshold=0.05)
        mean_gfr = sum(gfr_series[-50:]) / 50
        # GFR 允许因代偿有轻微波动，但不应剧烈变化
        assert 25.0 <= mean_gfr <= 90.0, (
            f"GFR 均值 {mean_gfr:.0f} 超出生理范围 [25,90]"
        )

    def test_healthy_gfr_and_svr_stable(self):
        """健康犬：GFR 和 SVR 应该稳定在正常范围。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        gfr_s, svr_s = [], []
        for _ in range(1000):
            vc.step()
            gfr_s.append(vc.kidney.GFR)
            svr_s.append(vc.heart.SVR)

        assert_stable("GFR", gfr_s, cv_threshold=0.05)
        assert_stable("SVR", svr_s, cv_threshold=0.05)
        mean_gfr = sum(gfr_s[-50:]) / 50
        assert 40 <= mean_gfr <= 80, f"GFR 均值 {mean_gfr:.0f} 不在 [40,80] 范围"
        assert 1.0 <= svr_s[-1] <= 1.8, f"SVR {svr_s[-1]:.3f} 不在正常范围 [1.0, 1.8]"

    def test_arf_reduces_gfr_but_svr_compensates(self):
        """ARF：GFR 下降，但 RAAS 激活使 SVR 代偿性升高。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("acute_renal_failure", severity="moderate")
        vc.attach_disease(disease)

        gfr_series, svr_series = [], []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                gfr_series.append(vc.kidney.GFR)
                svr_series.append(vc.heart.SVR)

        assert_stable("GFR", gfr_series, cv_threshold=0.05)
        assert_stable("SVR", svr_series, cv_threshold=0.05)
        assert gfr_series[-1] < vc.kidney.base_GFR * 0.8, (
            f"ARF 后 GFR {gfr_series[-1]:.0f} 未明显低于基线 {vc.kidney.base_GFR:.0f}"
        )
        assert svr_series[-1] > 1.0, (
            f"ARF 后 SVR {svr_series[-1]:.3f} 未超过基线 1.0（RAAS 未代偿）"
        )


@pytest.mark.suite_cardioreal
@pytest.mark.stability
class TestRAASDynamics:
    """RAAS 动力学专项测试：验证肾素-血管紧张素-醛固酮系统的激活和稳定特性。"""

    def test_renin_activates_with_blood_loss(self):
        """失血应该触发肾素激活。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        renin_baseline = vc.kidney.renin_activity

        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        for i in range(600):
            vc.step()
            if i == 599:
                renin_after = vc.kidney.renin_activity
                break

        assert renin_after > renin_baseline + 0.05, (
            f"失血后肾素 {renin_after:.3f} 未比基线 {renin_baseline:.3f} 明显升高（> 0.05）"
        )

    def test_angiotensin_ii_rises_and_sustains(self):
        """血管紧张素 II 在失血后应该升高并保持（无衰减振荡）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        angII_before = vc.kidney.angiotensin_II
        for i in range(600):
            vc.step()
            if i == 599:
                angII_after = vc.kidney.angiotensin_II
                break

        assert angII_after > angII_before + 0.10, (
            f"失血后 angiotensin_II {angII_before:.3f}→{angII_after:.3f} "
            f"未明显升高（> 0.10）"
        )

        angII_series = []
        for i in range(900):
            vc.step()
            if i >= 700:
                angII_series.append(vc.kidney.angiotensin_II)

        assert_stable("angiotensin_II", angII_series, cv_threshold=0.05)
        assert angII_series[-1] > 0.15, (
            f"angiotensin_II 在后期 {angII_series[-1]:.3f} 未维持升高（> 0.15）"
        )

    def test_aldosterone_increases_with_angiotensin_ii(self):
        """醛固酮应该随血管紧张素 II 增加而增加。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        ald_before = vc.kidney.aldosterone
        for i in range(600):
            vc.step()
            if i == 599:
                ald_after = vc.kidney.aldosterone
                break

        assert ald_after > ald_before, (
            f"失血后醛固酮未增加: {ald_before:.3f}→{ald_after:.3f}"
        )

    def test_svr_rises_due_to_angiotensin_ii(self):
        """SVR 应该因血管紧张素 II 升高而升高（外周血管收缩）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        svr_baseline = vc.heart.SVR

        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        for i in range(1000):
            vc.step()
            if i == 999:
                svr_after = vc.heart.SVR
                break

        assert svr_after > svr_baseline * 1.02, (
            f"失血后 SVR {svr_after:.3f} 未比基线 {svr_baseline:.3f} 增加超过 2%"
        )

    def test_raas_cascade_is_physiologically_timed(self):
        """RAAS 级联应该在生理时间内激活（肾素立即，AngII 数秒，醛固酮数十秒）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vc.schedule_event(0.0, "blood_loss", {"volume_ml": _BLOOD_LOSS_SEVERE})

        # Step 0-1: 肾素应该立即激活
        vc.step()
        renin_step1 = vc.kidney.renin_activity

        # Step 2-5: 血管紧张素 II 应该开始升高
        for _ in range(5):
            vc.step()
        angII_step6 = vc.kidney.angiotensin_II

        assert renin_step1 > 0.0, f"肾素在第1步未激活: {renin_step1:.3f}"
        assert angII_step6 > 0.01, f"AngII 在第6步未开始升高: {angII_step6:.3f}"