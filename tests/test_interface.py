"""
Interface Layer Tests — Flask Web GUI + CLI Daemon.

Covers:
- Flask page routes and API endpoints via test_client
- Session persistence across requests
- JSON content-type verification
- Error handling for invalid / malformed input
- CLI argument parsing and command structure

Run with:
    cd /path/to/project && python -m pytest tests/test_interface.py -v
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

# ── Path setup ──
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
_SRC = os.path.join(PROJECT_ROOT, "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

DATA_DIR = os.path.join(PROJECT_ROOT, "data")


# ─────────────────────────────────────────────────────────────
#  SECTION 1: Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def app():
    """Create Flask app with test config. Session-scoped: initialized once."""
    import gui_app as gui
    gui.app.config["TESTING"] = True
    gui._game_sessions.clear()

    from src.db.conn import connect
    from src.db.schema import init_db

    test_db_path = os.path.join(PROJECT_ROOT, "data", "game_sessions_test.db")
    if hasattr(gui, '_db_conn') and gui._db_conn is not None:
        try:
            gui._db_conn.close()
        except Exception:
            pass
    gui._db_conn = connect(test_db_path)
    init_db(gui._db_conn)

    try:
        gui._db_conn.execute("DELETE FROM action_log")
        gui._db_conn.execute("DELETE FROM sessions")
        gui._db_conn.commit()
    except Exception:
        pass
    return gui.app


@pytest.fixture(scope="session")
def client(app):
    """Flask test client. Session-scoped: one client for all tests."""
    return app.test_client()


@pytest.fixture(autouse=True)
def clean_sessions():
    """Ensure each test starts with clean game sessions and DB."""
    import gui_app as gui
    gui._game_sessions.clear()
    # Also clear the session DB so repeat test runs don't get UNIQUE violations
    # Use a timeout to avoid database locked errors
    try:
        import gui_app as _gui
        if hasattr(_gui, '_db_conn') and _gui._db_conn is not None:
            _gui._db_conn.execute("PRAGMA busy_timeout = 5000")
            _gui._db_conn.execute("DELETE FROM action_log")
            _gui._db_conn.execute("DELETE FROM sessions")
            _gui._db_conn.commit()
    except Exception:
        pass
    yield
    try:
        import gui_app as _gui
        if hasattr(_gui, '_db_conn') and _gui._db_conn is not None:
            _gui._db_conn.execute("PRAGMA busy_timeout = 5000")
            _gui._db_conn.execute("DELETE FROM action_log")
            _gui._db_conn.execute("DELETE FROM sessions")
            _gui._db_conn.commit()
    except Exception:
        pass


def _start_game(client, case_id="case_001"):
    """Helper: POST /api/new-game and return the JSON response."""
    resp = client.post(
        "/api/new-game",
        data=json.dumps({"case_id": case_id}),
        content_type="application/json",
    )
    return json.loads(resp.data)


# ─────────────────────────────────────────────────────────────
#  SECTION 2: Flask Page Route Tests
# ─────────────────────────────────────────────────────────────

class TestPageRoutes:

    def test_index_route_exists(self, client):
        """GET / should return 200."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_returns_html(self, client):
        """GET / should return HTML content."""
        resp = client.get("/")
        assert "text/html" in resp.content_type


# ─────────────────────────────────────────────────────────────
#  SECTION 3: API Static / Data Endpoints
# ─────────────────────────────────────────────────────────────

class TestStaticApiEndpoints:

    def test_api_cases(self, client):
        """GET /api/cases should return list of cases."""
        resp = client.get("/api/cases")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        # The endpoint wraps cases in {"cases": [...]} via jsonify(CASES_DATA["cases"])
        # Actually jsonify on a plain list returns the list directly
        if isinstance(data, dict):
            assert "cases" in data
            cases_list = data["cases"]
        else:
            cases_list = data
        assert isinstance(cases_list, list)
        assert len(cases_list) > 0

    def test_api_examinations(self, client):
        """GET /api/examinations should return exam definitions."""
        resp = client.get("/api/examinations")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "physical" in data

    def test_api_treatments(self, client):
        """GET /api/treatments should return treatment definitions."""
        resp = client.get("/api/treatments")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data) > 0


# ─────────────────────────────────────────────────────────────
#  SECTION 4: New Game Endpoint
# ─────────────────────────────────────────────────────────────

class TestNewGame:

    def test_api_new_game(self, client):
        """POST /api/new-game should initialize a game session."""
        data = _start_game(client)
        assert "session_id" in data
        assert "case" in data
        assert "game_state" in data
        assert "vitals" in data

    def test_api_new_game_default_case(self, client):
        """POST /api/new-game with no body should default to case_001."""
        resp = client.post(
            "/api/new-game",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["session_id"] == "case_001"

    def test_api_new_game_case_002(self, client):
        """POST /api/new-game with case_002 should work."""
        data = _start_game(client, case_id="case_002")
        assert data["session_id"] == "case_002"
        assert data["case"]["id"] == "case_002"

    def test_api_new_game_unknown_case(self, client):
        """POST /api/new-game with unknown case_id should return 404."""
        resp = client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "nonexistent"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert "error" in data

    def test_api_new_game_vitals_present(self, client):
        """POST /api/new-game should return vital signs."""
        data = _start_game(client)
        vitals = data["vitals"]
        assert "HR_bpm" in vitals
        assert "MAP_mmHg" in vitals
        assert "SpO2" in vitals
        assert "GFR" in vitals
        assert "pH" in vitals

    def test_api_new_game_game_state_fields(self, client):
        """POST /api/new-game should return all required game_state fields."""
        data = _start_game(client)
        gs = data["game_state"]
        assert "phase" in gs
        assert "time_elapsed_min" in gs
        assert "medical_phase" in gs
        assert "death_timer" in gs


# ─────────────────────────────────────────────────────────────
#  SECTION 5: Examine Endpoint
# ─────────────────────────────────────────────────────────────

class TestExamine:

    def test_api_examine_valid(self, client):
        """POST /api/examine with valid test_type should return success."""
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert data["report"] is not None
        assert data["report"]["test_type"] == "physical"
        assert "vitals" in data
        assert "phase" in data

    def test_api_examine_default_test_type(self, client):
        """POST /api/examine with no test_type should default to 'physical'."""
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert data["report"]["test_type"] == "physical"

    def test_api_examine_invalid_session(self, client):
        """POST /api/examine with unknown session should return 404."""
        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "nosuch", "test_type": "physical"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_api_examine_multiple_tests_accumulate(self, client):
        """Multiple different examine calls should accumulate reports."""
        _start_game(client)
        for tt in ("physical", "blood_gas", "auscultation"):
            resp = client.post(
                "/api/examine",
                data=json.dumps({"session_id": "case_001", "test_type": tt}),
                content_type="application/json",
            )
            data = json.loads(resp.data)
            assert data["success"] is True

        state_resp = client.get("/api/game-state?session_id=case_001")
        state_data = json.loads(state_resp.data)
        assert state_data["reports_count"] == 3

    def test_api_examine_increments_time_elapsed_min(self, client):
        """Each examine call should increment time_elapsed_min."""
        _start_game(client)
        resp1 = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        assert json.loads(resp1.data)["time_elapsed_min"] == 5

        resp2 = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "blood_gas"}),
            content_type="application/json",
        )
        # blood_gas has time_cost_min=5, so time_elapsed_min goes from 1 → 4
        assert json.loads(resp2.data)["time_elapsed_min"] == 10

    def test_api_examine_returns_game_log(self, client):
        """POST /api/examine should return game_log field."""
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        assert "game_log" in data
        assert isinstance(data["game_log"], list)


# ─────────────────────────────────────────────────────────────
#  SECTION 6: Diagnose Endpoint
# ─────────────────────────────────────────────────────────────

class TestDiagnose:

    def test_api_diagnose_valid(self, client):
        """POST /api/diagnose with valid diagnosis should return success."""
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": "pneumonia"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert data["phase"] == "won"

    def test_api_diagnose_correct_sets_won(self, client):
        """Correct diagnosis should set phase to 'won'."""
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": "pneumonia"}),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        assert data["phase"] == "won"
        assert "game_over" in data
        assert "score" in data["game_over"]

    def test_api_diagnose_wrong_stays_playing(self, client):
        """Incorrect diagnosis should keep phase as 'playing'."""
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": "acute_renal_failure"}),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        assert data["phase"] == "playing"
        assert data["treatment_result"]["correct"] is False

    def test_api_diagnose_invalid_session(self, client):
        """POST /api/diagnose without valid session should return 404."""
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "nosuch", "diagnosis": "pneumonia"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_api_diagnose_empty_diagnosis(self, client):
        """POST /api/diagnose with empty diagnosis string should not 500."""
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": ""}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_api_diagnose_game_over_structure(self, client):
        """Winning diagnosis should include game_over with reason and score."""
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": "pneumonia"}),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        go = data["game_over"]
        assert "reason" in go
        assert "actual_disease" in go
        score = go["score"]
        assert "total" in score
        assert "grade" in score
        assert 20 <= score["total"] <= 100
        assert score["grade"] in ("S", "A", "B", "C", "D")


# ─────────────────────────────────────────────────────────────
#  SECTION 7: Wait Endpoint
# ─────────────────────────────────────────────────────────────

class TestWait:

    def test_api_wait_valid(self, client):
        """POST /api/wait should succeed with valid session."""
        _start_game(client)
        resp = client.post(
            "/api/wait",
            data=json.dumps({"session_id": "case_001"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["success"] is True
        assert data["time_elapsed_min"] == 10

    def test_api_wait_invalid_session(self, client):
        """POST /api/wait with unknown session should return 404."""
        resp = client.post(
            "/api/wait",
            data=json.dumps({"session_id": "nosuch"}),
            content_type="application/json",
        )
        assert resp.status_code == 404

    def test_api_wait_advances_time(self, client):
        """Wait should advance time_elapsed_min."""
        _start_game(client)
        resp = client.post(
            "/api/wait",
            data=json.dumps({"session_id": "case_001"}),
            content_type="application/json",
        )
        data = json.loads(resp.data)
        assert data["time_elapsed_min"] > 0


# ─────────────────────────────────────────────────────────────
#  SECTION 8: Game State Endpoint
# ─────────────────────────────────────────────────────────────

class TestGameState:

    def test_api_game_state_valid(self, client):
        """GET /api/game-state with valid session should return current state."""
        _start_game(client)
        resp = client.get("/api/game-state?session_id=case_001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "phase" in data
        assert "medical_phase" in data
        assert "vitals" in data
        assert "time_elapsed_min" in data

    def test_api_game_state_invalid_session(self, client):
        """GET /api/game-state with unknown session should return 404."""
        resp = client.get("/api/game-state?session_id=nosuch")
        assert resp.status_code == 404

    def test_api_game_state_default_session(self, client):
        """GET /api/game-state with no param should default to case_001."""
        _start_game(client)
        resp = client.get("/api/game-state")
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────
#  SECTION 9: Hint Endpoint
# ─────────────────────────────────────────────────────────────

class TestHint:

    def test_api_hint_no_reports(self, client):
        """GET /api/hint with no reports should give prompt to examine first."""
        _start_game(client)
        resp = client.get("/api/hint?session_id=case_001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "hint" in data

    def test_api_hint_with_reports(self, client):
        """GET /api/hint after examinations should give disease-matching hints."""
        _start_game(client)
        for tt in ("physical", "blood_gas", "auscultation", "chest_xray"):
            client.post(
                "/api/examine",
                data=json.dumps({"session_id": "case_001", "test_type": tt}),
                content_type="application/json",
            )
        resp = client.get("/api/hint?session_id=case_001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "hint" in data
        assert "置信度" in data["hint"] or "肺炎" in data["hint"]

    def test_api_hint_invalid_session(self, client):
        """GET /api/hint with unknown session should return 404."""
        resp = client.get("/api/hint?session_id=nosuch")
        assert resp.status_code == 404

    def test_api_diagnosis_returns_matches(self, client):
        """GET /api/diagnosis should return structured match data with confidence."""
        _start_game(client)
        for tt in ("physical", "blood_gas", "auscultation", "chest_xray"):
            client.post(
                "/api/examine",
                data=json.dumps({"session_id": "case_001", "test_type": tt}),
                content_type="application/json",
            )
        resp = client.get("/api/diagnosis?session_id=case_001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "matches" in data
        assert isinstance(data["matches"], list)
        assert len(data["matches"]) > 0
        top = data["matches"][0]
        assert "disease" in top
        assert "confidence" in top
        assert "matched_clues" in top
        assert "missed_clues" in top
        # matches should be sorted by confidence descending
        for i in range(len(data["matches"]) - 1):
            assert data["matches"][i]["confidence"] >= data["matches"][i + 1]["confidence"]

    def test_api_diagnosis_empty_reports(self, client):
        """GET /api/diagnosis with no reports should return zero-confidence matches."""
        _start_game(client)
        resp = client.get("/api/diagnosis?session_id=case_001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "matches" in data
        for m in data["matches"]:
            assert m["confidence"] == 0.0

    def test_api_diagnosis_invalid_session(self, client):
        """GET /api/diagnosis with unknown session should return 404."""
        resp = client.get("/api/diagnosis?session_id=nosuch")
        assert resp.status_code == 404

    def test_api_diagnosis_suggested_tests(self, client):
        """GET /api/diagnosis should include suggested_tests for top matches."""
        _start_game(client)
        client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        resp = client.get("/api/diagnosis?session_id=case_001")
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert "suggested_tests" in data
        assert isinstance(data["suggested_tests"], list)


# ─────────────────────────────────────────────────────────────
#  SECTION 10: Content Type / JSON Response Verification
# ─────────────────────────────────────────────────────────────

class TestResponseFormat:

    def test_api_cases_is_json(self, client):
        resp = client.get("/api/cases")
        assert resp.content_type.startswith("application/json")

    def test_api_examinations_is_json(self, client):
        resp = client.get("/api/examinations")
        assert resp.content_type.startswith("application/json")

    def test_api_treatments_is_json(self, client):
        resp = client.get("/api/treatments")
        assert resp.content_type.startswith("application/json")

    def test_api_new_game_is_json(self, client):
        resp = client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "case_001"}),
            content_type="application/json",
        )
        assert resp.content_type.startswith("application/json")

    def test_api_examine_is_json(self, client):
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        assert resp.content_type.startswith("application/json")

    def test_api_diagnose_is_json(self, client):
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": "pneumonia"}),
            content_type="application/json",
        )
        assert resp.content_type.startswith("application/json")

    def test_api_game_state_is_json(self, client):
        _start_game(client)
        resp = client.get("/api/game-state?session_id=case_001")
        assert resp.content_type.startswith("application/json")

    def test_api_wait_is_json(self, client):
        _start_game(client)
        resp = client.post(
            "/api/wait",
            data=json.dumps({"session_id": "case_001"}),
            content_type="application/json",
        )
        assert resp.content_type.startswith("application/json")


# ─────────────────────────────────────────────────────────────
#  SECTION 11: Session Persistence
# ─────────────────────────────────────────────────────────────

class TestSessionPersistence:

    def test_full_game_flow(self, client):
        """Complete flow: new-game -> examine -> examine -> diagnose."""
        start_data = _start_game(client)
        assert start_data["game_state"]["time_elapsed_min"] == 0

        resp1 = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        d1 = json.loads(resp1.data)
        assert d1["time_elapsed_min"] == 5

        resp2 = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "blood_gas"}),
            content_type="application/json",
        )
        d2 = json.loads(resp2.data)
        # blood_gas has time_cost_min=5, so time_elapsed_min goes 1 → 4
        assert d2["time_elapsed_min"] == 10

        # Check accumulated reports via game-state
        state = client.get("/api/game-state?session_id=case_001")
        sd = json.loads(state.data)
        assert sd["reports_count"] == 2

        # Diagnose correctly (treat costs 5 min)
        diag = client.post(
            "/api/diagnose",
            data=json.dumps({"session_id": "case_001", "diagnosis": "pneumonia"}),
            content_type="application/json",
        )
        dd = json.loads(diag.data)
        assert dd["phase"] == "won"
        assert dd["time_elapsed_min"] == 15

    def test_multiple_case_isolation(self, client):
        """Two different cases should maintain separate sessions."""
        _start_game(client, case_id="case_001")
        _start_game(client, case_id="case_002")

        state1 = client.get("/api/game-state?session_id=case_001")
        state2 = client.get("/api/game-state?session_id=case_002")
        assert state1.status_code == 200
        assert state2.status_code == 200

    def test_game_state_after_lost(self, client):
        """After game is lost, further actions should return error with 400."""
        _start_game(client)
        import gui_app as gui
        state = gui._game_sessions["case_001"]
        state.phase = "lost"

        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        # Lost games return 400 with {"error": "..."}
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data

    def test_game_state_after_won(self, client):
        """After game is won, further actions should return error with 400."""
        _start_game(client)
        import gui_app as gui
        state = gui._game_sessions["case_001"]
        state.phase = "won"

        resp = client.post(
            "/api/examine",
            data=json.dumps({"session_id": "case_001", "test_type": "physical"}),
            content_type="application/json",
        )
        assert resp.status_code == 400
        data = json.loads(resp.data)
        assert "error" in data


# ─────────────────────────────────────────────────────────────
#  SECTION 12: Error Handling / Edge Cases
# ─────────────────────────────────────────────────────────────

class TestErrorHandling:

    def test_examine_empty_body(self, client):
        """POST /api/examine with empty JSON body should use defaults."""
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_diagnose_empty_body(self, client):
        """POST /api/diagnose with empty body should not 500."""
        _start_game(client)
        resp = client.post(
            "/api/diagnose",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_wait_empty_body(self, client):
        """POST /api/wait with empty body should use default session_id."""
        _start_game(client)
        resp = client.post(
            "/api/wait",
            data=json.dumps({}),
            content_type="application/json",
        )
        assert resp.status_code == 200

    def test_malformed_json_examine(self, client):
        """POST /api/examine with malformed JSON should not 500."""
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data="not valid json{{{",
            content_type="application/json",
        )
        assert resp.status_code == 400

    def test_unknown_case_id(self, client):
        """Unknown case_id should return 404."""
        resp = client.post(
            "/api/new-game",
            data=json.dumps({"case_id": "ghost_case"}),
            content_type="application/json",
        )
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert "error" in data

    def test_post_without_content_type_header(self, client):
        """POST with JSON body but no content-type returns 415 or handles gracefully."""
        _start_game(client)
        resp = client.post(
            "/api/examine",
            data='{"session_id": "case_001"}',
        )
        # Flask returns 415 Unsupported Media Type when content-type is missing
        assert resp.status_code in (200, 400, 415)


# ─────────────────────────────────────────────────────────────
#  SECTION 13: All Registered Routes Return No 500
# ─────────────────────────────────────────────────────────────

class TestAllRoutesNo500:

    @pytest.mark.parametrize("path,method", [
        ("/", "GET"),
        ("/api/cases", "GET"),
        ("/api/examinations", "GET"),
        ("/api/treatments", "GET"),
    ])
    def test_routes_no_500(self, client, path, method):
        """Each static route should return without 500 error."""
        if method == "GET":
            resp = client.get(path)
        else:
            resp = client.post(path)
        assert resp.status_code != 500, f"{method} {path} returned 500"


# ─────────────────────────────────────────────────────────────
#  SECTION 14: CLI Daemon — Argument Parsing
# ─────────────────────────────────────────────────────────────

class TestCLI:
    """
    Tests for cli_daemon.py constants and structure.

    NOTE: cli_daemon.py has an import bug — it references `TOTAL_BLOOD_VOLUME_ML`
    which does not exist in src.parameters (the actual name is
    `total_blood_volume_ml`, a function). It also imports
    `from simulation import VirtualCreature` (without `src.` prefix), which only
    works when the script is run from the project root as __main__.
    Therefore, we test CLI constants by extracting them from the source file
    rather than importing the module.

    BUG FOUND: cli_daemon.py line 23:
        from src.parameters import (TOTAL_BLOOD_VOLUME_ML, ...)
    Should be:
        from src.parameters import (total_blood_volume_ml, ...)
    Or the function wrapper should be added to parameters.py.
    """

    @staticmethod
    def _extract_cli_constants():
        """Extract SCENARIOS, NORMAL_RANGES, HISTORY_METRICS by running
        cli_daemon.py constants module via runpy with patched imports.

        cli_daemon.py cannot be directly imported because:
        1. It imports `from simulation import VirtualCreature` (no src. prefix)
        2. It imports `from src.parameters import (TOTAL_BLOOD_VOLUME_ML, ...)`
           but TOTAL_BLOOD_VOLUME_ML does not exist in src.parameters
        """
        helper_code = (
            "import sys, json, types\n"
            f"sys.path.insert(0, r'{PROJECT_ROOT}')\n"
            f"sys.path.insert(0, r'{os.path.join(PROJECT_ROOT, 'src')}')\n"
            "# Create a stub module so 'from simulation import VirtualCreature' works\n"
            "import importlib\n"
            "sim = importlib.import_module('src.simulation')\n"
            "sys.modules['simulation'] = sim\n"
            "# Patch parameters to provide the missing name\n"
            "params = importlib.import_module('src.parameters')\n"
            "if not hasattr(params, 'TOTAL_BLOOD_VOLUME_ML'):\n"
            "    params.TOTAL_BLOOD_VOLUME_ML = 600.0\n"
            "# Now execute the module body (before if __name__ == '__main__')\n"
            "cli_src = open(r'" + os.path.join(PROJECT_ROOT, "cli_daemon.py") + "').read()\n"
            "cli_body = cli_src.split('if __name__')[0]\n"
            "# Provide __file__ for the exec context\n"
            "exec_ctx = {'__file__': r'" + os.path.join(PROJECT_ROOT, "cli_daemon.py") + "', '__name__': '__module__'}\n"
            "exec(cli_body, exec_ctx)\n"
            "print(json.dumps({\n"
            "    'scenarios': {k: {'label': v['label'], 'events': v['events'], 'color': v['color'], 'label_en': v.get('label_en','')} for k, v in exec_ctx['SCENARIOS'].items()},\n"
            "    'history_metrics': exec_ctx['HISTORY_METRICS'],\n"
            "    'cocaine_metrics': exec_ctx['COCAINE_METRICS'],\n"
            "    'normal_ranges': {k: list(v) for k, v in exec_ctx['NORMAL_RANGES'].items()},\n"
            "}))\n"
        )
        import subprocess
        result = subprocess.run(
            [sys.executable, "-c", helper_code],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode != 0:
            pytest.fail(f"CLI helper failed: {result.stderr}")
        return json.loads(result.stdout)

    def test_scenario_data_structure(self):
        """SCENARIOS dict should have expected scenario keys."""
        data = self._extract_cli_constants()
        scenarios = data["scenarios"]
        assert "normal" in scenarios
        assert "blood_loss_200" in scenarios
        assert "dehydration" in scenarios
        assert "cocaine" in scenarios

    def test_scenario_has_required_fields(self):
        """Each scenario should have label, events, and color fields."""
        data = self._extract_cli_constants()
        for key, scenario in data["scenarios"].items():
            assert "label" in scenario, f"Scenario '{key}' missing 'label'"
            assert "events" in scenario, f"Scenario '{key}' missing 'events'"
            assert "color" in scenario, f"Scenario '{key}' missing 'color'"
            assert isinstance(scenario["events"], list)

    def test_normal_scenario_no_events(self):
        """Normal scenario should have empty events list."""
        data = self._extract_cli_constants()
        assert data["scenarios"]["normal"]["events"] == []

    def test_blood_loss_scenario_events(self):
        """Blood loss scenarios should have blood_loss event type."""
        data = self._extract_cli_constants()
        for key in ("blood_loss_100", "blood_loss_200"):
            events = data["scenarios"][key]["events"]
            assert len(events) >= 1
            assert events[0]["type"] == "blood_loss"
            assert "vol" in events[0]
            assert events[0]["vol"] > 0

    def test_cocaine_scenario_events(self):
        """Cocaine scenarios should have cocaine event type with dose."""
        data = self._extract_cli_constants()
        for key in ("cocaine", "cocaine_high"):
            events = data["scenarios"][key]["events"]
            assert len(events) >= 1
            assert events[0]["type"] == "cocaine"
            assert "dose_mg_kg" in events[0]

    def test_all_scenarios_have_label_en(self):
        """Each scenario should have a label_en field."""
        data = self._extract_cli_constants()
        for key, scenario in data["scenarios"].items():
            assert "label_en" in scenario, f"Scenario '{key}' missing 'label_en'"

    def test_normal_ranges_validity(self):
        """All NORMAL_RANGES in cli_daemon should have lo < hi."""
        data = self._extract_cli_constants()
        for key, vals in data["normal_ranges"].items():
            lo, hi = vals
            assert lo < hi, f"NORMAL_RANGES['{key}']: {lo} >= {hi}"

    def test_history_metrics_list(self):
        """HISTORY_METRICS should contain expected metric keys."""
        data = self._extract_cli_constants()
        expected = {"HR_bpm", "MAP_mmHg", "CO_ml_min", "blood_volume_ml",
                    "saturation", "RR", "GFR", "urine_ml_min", "BUN", "pH"}
        assert set(data["history_metrics"]) == expected

    def test_cocaine_metrics_list(self):
        """COCAINE_METRICS should be a subset with cocaine-specific fields."""
        data = self._extract_cli_constants()
        assert "HR_bpm" in data["cocaine_metrics"]
        assert "MAP_mmHg" in data["cocaine_metrics"]
        assert "contractility_factor" in data["cocaine_metrics"]

    def test_cli_import_works(self):
        """cli_daemon.py 应当能直接 import（之前有 TOTAL_BLOOD VOLUME_ML 拼写错误，已修复）。"""
        import cli_daemon  # noqa: F401
        assert True

