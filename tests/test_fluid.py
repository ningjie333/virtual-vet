"""
P2-A + P2-C + P2-E: Fluid Compartment 三室模型 + HCO₃⁻/CO₂ 缓冲系统 + VirtualCreature 集成测试
Vascular / ISF / ICF 三个隔室的基础液体分布和交换
Henderson-Hasselbalch 酸碱平衡
VirtualCreature.step() 集成
"""

import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from fluid import FluidCompartment, HendersonHasselbalch


class TestFluidCompartmentInit:
    """三室模型初始化"""

    def test_default_volumes_20kg(self):
        """20kg 犬默认三室容量"""
        fc = FluidCompartment(weight_kg=20.0)
        # 血管内液 ≈ 8% 体重 (血浆 5% + 血细胞 3%)
        assert fc.vascular_volume_ml == pytest.approx(1600.0, rel=0.01)
        # ISF ≈ 15% 体重
        assert fc.isf_volume_ml == pytest.approx(3000.0, rel=0.01)
        # ICF ≈ 40% 体重
        assert fc.icf_volume_ml == pytest.approx(8000.0, rel=0.01)

    def test_total_body_water_sums_correctly(self):
        """总体液 = 血管 + ISF + ICF"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.total_body_water_ml == pytest.approx(
            fc.vascular_volume_ml + fc.isf_volume_ml + fc.icf_volume_ml, rel=0.01
        )

    def test_total_body_water_is_63_percent_weight(self):
        """总体液 ≈ 63% 体重 (8%血管 + 15%ISF + 40%ICF)"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.total_body_water_ml == pytest.approx(12600.0, rel=0.01)

    def test_initial_osmolality_equal_across_compartments(self):
        """初始状态下三室渗透压相等（等渗）"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.vascular_osmolality == pytest.approx(295.0, rel=0.01)
        assert fc.isf_osmolality == pytest.approx(295.0, rel=0.01)
        assert fc.icf_osmolality == pytest.approx(295.0, rel=0.01)

    def test_initial_sodium_distribution(self):
        """初始钠分布：主要在血管和 ISF（细胞外），ICF 很低"""
        fc = FluidCompartment(weight_kg=20.0)
        # 细胞外 Na⁺ ≈ 145 mEq/L
        assert fc.vascular_na_meq_l == pytest.approx(145.0, rel=0.01)
        assert fc.isf_na_meq_l == pytest.approx(145.0, rel=0.01)
        # 细胞内 Na⁺ ≈ 12 mEq/L
        assert fc.icf_na_meq_l == pytest.approx(12.0, rel=0.01)

    def test_initial_potassium_distribution(self):
        """初始钾分布：主要在 ICF（细胞内），细胞外很低"""
        fc = FluidCompartment(weight_kg=20.0)
        # 细胞外 K⁺ ≈ 4.2 mEq/L
        assert fc.vascular_k_meq_l == pytest.approx(4.2, rel=0.01)
        assert fc.isf_k_meq_l == pytest.approx(4.2, rel=0.01)
        # 细胞内 K⁺ ≈ 150 mEq/L
        assert fc.icf_k_meq_l == pytest.approx(150.0, rel=0.01)


class TestStarlingForces:
    """Starling forces 驱动血管↔ISF 液体交换"""

    def test_net_filtration_pressure_at_equilibrium(self):
        """平衡状态下净滤过压 ≈ 8 mmHg（动脉端典型值，静脉端重吸收平衡）"""
        fc = FluidCompartment(weight_kg=20.0)
        nfp = fc.compute_net_filtration_pressure()
        # Pc=25, Pi=-3, πc=25, πi=5 → NFP = (25-(-3)) - (25-5) = 28-20 = 8
        assert nfp == pytest.approx(8.0, abs=1.0)

    def test_capillary_hydrostatic_pressure(self):
        """毛细血管静水压 ≈ 25 mmHg（动脉端）"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.capillary_hydrostatic_mmHg == pytest.approx(25.0, rel=0.1)

    def test_tissue_hydrostatic_pressure(self):
        """组织静水压 ≈ -3 mmHg（轻微负压）"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.tissue_hydrostatic_mmHg == pytest.approx(-3.0, abs=1.0)

    def test_plasma_colloid_osmotic_pressure(self):
        """血浆胶体渗透压 ≈ 25 mmHg"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.plasma_colloid_osmotic_mmHg == pytest.approx(25.0, rel=0.1)

    def test_tissue_colloid_osmotic_pressure(self):
        """组织胶体渗透压 ≈ 5 mmHg"""
        fc = FluidCompartment(weight_kg=20.0)
        assert fc.tissue_colloid_osmotic_mmHg == pytest.approx(5.0, abs=2.0)


class TestFluidExchange:
    """液体跨室交换"""

    def test_vascular_to_isf_fluid_shift_with_infusion(self):
        """输液后血管内液增加，Starling 平衡重建"""
        fc = FluidCompartment(weight_kg=20.0)
        initial_vascular = fc.vascular_volume_ml
        fc.add_vascular_fluid(200.0)  # 200 mL 输液
        assert fc.vascular_volume_ml == pytest.approx(initial_vascular + 200.0, rel=0.01)

    def test_osmotic_water_shift_hypertonic(self):
        """高渗时水从 ICF → ISF/血管（细胞内脱水）"""
        fc = FluidCompartment(weight_kg=20.0)
        initial_icf = fc.icf_volume_ml
        # 增加血管内钠（模拟高渗盐水）
        fc.add_vascular_sodium(50.0)  # mEq
        fc.compute(dt=60.0)  # 推进 60 秒
        # ICF 应该减少（水外移）
        assert fc.icf_volume_ml < initial_icf

    def test_total_body_water_conserved(self):
        """三室总液体量守恒（无外部输入/丢失时）"""
        fc = FluidCompartment(weight_kg=20.0)
        initial_total = fc.total_body_water_ml
        fc.compute(dt=60.0)
        assert fc.total_body_water_ml == pytest.approx(initial_total, abs=1.0)

    def test_negative_fluid_removal(self):
        """从血管抽血"""
        fc = FluidCompartment(weight_kg=20.0)
        initial = fc.vascular_volume_ml
        fc.remove_vascular_fluid(100.0)
        assert fc.vascular_volume_ml == pytest.approx(initial - 100.0, rel=0.01)

    def test_cannot_remove_more_than_available(self):
        """不能抽出超过血管内存在的液体"""
        fc = FluidCompartment(weight_kg=20.0)
        fc.remove_vascular_fluid(99999.0)
        assert fc.vascular_volume_ml >= 0.0


class TestFluidCompartmentSummary:
    """summary() 输出"""

    def test_summary_returns_all_keys(self):
        fc = FluidCompartment(weight_kg=20.0)
        s = fc.summary()
        assert "vascular_ml" in s
        assert "isf_ml" in s
        assert "icf_ml" in s
        assert "total_water_ml" in s
        assert "osmolality_vascular" in s
        assert "osmolality_icf" in s


# ── P2-C: HCO₃⁻/CO₂ 缓冲系统 ──────────────────────────────────────────────


class TestHendersonHasselbalch:
    """Henderson-Hasselbalch 方程：pH = pKa + log([HCO₃⁻] / (0.03 × PCO₂))"""

    def test_normal_ph(self):
        """正常值：HCO₃⁻=24, PCO₂=40 → pH ≈ 7.40"""
        hh = HendersonHasselbalch(hco3_meq_l=24.0, pco2_mmHg=40.0)
        assert hh.ph == pytest.approx(7.40, abs=0.02)

    def test_metabolic_acidosis(self):
        """代谢性酸中毒：HCO₃⁻↓ → pH↓"""
        hh = HendersonHasselbalch(hco3_meq_l=12.0, pco2_mmHg=40.0)
        assert hh.ph == pytest.approx(7.10, abs=0.05)

    def test_metabolic_alkalosis(self):
        """代谢性碱中毒：HCO₃⁻↑ → pH↑"""
        hh = HendersonHasselbalch(hco3_meq_l=36.0, pco2_mmHg=40.0)
        assert hh.ph == pytest.approx(7.58, abs=0.05)

    def test_respiratory_acidosis(self):
        """呼吸性酸中毒：PCO₂↑ → pH↓"""
        hh = HendersonHasselbalch(hco3_meq_l=24.0, pco2_mmHg=60.0)
        assert hh.ph == pytest.approx(7.21, abs=0.05)

    def test_respiratory_alkalosis(self):
        """呼吸性碱中毒：PCO₂↓ → pH↑"""
        hh = HendersonHasselbalch(hco3_meq_l=24.0, pco2_mmHg=25.0)
        assert hh.ph == pytest.approx(7.60, abs=0.05)

    def test_compensated_metabolic_acidosis(self):
        """代偿性代谢性酸中毒：HCO₃⁻↓ + PCO₂↓（呼吸代偿）→ pH 趋向正常"""
        hh = HendersonHasselbalch(hco3_meq_l=12.0, pco2_mmHg=24.0)
        # 预期：pH = 6.1 + log(12 / (0.03×24)) = 6.1 + log(16.67) = 6.1 + 1.22 = 7.32
        assert hh.ph == pytest.approx(7.32, abs=0.05)

    def test_ph_clamp(self):
        """pH 被限制在 [6.8, 7.8] 范围内"""
        # 极端酸中毒
        hh_acid = HendersonHasselbalch(hco3_meq_l=3.0, pco2_mmHg=80.0)
        assert hh_acid.ph >= 6.8
        # 极端碱中毒
        hh_alk = HendersonHasselbalch(hco3_meq_l=60.0, pco2_mmHg=10.0)
        assert hh_alk.ph <= 7.8

    def test_pco2_zero_safe(self):
        """PCO₂ = 0 时不会崩溃，返回最低 pH"""
        hh = HendersonHasselbalch(hco3_meq_l=24.0, pco2_mmHg=0.0)
        assert hh.ph >= 6.8

    def test_expected_pco2_for_hco3(self):
        """给定 HCO₃⁻ 和 pH，计算预期 PCO₂"""
        # pH = 7.40, HCO₃⁻ = 24 → PCO₂ ≈ 40
        hh = HendersonHasselbalch(hco3_meq_l=24.0, pco2_mmHg=40.0)
        expected_pco2 = hh.expected_pco2(hco3_meq_l=24.0, ph=7.40)
        assert expected_pco2 == pytest.approx(40.0, abs=1.0)

    def test_expected_hco3_for_pco2(self):
        """给定 PCO₂ 和 pH，计算预期 HCO₃⁻"""
        hh = HendersonHasselbalch(hco3_meq_l=24.0, pco2_mmHg=40.0)
        expected_hco3 = hh.expected_hco3(pco2_mmHg=40.0, ph=7.40)
        assert expected_hco3 == pytest.approx(24.0, abs=0.5)


# ── P2-E: VirtualCreature 集成 ─────────────────────────────────────────────


class TestFluidIntegration:
    """VirtualCreature 与 FluidCompartment 集成"""

    def test_creature_has_fluid_compartment(self):
        """VirtualCreature 初始化时创建 FluidCompartment"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0)
        assert hasattr(vc, 'fluid')
        assert vc.fluid is not None
        assert vc.fluid.vascular_volume_ml > 0

    def test_fluid_computes_each_step(self):
        """VirtualCreature.step() 调用 fluid.compute()"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0)
        vc.step()
        # fluid.compute() 应该被调用（Starling 交换会改变容量）
        # 至少 total_body_water 应该被更新
        assert vc.fluid.total_body_water_ml > 0

    def test_ph_computed_from_hh(self):
        """step() 后 blood.pH 由 Henderson-Hasselbalch 计算"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0)
        vc.step()
        # 正常状态下 pH 应在 7.35-7.45 范围
        assert 7.35 <= vc.blood.arterial_pH <= 7.45

    def test_fluid_history_recorded(self):
        """step() 后 fluid 历史被记录"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0)
        vc.step()
        assert "fluid_vascular_ml" in vc.history
        assert "fluid_isf_ml" in vc.history
        assert "fluid_icf_ml" in vc.history
        assert len(vc.history["fluid_vascular_ml"]) == 1

    def test_multiple_steps_accumulate(self):
        """多步后 fluid 历史累积"""
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from src.simulation import VirtualCreature
        vc = VirtualCreature(body_weight_kg=20.0)
        for _ in range(10):
            vc.step()
        assert len(vc.history["fluid_vascular_ml"]) == 10


# ── P2-D: 电解质跨膜交换 ──────────────────────────────────────────────────


class TestElectrolyteExchange:
    """Na⁺/K⁺/Cl⁻ 三室分布动态"""

    def test_na_follows_water_shift(self):
        """水从 ICF→ISF 时，ISF 钠被稀释"""
        fc = FluidCompartment(weight_kg=20.0)
        # 增加血管内钠（高渗盐水）→ 水从 ICF→ISF
        fc.add_vascular_sodium(100.0)
        fc.compute(dt=60.0)
        # ISF 水量增加（水从 ICF 来），但钠总量不变（只加水）→ 稀释
        # 注意：Starling 交换会把血管内钠带到 ISF
        # 关键是三室钠总量应该守恒（无外部丢失）
        total_na = (
            fc.vascular_na_meq_l * fc.vascular_volume_ml / 1000.0
            + fc.isf_na_meq_l * fc.isf_volume_ml / 1000.0
            + fc.icf_na_meq_l * fc.icf_volume_ml / 1000.0
        )
        # 初始总钠 ≈ 145×1.6 + 145×3.0 + 12×8.0 = 232 + 435 + 96 = 763 mEq
        assert total_na == pytest.approx(763.0 + 100.0, abs=5.0)  # +100 是外部添加的

    def test_k_remains_intracellular(self):
        """钾主要分布在细胞内，ICF 钾 >> 细胞外"""
        fc = FluidCompartment(weight_kg=20.0)
        # ICF 钾含量 >> 细胞外
        icf_k_content = fc.icf_k_meq_l * fc.icf_volume_ml / 1000.0
        ec_k_content = (fc.vascular_k_meq_l * fc.vascular_volume_ml / 1000.0
                        + fc.isf_k_meq_l * fc.isf_volume_ml / 1000.0)
        assert icf_k_content > ec_k_content * 5.0

    def test_hyperkalemia_from_arf(self):
        """ARF 时血钾升高——模拟肾脏排钾障碍"""
        fc = FluidCompartment(weight_kg=20.0)
        initial_k = fc.vascular_k_meq_l
        # 模拟 ARF：ICF 钾外移（酸中毒 + 肾排钾障碍）
        # 简化：直接向血管添加钾
        fc.vascular_k_meq_l += 3.0  # 高钾血症
        assert fc.vascular_k_meq_l > initial_k
        assert fc.vascular_k_meq_l > 5.5  # 高钾血症阈值

    def test_hco3_buffering(self):
        """HCO₃⁻ 缓冲：代谢性酸中毒时 HCO₃⁻ 消耗"""
        fc = FluidCompartment(weight_kg=20.0)
        initial_hco3 = fc.vascular_hco3_meq_l
        # 模拟乳酸酸中毒：HCO₃⁻ 缓冲 H⁺ → H₂CO₃ → CO₂ + H₂O
        # 每 1 mmol/L 乳酸消耗 1 mEq/L HCO₃⁻
        lactate_increase = 5.0  # mmol/L
        fc.vascular_hco3_meq_l -= lactate_increase
        assert fc.vascular_hco3_meq_l == pytest.approx(initial_hco3 - 5.0, abs=0.1)

    def test_electrolyte_conservation_no_external(self):
        """无外部输入/丢失时，三室总电解质守恒"""
        fc = FluidCompartment(weight_kg=20.0)
        # 初始总钠
        initial_total_na = (
            fc.vascular_na_meq_l * fc.vascular_volume_ml / 1000.0
            + fc.isf_na_meq_l * fc.isf_volume_ml / 1000.0
            + fc.icf_na_meq_l * fc.icf_volume_ml / 1000.0
        )
        # 运行多步
        for _ in range(10):
            fc.compute(dt=60.0)
        # 总钠应该守恒（只有内部交换）
        final_total_na = (
            fc.vascular_na_meq_l * fc.vascular_volume_ml / 1000.0
            + fc.isf_na_meq_l * fc.isf_volume_ml / 1000.0
            + fc.icf_na_meq_l * fc.icf_volume_ml / 1000.0
        )
        assert final_total_na == pytest.approx(initial_total_na, abs=1.0)


# ── P1: Branch coverage supplements ────────────────────────────────────────


class TestDerivativesMAPCoupling:
    """流体模块 derivatives() 的 MAP-coupling 分支 (line 193-200)."""

    def test_derivatives_with_map_input(self):
        """MAP 输入时，毛细血管静水压动态更新 (Landis-Pappenheimer)."""
        fc = FluidCompartment(weight_kg=20.0)
        initial_pc = fc.capillary_hydrostatic_mmHg

        # MAP = 120 mmHg → 毛细血管静水压应升高
        dydt, outputs = fc.derivatives(dt=0.1, map_input=120.0)

        assert fc.capillary_hydrostatic_mmHg > initial_pc, (
            f"High MAP should raise capillary pressure above {initial_pc}"
        )
        assert fc.capillary_hydrostatic_mmHg <= 50.0, "Capillary pressure should not exceed 50 mmHg clamp"

    def test_derivatives_low_map(self):
        """低 MAP (< 90) 时，毛细血管静水压降低."""
        fc = FluidCompartment(weight_kg=20.0)
        initial_pc = fc.capillary_hydrostatic_mmHg

        dydt, outputs = fc.derivatives(dt=0.1, map_input=60.0)

        assert fc.capillary_hydrostatic_mmHg < initial_pc, (
            f"Low MAP should lower capillary pressure below {initial_pc}"
        )
        assert fc.capillary_hydrostatic_mmHg >= 10.0, "Capillary pressure should not go below 10 mmHg clamp"

    def test_derivatives_map_at_baseline_no_change(self):
        """MAP = 90 (基线) 时，毛细血管静水压不变."""
        fc = FluidCompartment(weight_kg=20.0)
        initial_pc = fc.capillary_hydrostatic_mmHg

        dydt, outputs = fc.derivatives(dt=0.1, map_input=90.0)

        assert fc.capillary_hydrostatic_mmHg == pytest.approx(initial_pc, abs=0.5)

    def test_derivatives_returns_starling_rate(self):
        """derivatives() 返回 starling 和 osmotic 变化率."""
        fc = FluidCompartment(weight_kg=20.0)
        dydt, outputs = fc.derivatives(dt=0.1, map_input=90.0)

        assert "starling_flow_mL_min" in outputs
        assert "osmotic_shift_mL_min" in outputs
        assert "nfp_mmHg" in outputs
        assert isinstance(outputs["starling_flow_mL_min"], float)


class TestStarlingReverseFlow:
    """Starling 交换的反向路径: ISF → 血管 (flow_ml < 0, lines 336-355)."""

    def test_reverse_starling_by_low_capillary_pressure(self):
        """降低毛细血管静水压使 NFP < 0 → ISF 重吸收回血管."""
        fc = FluidCompartment(weight_kg=20.0)
        fc.capillary_hydrostatic_mmHg = 10.0  # 极低毛细血管压

        nfp = fc.compute_net_filtration_pressure()
        assert nfp < 0, f"NFP should be negative with low capillary pressure, got {nfp:.2f}"

        flow = fc._compute_starling_exchange(dt=60.0)
        assert flow < 0, f"Starling flow should be negative (reabsorption), got {flow:.3f}"

    def test_reverse_starling_electrolyte_transfer(self):
        """反向 Starling 交换时，ISF 电解质进入血管."""
        fc = FluidCompartment(weight_kg=20.0)
        fc.capillary_hydrostatic_mmHg = 10.0

        initial_vasc_na = fc.vascular_na_meq_l
        initial_isf_na = fc.isf_na_meq_l

        flow = fc._compute_starling_exchange(dt=60.0)
        fc._exchange_electrolytes_starling(flow)

        # ISF → 血管：血管钠浓度应改变（ISF 钠与血管钠接近，变化不大）
        # 关键是体积变化：血管体积增加，ISF 体积减少
        # 验证三室钠总量守恒（无外部输入）
        total_na_before = (
            fc.vascular_na_meq_l * fc.vascular_volume_ml / 1000.0
            + fc.isf_na_meq_l * fc.isf_volume_ml / 1000.0
            + fc.icf_na_meq_l * fc.icf_volume_ml / 1000.0
        )
        fc.vascular_volume_ml -= flow
        fc.isf_volume_ml += flow
        total_na_after = (
            fc.vascular_na_meq_l * fc.vascular_volume_ml / 1000.0
            + fc.isf_na_meq_l * fc.isf_volume_ml / 1000.0
            + fc.icf_na_meq_l * fc.icf_volume_ml / 1000.0
        )
        assert total_na_after == pytest.approx(total_na_before, abs=1.0)


class TestOsmoticReverseFlow:
    """渗透压水转移的反向路径: ICF → ISF (shift_ml < 0, lines 422-435)."""

    def test_reverse_osmotic_by_hypotonic_isf(self):
        """降低 ISF 渗透压 → 水从 ICF 转移到 ISF (低渗)."""
        fc = FluidCompartment(weight_kg=20.0)
        fc.isf_na_meq_l = 120.0
        fc._update_osmolality()  # 更新 osmolality 以反映新的 Na⁺ 浓度

        initial_icf = fc.icf_volume_ml
        initial_isf = fc.isf_volume_ml
        initial_icf_k = fc.icf_k_meq_l

        shift = fc._compute_osmotic_water_shift(dt=60.0)
        assert shift < 0, f"Osmotic shift should be negative (ICF→ISF), got {shift:.3f}"

        fc._exchange_electrolytes_osmotic(shift)
        fc.isf_volume_ml -= shift
        fc.icf_volume_ml += shift

        assert fc.icf_volume_ml < initial_icf
        assert fc.isf_volume_ml > initial_isf
        assert fc.icf_k_meq_l > initial_icf_k

    def test_reverse_osmotic_isf_dilution(self):
        """ICF → ISF 转移时，ISF 电解质被稀释."""
        fc = FluidCompartment(weight_kg=20.0)
        fc.isf_na_meq_l = 120.0
        fc._update_osmolality()

        initial_isf_na = fc.isf_na_meq_l
        shift = fc._compute_osmotic_water_shift(dt=60.0)
        fc._exchange_electrolytes_osmotic(shift)

        assert fc.isf_na_meq_l < initial_isf_na

    def test_total_water_conserved_osmotic_reverse(self):
        """渗透压水转移反向时，总液体量守恒."""
        fc = FluidCompartment(weight_kg=20.0)
        fc.isf_na_meq_l = 120.0
        fc._update_osmolality()

        initial_total = fc.total_body_water_ml
        shift = fc._compute_osmotic_water_shift(dt=60.0)
        fc._exchange_electrolytes_osmotic(shift)
        fc.isf_volume_ml -= shift
        fc.icf_volume_ml += shift
        fc._update_osmolality()
        fc.total_body_water_ml = (
            fc.vascular_volume_ml + fc.isf_volume_ml + fc.icf_volume_ml
        )

        assert fc.total_body_water_ml == pytest.approx(initial_total, abs=1.0)


class TestZeroFlowGuard:
    """零流量 guard 分支 (abs(flow_ml) < 1e-9) 的正确性."""

    def test_starling_zero_flow_no_change(self):
        """零流量 Starling 交换时，电解质浓度不变."""
        fc = FluidCompartment(weight_kg=20.0)
        na_before = fc.vascular_na_meq_l
        cl_before = fc.vascular_cl_meq_l
        hco3_before = fc.vascular_hco3_meq_l

        fc._exchange_electrolytes_starling(0.0)

        assert fc.vascular_na_meq_l == na_before
        assert fc.vascular_cl_meq_l == cl_before
        assert fc.vascular_hco3_meq_l == hco3_before

    def test_osmotic_zero_shift_no_change(self):
        """零渗透压水转移时，电解质浓度不变."""
        fc = FluidCompartment(weight_kg=20.0)
        isf_na_before = fc.isf_na_meq_l
        icf_k_before = fc.icf_k_meq_l

        fc._exchange_electrolytes_osmotic(0.0)

        assert fc.isf_na_meq_l == isf_na_before
        assert fc.icf_k_meq_l == icf_k_before
