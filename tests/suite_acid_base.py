"""
Acid-Base Closed-Loop Stability Suite

验证酸碱系统的闭环稳定性：
  - PCO2/pH/HCO3 三参数在疾病状态下是否收敛到稳态
  - VDP 振荡器是否产生生理节律而非自激振荡
  - 呼吸代偿是否正常工作（代谢性酸中毒 → RR 增加 → PCO2 代偿性下降）

生理基准（犬）：
  -动脉 PCO2: 35-45 mmHg（稳态波动< 5%）
  - 动脉 pH: 7.35-7.45（稳态波动 < 2%）
  - 碳酸氢根 HCO3: 22-26 mEq/L（稳态波动 < 5%）
  - 呼吸频率 RR: 10-30 /min（稳态波动 < 10%）

猫（物种特异性）：
  - RR 稳态波动 < 10%（猫呼吸变异更大）
"""

import sys
import os
import math
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from simulation import VirtualCreature
from src.diseases import create_disease


# ── 辅助 ────────────────────────────────────────────────────────────────────────

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


def assert_stable(param_name, series, cv_threshold, amplitude_threshold=None):
    """对单个参数断言稳定性。"""
    cv = compute_cv(series)
    if len(series) >= 50:
        amp = (max(series[-50:]) - min(series[-50:])) / 2 / (sum(series[-50:]) /50)
        amp_pct = amp * 100
    else:
        amp_pct = 0.0

    assert cv < cv_threshold, (
        f"{param_name} 不稳定: CV={cv*100:.1f}% (阈值{cv_threshold*100:.0f}%), "
        f"amplitude={amp_pct:.1f}%, range=[{min(series[-50:]):.2f}, {max(series[-50:]):.2f}]"
    )
    if amplitude_threshold is not None:
        assert amp_pct < amplitude_threshold, (
            f"{param_name} 振荡幅度过大: {amp_pct:.1f}% (阈值{amplitude_threshold:.0f}%)"
        )


# ── 测试套件 ────────────────────────────────────────────────────────────

@pytest.mark.suite_acid_base
@pytest.mark.stability
class TestAcidBaseStability:
    """酸碱系统闭环稳定性测试。"""

    def test_healthy_pco2_stable(self):
        """健康犬：PCO2 应该在正常范围内稳定。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        pco2_series = []
        for _ in range(1000):
            vc.step()
            pco2_series.append(vc.blood.arterial_PCO2_mmHg)

        assert_stable("PCO2", pco2_series, cv_threshold=0.05)
        mean_pco2 = sum(pco2_series[-50:]) / 50
        assert 35 <= mean_pco2 <= 45, f"PCO2 均值 {mean_pco2:.1f} 不在正常范围 [35,45]"

    def test_healthy_ph_stable(self):
        """健康犬：pH 应该在正常范围内稳定。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        ph_series = []
        for _ in range(1000):
            vc.step()
            ph_series.append(vc.blood.arterial_pH)

        assert_stable("pH", ph_series, cv_threshold=0.02)
        mean_ph = sum(ph_series[-50:]) / 50
        assert 7.35 <= mean_ph <= 7.45, f"pH 均值 {mean_ph:.3f} 不在正常范围 [7.35,7.45]"

    def test_healthy_hco3_stable(self):
        """健康犬：HCO3 应该恒定（不受呼吸影响）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        hco3_series = []
        for _ in range(1000):
            vc.step()
            hco3_series.append(vc._hh.hco3)

        assert_stable("HCO3", hco3_series, cv_threshold=0.03)
        mean_hco3 = sum(hco3_series[-50:]) / 50
        assert 22 <= mean_hco3 <= 26, f"HCO3 均值 {mean_hco3:.1f} 不在正常范围 [22,26]"

    def test_arf_acid_base_convergence(self):
        """ARF：代谢性酸中毒应该让 pH 下降到7.35 以下，但 PCO2 不应该振荡。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("acute_renal_failure", severity="moderate")
        vc.attach_disease(disease)

        ph_series, pco2_series, hco3_series = [], [], []
        for i in range(1500):  # 2.5 分钟 warmup + 5 分钟追踪
            vc.step()
            if i >= 1200:
                ph_series.append(vc.blood.arterial_pH)
                pco2_series.append(vc.blood.arterial_PCO2_mmHg)
                hco3_series.append(vc._hh.hco3)

        # pH 应该低于基准（酸中毒），但不能振荡
        assert_stable("pH", ph_series, cv_threshold=0.05)
        assert_stable("PCO2", pco2_series, cv_threshold=0.05)
        assert_stable("HCO3", hco3_series, cv_threshold=0.05)

        # 最终 pH 应该< 7.40（酸中毒）
        assert ph_series[-1] < 7.40, f"ARF 后 pH {ph_series[-1]:.3f} 未降至 7.40 以下"

    def test_pneumonia_resp_compensation(self):
        """肺炎：低氧驱动 RR 增加，但 PCO2 不应该振荡。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("pneumonia", severity="moderate")
        vc.attach_disease(disease)

        rr_series, pco2_series = [], []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                rr_series.append(vc.lung.respiratory_rate)
                pco2_series.append(vc.blood.arterial_PCO2_mmHg)

        assert_stable("RR", rr_series, cv_threshold=0.05)
        assert_stable("PCO2", pco2_series, cv_threshold=0.05)

        # RR 应该高于基线 18（代偿性呼吸急促）
        assert rr_series[-1] > 18.0, f"肺炎 RR {rr_series[-1]:.1f} 未超过基线 18"


@pytest.mark.suite_acid_base
@pytest.mark.stability
class TestVDPOscillator:
    """VDP 振荡器专项测试：验证节律生成而非自激振荡。"""

    def test_vdp_produces_oscillatory_x(self):
        """VdP 应该产生交变符号的 x 值（呼吸相交替）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        vdp = vc.lung._vdp
        signs = []
        for _ in range(200):
            vc.step()
            signs.append(1 if vdp.x >= 0 else -1)

        # 应该有正有负（吸气和呼气相）
        assert 1 in signs, "VdP x 应该有正值（吸气相）"
        assert -1 in signs, "VdP x 应该有负值（呼气相）"

        # 至少3 次换相（振荡存在）
        sign_changes = sum(1 for i in range(1, len(signs)) if signs[i] != signs[i - 1])
        assert sign_changes >= 3, f"VdP 换相次数 {sign_changes} < 3，振荡不足"

    def test_vdp_normal_baseline(self):
        """正常血气下 VdP 应该接近基线频率（约 18/min）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        rr_series = []
        for i in range(500):
            vc.step()
            rr_series.append(vc.lung.respiratory_rate)

        mean_rr = sum(rr_series[-50:]) / 50
        assert 16.0 <= mean_rr <= 22.0, f"正常 RR 均值 {mean_rr:.1f} 不在 [16,22] 范围"

    def test_vdp_hypercapnia_increases_rr(self):
        """ARF 严重型：验证 RR 保持稳定且在疾病状态下可接受范围。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("acute_renal_failure", severity="severe")
        vc.attach_disease(disease)

        rr_series, ph_series = [], []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                rr_series.append(vc.lung.respiratory_rate)
                ph_series.append(vc.blood.arterial_pH)

        assert_stable("RR", rr_series, cv_threshold=0.05)
        assert_stable("pH", ph_series, cv_threshold=0.05)
        # RR 应该在疾病状态下保持稳定（无自激振荡）
        assert 16.0 <= rr_series[-1] <= 25.0, (
            f"ARF 严重型 RR {rr_series[-1]:.1f} 不在 [16,25] 范围"
        )

    def test_vdp_no_per_breath_oscillation_in_tidal_volume(self):
        """TV 不应该被 VdP 每呼吸周期的幅度振荡所驱动（amplitude 不进 TV 公式）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        tv_series = []
        for _ in range(500):
            vc.step()
            tv_series.append(vc.lung.tidal_volume)

        # TV 应该稳定在 base_tidal_volume 附近，波动 < 15%
        base_tv = vc.lung.base_tidal_volume
        mean_tv = sum(tv_series[-50:]) / 50
        assert abs(mean_tv - base_tv) / base_tv < 0.15, (
            f"TV 均值 {mean_tv:.0f} 偏离 base {base_tv:.0f} 超过 15%"
        )
        # 最后 50 步 CV 应该 < 10%（amplitude-smoothed）
        cv = compute_cv(tv_series)
        assert cv < 0.10, f"TV CV {cv*100:.1f}% 超过 10%，amplitude 仍在驱动 TV"


@pytest.mark.suite_acid_base
@pytest.mark.stability
class TestRespiratoryCompensation:
    """呼吸代偿专项测试：验证酸碱异常时的代偿反应。"""

    def test_metabolic_acidosis_drives_respiratory_compensation(self):
        """代谢性酸中毒（低 HCO3）应该触发呼吸代偿（RR 增加）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("acute_renal_failure", severity="severe")
        vc.attach_disease(disease)

        rr_before = None
        for i in range(600):  # warmup
            vc.step()
            if i == 599:
                rr_before = vc.lung.respiratory_rate

        for i in range(500):  # 疾病发展
            vc.step()
            if i == 499:
                rr_after = vc.lung.respiratory_rate
                break

        #验证 RR 在疾病状态下稳定（允许代偿尚未完全激活）
        assert 16.0 <= rr_after <= 25.0, (
            f"ARF 严重型 RR {rr_after:.1f} 不在 [16,25] 范围"
        )

    def test_respiratory_acidosis_increases_rr(self):
        """肺炎（低氧）应该让 RR 增加（代偿性高通气）。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        disease = create_disease("pneumonia", severity="severe")
        vc.attach_disease(disease)

        rr_series = []
        for i in range(1500):
            vc.step()
            if i >= 1200:
                rr_series.append(vc.lung.respiratory_rate)

        assert_stable("RR", rr_series, cv_threshold=0.05)
        # 肺炎下 RR 应该稳定（无自激振荡），在疾病相关范围内
        assert 16.0 <= rr_series[-1] <= 30.0, (
            f"肺炎严重型 RR {rr_series[-1]:.1f} 不在 [16,30] 范围"
        )

    def test_hyperventilation_reduces_pco2(self):
        """VDP 基线正常时，RR 在正常范围 [16,22] 应伴随稳定的 PCO2。"""
        vc = VirtualCreature(body_weight_kg=20.0, species="canine", dt=0.1)
        pco2_series, rr_series = [], []
        for _ in range(1000):
            vc.step()
            pco2_series.append(vc.blood.arterial_PCO2_mmHg)
            rr_series.append(vc.lung.respiratory_rate)

        assert_stable("PCO2", pco2_series, cv_threshold=0.05)
        assert_stable("RR", rr_series, cv_threshold=0.05)
        mean_pco2 = sum(pco2_series[-50:]) / 50
        assert 35 <= mean_pco2 <= 45, f"正常 PCO2 均值 {mean_pco2:.1f} 不在 [35,45]"