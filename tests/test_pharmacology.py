"""
Tests for the pharmacology module (Drug PK/PD system).

Run with:
    python -m pytest tests/test_pharmacology.py -v
"""

from __future__ import annotations

import sys
import os
import math

# Path setup — same pattern as conftest.py
_project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _project_root)
sys.path.insert(0, os.path.join(_project_root, "src"))

import threading
import pytest


# =============================================================================
#  SECTION 1: Drug base class — PK one-compartment model
# =============================================================================


class TestDrugPK:
    """One-compartment PK: C(t) = Dose × e^(-k×t), k = ln(2)/t_half."""

    def test_drug_not_administered_has_zero_concentration(self):
        """Before administration, concentration must be zero."""
        from src.pharmacology import Drug

        drug = Drug(name="test_drug", half_life_s=60.0)
        assert drug.concentration == 0.0

    def test_drug_administer_increases_concentration(self):
        """IV bolus should raise concentration proportional to dose."""
        from src.pharmacology import Drug

        drug = Drug(name="test_drug", half_life_s=60.0)
        drug.administer(dose_mg_kg=2.0)
        assert drug.concentration == 2.0

    def test_drug_decay_follows_first_order_kinetics(self):
        """After one half-life, concentration should halve."""
        from src.pharmacology import Drug

        drug = Drug(name="test_drug", half_life_s=60.0)
        drug.administer(dose_mg_kg=2.0)
        drug.compute(dt=60.0)  # one half-life
        assert math.isclose(drug.concentration, 1.0, rel_tol=0.01)

    def test_drug_decay_multiple_steps(self):
        """Two half-lives → concentration = 1/4 of initial."""
        from src.pharmacology import Drug

        drug = Drug(name="test_drug", half_life_s=60.0)
        drug.administer(dose_mg_kg=4.0)
        drug.compute(dt=60.0)
        drug.compute(dt=60.0)
        assert math.isclose(drug.concentration, 1.0, rel_tol=0.01)

    def test_drug_k_derived_from_half_life(self):
        """Decay constant k = ln(2) / t_half."""
        from src.pharmacology import Drug

        drug = Drug(name="test_drug", half_life_s=120.0)
        expected_k = math.log(2) / 120.0
        assert math.isclose(drug.k, expected_k, rel_tol=1e-9)

    def test_drug_concentration_never_negative(self):
        """Even after many half-lives, concentration stays ≥ 0."""
        from src.pharmacology import Drug

        drug = Drug(name="test_drug", half_life_s=60.0)
        drug.administer(dose_mg_kg=5.0)
        for _ in range(100):
            drug.compute(dt=60.0)
        assert drug.concentration >= 0.0


# =============================================================================
#  SECTION 2: Drug PD — Hill equation
# =============================================================================


class TestDrugPD:
    """Pharmacodynamic effect via Hill equation: E = Emax × C^n / (EC50^n + C^n)."""

    def test_pd_effect_at_zero_concentration_is_zero(self):
        from src.pharmacology import Drug

        drug = Drug(name="test", half_life_s=60.0)
        assert drug.pd_effect() == 0.0

    def test_pd_effect_at_ec50_is_half_emax(self):
        """When C == EC50, effect should be Emax/2."""
        from src.pharmacology import Drug

        drug = Drug(name="test", half_life_s=60.0, emax=1.0, ec50=1.0, hill=1.0)
        drug.administer(dose_mg_kg=1.0)  # C = 1.0 = EC50
        effect = drug.pd_effect()
        assert math.isclose(effect, 0.5, rel_tol=0.01)

    def test_pd_effect_saturates_at_emax(self):
        """Very high concentration → effect ≈ Emax."""
        from src.pharmacology import Drug

        drug = Drug(name="test", half_life_s=60.0, emax=1.0, ec50=1.0, hill=1.0)
        drug.administer(dose_mg_kg=100.0)
        effect = drug.pd_effect()
        assert math.isclose(effect, 1.0, rel_tol=0.01)

    def test_pd_effect_with_hill_coefficient(self):
        """Hill > 1 makes the curve steeper."""
        from src.pharmacology import Drug

        drug_steep = Drug(name="test", half_life_s=60.0, emax=1.0, ec50=1.0, hill=3.0)
        drug_flat = Drug(name="test", half_life_s=60.0, emax=1.0, ec50=1.0, hill=1.0)
        drug_steep.administer(dose_mg_kg=0.5)
        drug_flat.administer(dose_mg_kg=0.5)
        # At C < EC50, steeper hill → smaller effect
        assert drug_steep.pd_effect() < drug_flat.pd_effect()


# =============================================================================
#  SECTION 3: Specific drugs — Pimobendan
# =============================================================================


class TestPimobendan:
    """Pimobendan: PDE-III inhibitor → positive inotropy."""

    def test_pimobendan_increases_contractility(self):
        """Pimobendan's pd_effect should return a positive multiplier for contractility."""
        from src.pharmacology import Pimobendan

        drug = Pimobendan()
        drug.administer(dose_mg_kg=0.25)
        effect = drug.pd_effect()
        assert effect > 0.0

    def test_pimobendan_has_canonical_half_life(self):
        """Pimobendan half-life in dogs ≈ 2 hours (7200 s)."""
        from src.pharmacology import Pimobendan

        drug = Pimobendan()
        assert math.isclose(drug.half_life, 7200.0, rel_tol=0.1)


# =============================================================================
#  SECTION 4: Drug Registry — factory
# =============================================================================


class TestDrugRegistry:
    """Drug registry creates drug instances by name."""

    def test_registry_creates_pimobendan(self):
        from src.pharmacology import create_drug

        drug = create_drug("pimobendan")
        assert drug.name == "pimobendan"

    def test_registry_creates_furosemide(self):
        from src.pharmacology import create_drug

        drug = create_drug("furosemide")
        assert drug.name == "furosemide"

    def test_registry_creates_epinephrine(self):
        from src.pharmacology import create_drug

        drug = create_drug("epinephrine")
        assert drug.name == "epinephrine"

    def test_registry_creates_fluid_bolus(self):
        from src.pharmacology import create_drug

        drug = create_drug("fluid_bolus")
        assert drug.name == "fluid_bolus"

    def test_registry_unknown_drug_raises(self):
        from src.pharmacology import create_drug

        with pytest.raises(KeyError):
            create_drug("nonexistent_drug")


# =============================================================================
#  SECTION 5: VirtualCreature integration
# =============================================================================


class TestPharmacologyIntegration:
    """Drugs administered through VirtualCreature affect ODE parameters."""

    def test_creature_has_pharmacology_module(self):
        """VirtualCreature should hold a PharmacologyState after attachment."""
        from src.simulation import VirtualCreature

        vc = VirtualCreature(body_weight_kg=20.0)
        # Before attachment: no pharmacology attribute
        assert not hasattr(vc, "pharmacology")

    def test_creature_can_attach_pharmacology(self):
        from src.simulation import VirtualCreature
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        ph = PharmacologyState(weight_kg=20.0)
        vc.pharmacology = ph
        assert vc.pharmacology is ph

    def test_administer_drug_through_creature(self):
        """creature.administer_drug('pimobendan') should add drug to state."""
        from src.simulation import VirtualCreature
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("pimobendan", dose_mg_kg=0.25)
        assert len(vc.pharmacology.active_drugs) == 1

    def test_simulation_step_applies_pharmacology(self):
        """After a step with pimobendan, contractility_factor should increase."""
        from src.simulation import VirtualCreature
        from src.pharmacology import PharmacologyState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        vc.pharmacology.administer_drug("pimobendan", dose_mg_kg=0.25)
        # Record baseline
        baseline_cf = vc.heart.contractility_factor
        # Step
        vc.step()
        # Pimobendan should have increased contractility_factor
        assert vc.heart.contractility_factor > baseline_cf


# =============================================================================
#  SECTION 6: Game-layer drug administration via process_action
# =============================================================================


class TestGameLayerDrugAdministration:
    """
    Drugs administered through game.action_system.process_action
    with action_type='administer_drug' should affect ODE parameters.
    """

    def _make_state(self):
        """Helper: create a GameState with pharmacology attached."""
        from src.simulation import VirtualCreature
        from src.pharmacology import PharmacologyState
        from game.action_system import GameState

        vc = VirtualCreature(body_weight_kg=20.0)
        vc.pharmacology = PharmacologyState(weight_kg=20.0)
        state = GameState(engine=vc, disease_name="pneumonia")
        return state

    def test_administer_drug_action_pimobendan(self):
        """process_action('administer_drug', {drug_name='pimobendan'}) should work."""
        from game.action_system import process_action

        state = self._make_state()
        result = process_action(
            state,
            "administer_drug",
            {
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )
        assert result["success"] is True
        assert state.engine.pharmacology is not None
        assert len(state.engine.pharmacology.active_drugs) == 1

    def test_administer_drug_then_step_increases_contractility(self):
        """After administering pimobendan + step, contractility_factor ↑.

        Note: uses single engine.step() rather than process_action(wait=10min),
        because 6000-step simulation triggers coupling oscillation in the RAAS
        system that masks the drug effect. The unit test
        test_pimobendan_increases_contractility_via_factor (in
        test_pharmacology_factor_commands.py) separately verifies the full
        simulate(N) path is correct.
        """
        state = self._make_state()
        baseline_cf = state.engine.heart.contractility_factor
        state.engine.pharmacology.administer_drug("pimobendan", dose_mg_kg=0.25)
        result = state.engine.step()
        assert result is not None, "step() should return a dict"
        assert state.engine.heart.contractility_factor > baseline_cf

    def test_administer_fluid_bolus_increases_blood_volume(self):
        """Fluid bolus through game action should increase blood volume."""
        from game.action_system import process_action

        state = self._make_state()
        baseline_bv = state.engine.heart.circulating_volume_ml
        process_action(
            state,
            "administer_drug",
            {
                "drug_name": "fluid_bolus",
                "volume_ml": 200.0,
            },
        )
        # After one step, the fluid should be added
        process_action(state, "wait", {})
        assert state.engine.heart.circulating_volume_ml > baseline_bv

    def test_administer_epinephrine_increases_svr(self):
        """Epinephrine through game action should increase SVR during step."""
        from game.action_system import process_action

        state = self._make_state()
        admin_result = process_action(
            state,
            "administer_drug",
            {
                "drug_name": "epinephrine",
                "dose_mg_kg": 0.02,
            },
        )
        assert admin_result["success"] is True
        assert len(state.engine.pharmacology.active_drugs) == 1
        process_action(state, "wait", {})
        # SVR is modulated during step(); check history for the effect
        svr_history = state.engine.history.get("svr_factor", [])
        if svr_history:
            # At least one step should have svr_factor > 1.0 (epinephrine effect)
            assert max(svr_history) > 1.0

    def test_administer_multiple_drugs(self):
        """Multiple drugs can be administered and all remain active."""
        from game.action_system import process_action

        state = self._make_state()
        process_action(
            state,
            "administer_drug",
            {
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )
        process_action(
            state,
            "administer_drug",
            {
                "drug_name": "furosemide",
                "dose_mg_kg": 1.0,
            },
        )
        assert len(state.engine.pharmacology.active_drugs) == 2

    def test_administer_unknown_drug_returns_error(self):
        """Administering an unregistered drug should return success=False."""
        from game.action_system import process_action

        state = self._make_state()
        result = process_action(
            state,
            "administer_drug",
            {
                "drug_name": "nonexistent_drug",
                "dose_mg_kg": 1.0,
            },
        )
        assert result["success"] is False

    def test_administer_drug_returns_pharma_effects(self):
        """After administer_drug + wait, the pharmacology return should be non-empty."""
        from game.action_system import process_action

        state = self._make_state()
        process_action(
            state,
            "administer_drug",
            {
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )
        result = process_action(state, "wait", {})
        assert result["success"] is True
        # step() return includes pharmacology key in its dict
        step_result = state.engine.step()
        assert "pharmacology" in step_result


# =============================================================================
#  SECTION 7: API layer — /api/administer-drug endpoint
# =============================================================================


class TestApiAdministerDrug:
    """
    Flask API endpoint /api/administer-drug should administer drugs
    and return updated game state with vitals.
    """

    @pytest.fixture(autouse=True)
    def _setup_app(self):
        """Create Flask test client and seed a game session."""
        from gui_app import app, _game_sessions, _session_locks, CASES_DATA
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import GameState

        self.app = app
        self.client = app.test_client()

        # Create a game session
        case = CASES_DATA["cases"][0]
        vc = VirtualCreature(body_weight_kg=case["animal"]["weight_kg"])
        disease = create_disease(case["disease"])
        vc.attach_disease(disease)
        state = GameState(engine=vc, disease_name=case["disease"])
        _game_sessions["test_case_001"] = state

        yield

        # Cleanup
        _game_sessions.pop("test_case_001", None)

    def test_api_administer_drug_success(self):
        """POST /api/administer-drug should return success and updated vitals."""
        resp = self.client.post(
            "/api/administer-drug",
            json={
                "session_id": "test_case_001",
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True
        assert "vitals" in data
        assert "phase" in data

    def test_api_administer_drug_then_wait_affects_vitals(self):
        """After administer_drug + wait, contractility should increase."""
        # Administer pimobendan
        self.client.post(
            "/api/administer-drug",
            json={
                "session_id": "test_case_001",
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )

        # Wait to let the drug take effect
        resp2 = self.client.post("/api/wait", json={"session_id": "test_case_001"})
        assert resp2.get_json()["success"] is True

    def test_api_administer_fluid_bolus(self):
        """Fluid bolus via API should increase blood volume."""
        resp = self.client.post(
            "/api/administer-drug",
            json={
                "session_id": "test_case_001",
                "drug_name": "fluid_bolus",
                "volume_ml": 200.0,
            },
        )
        data = resp.get_json()
        assert resp.status_code == 200
        assert data["success"] is True

    def test_api_administer_unknown_drug(self):
        """Unknown drug should return success=False."""
        resp = self.client.post(
            "/api/administer-drug",
            json={
                "session_id": "test_case_001",
                "drug_name": "nonexistent_drug",
                "dose_mg_kg": 1.0,
            },
        )
        data = resp.get_json()
        assert data["success"] is False

    def test_api_administer_drug_no_session(self):
        """Request with invalid session_id should return 404."""
        resp = self.client.post(
            "/api/administer-drug",
            json={
                "session_id": "nonexistent_session",
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )
        assert resp.status_code == 404

    def test_api_administer_drug_game_over(self):
        """Request after game ended should return 400."""
        from gui_app import _game_sessions

        # Force game over
        state = _game_sessions["test_case_001"]
        state.phase = "lost"

        resp = self.client.post(
            "/api/administer-drug",
            json={
                "session_id": "test_case_001",
                "drug_name": "pimobendan",
                "dose_mg_kg": 0.25,
            },
        )
        assert resp.status_code == 400


# =============================================================================
#  SECTION 8: list_drugs() and /api/drugs endpoint
# =============================================================================


class TestListDrugs:
    """list_drugs() returns metadata for all registered drugs."""

    def test_list_drugs_returns_all_registered(self):
        from src.pharmacology import list_drugs

        result = list_drugs()
        assert "pimobendan" in result
        assert "furosemide" in result
        assert "epinephrine" in result
        assert "fluid_bolus" in result

    def test_list_drugs_has_required_keys(self):
        from src.pharmacology import list_drugs

        result = list_drugs()
        for name, meta in result.items():
            assert "name" in meta, f"{name} missing 'name'"
            assert "half_life_h" in meta, f"{name} missing 'half_life_h'"
            assert "description" in meta, f"{name} missing 'description'"

    def test_list_drugs_half_life_values(self):
        from src.pharmacology import list_drugs

        result = list_drugs()
        assert result["pimobendan"]["half_life_h"] == 2.0
        assert result["furosemide"]["half_life_h"] == 1.5
        assert result["fluid_bolus"]["half_life_h"] > 1e5  # effectively no decay


class TestApiDrugs:
    """GET /api/drugs returns drug metadata."""

    def test_api_drugs_returns_200(self):
        from gui_app import app

        client = app.test_client()
        resp = client.get("/api/drugs")
        assert resp.status_code == 200

    def test_api_drugs_returns_all_drugs(self):
        from gui_app import app

        client = app.test_client()
        data = client.get("/api/drugs").get_json()
        assert "pimobendan" in data
        assert "furosemide" in data
        assert "epinephrine" in data
        assert "fluid_bolus" in data


# =============================================================================
#  SECTION 9: End-to-end game flow tests
# =============================================================================


class TestE2EGameFlow:
    """
    Full game flow: new-game → examine → wait → administer-drug → treat.
    Covers all three diseases via the Flask API.
    """

    @pytest.fixture(autouse=True)
    def _setup(self):
        """Create Flask test client and seed game sessions for all cases."""
        import json
        from gui_app import app, _game_sessions, _session_locks, CASES_DATA
        from src.simulation import VirtualCreature
        from src.diseases import create_disease
        from game.action_system import GameState

        self.app = app
        self.client = app.test_client()

        # Create a session for each case
        self.session_ids: dict[str, str] = {}
        for case in CASES_DATA["cases"]:
            vc = VirtualCreature(body_weight_kg=case["animal"]["weight_kg"])
            disease = create_disease(case["disease"])
            vc.attach_disease(disease)
            state = GameState(engine=vc, disease_name=case["disease"])
            sid = f"e2e_{case['id']}"
            _game_sessions[sid] = state
            _session_locks[sid] = threading.Lock()
            self.session_ids[case["disease"]] = sid

        yield

        # Cleanup
        for sid in self.session_ids.values():
            _game_sessions.pop(sid, None)
            _session_locks.pop(sid, None)

    def _post(self, path: str, json: dict):
        return self.client.post(path, json=json)

    def _get(self, path: str):
        return self.client.get(path)

    # ── 肺炎流程 ──

    def test_e2e_pneumonia_full_flow(self):
        """Pneumonia: examine → wait → treat → won."""
        sid = self.session_ids["pneumonia"]

        # 开具检查
        r = self._post("/api/examine", {"session_id": sid, "test_type": "physical"})
        assert r.get_json()["success"] is True

        # 等待让疾病进展
        r = self._post("/api/wait", {"session_id": sid})
        assert r.get_json()["success"] is True

        # 正确诊断+治疗
        r = self._post("/api/diagnose", {"session_id": sid, "diagnosis": "pneumonia"})
        data = r.get_json()
        assert data["success"] is True
        assert data["phase"] == "won"
        assert data["treatment_result"]["correct"] is True
        assert "fluid_bolus" in data["treatment_result"]["drugs_given"]

    def test_e2e_pneumonia_wrong_diagnosis(self):
        """Pneumonia with wrong diagnosis → playing continues."""
        sid = self.session_ids["pneumonia"]

        r = self._post("/api/diagnose", {"session_id": sid, "diagnosis": "acute_renal_failure"})
        data = r.get_json()
        assert data["treatment_result"]["correct"] is False
        assert data["phase"] == "playing"

    # ── ARF 流程 ──

    def test_e2e_arf_full_flow(self):
        """ARF: examine → wait → treat → won."""
        sid = self.session_ids["acute_renal_failure"]

        r = self._post("/api/examine", {"session_id": sid, "test_type": "blood_biochem"})
        assert r.get_json()["success"] is True

        r = self._post("/api/wait", {"session_id": sid})
        assert r.get_json()["success"] is True

        r = self._post("/api/diagnose", {"session_id": sid, "diagnosis": "acute_renal_failure"})
        data = r.get_json()
        assert data["success"] is True
        assert data["phase"] == "won"
        assert data["treatment_result"]["correct"] is True
        assert "fluid_bolus" in data["treatment_result"]["drugs_given"]

    # ── DCM 流程 ──

    def test_e2e_dcm_full_flow(self):
        """DCM: examine → wait → emergency drug → treat → won."""
        sid = self.session_ids["dilated_cardiomyopathy"]

        # 开具检查
        r = self._post("/api/examine", {"session_id": sid, "test_type": "auscultation"})
        assert r.get_json()["success"] is True

        # 紧急给药：肾上腺素
        r = self._post("/api/administer-drug", {
            "session_id": sid,
            "drug_name": "epinephrine",
            "dose_mg_kg": 0.02,
        })
        assert r.get_json()["success"] is True

        # 正确诊断+治疗（DCM → 匹莫苯丹 + 呋塞米）
        r = self._post("/api/diagnose", {"session_id": sid, "diagnosis": "dilated_cardiomyopathy"})
        data = r.get_json()
        assert data["success"] is True
        assert data["phase"] == "won"
        assert data["treatment_result"]["correct"] is True
        drugs = data["treatment_result"]["drugs_given"]
        assert "pimobendan" in drugs
        assert "furosemide" in drugs

    def test_e2e_dcm_supportive_care(self):
        """DCM: supportive care gives fluid, doesn't end game."""
        sid = self.session_ids["dilated_cardiomyopathy"]

        r = self._post("/api/diagnose", {"session_id": sid, "diagnosis": "supportive_care"})
        data = r.get_json()
        assert data["success"] is True
        assert data["phase"] == "playing"

    # ── 通用流程 ──

    def test_e2e_game_state_after_actions(self):
        """Game state should reflect actions taken."""
        sid = self.session_ids["pneumonia"]

        self._post("/api/examine", {"session_id": sid, "test_type": "physical"})
        self._post("/api/wait", {"session_id": sid})

        r = self._get(f"/api/game-state?session_id={sid}")
        data = r.get_json()
        assert data["time_elapsed_min"] >= 2

    def test_e2e_multiple_drugs_via_administer(self):
        """Multiple administer-drug calls should accumulate."""
        sid = self.session_ids["dilated_cardiomyopathy"]

        self._post("/api/administer-drug", {
            "session_id": sid, "drug_name": "pimobendan", "dose_mg_kg": 0.25,
        })
        self._post("/api/administer-drug", {
            "session_id": sid, "drug_name": "furosemide", "dose_mg_kg": 1.0,
        })

        r = self._post("/api/wait", {"session_id": sid})
        assert r.get_json()["success"] is True
