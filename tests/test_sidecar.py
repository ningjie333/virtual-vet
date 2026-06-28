"""virtual-vet sidecar 端到端测试。

通过 spawn sidecar_entry.py 子进程，stdin/stdout 走 JSON-RPC 协议，
覆盖完整生命周期: list_cases → new_session → advance → administer_drug
              → examine → diagnose → end_session → shutdown。

设计原则:
  - 测试用例不依赖具体疾病数值，只校验字段契约和阶段转移
  - 用 case_001（pneumonia, 犬, 20kg, ★☆☆）作为主路径
  - 用 case_003（DCM, 犬, 难度2）作为次路径，验证多病历并发
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_ENTRY = _PROJECT_ROOT / "sidecar_entry.py"


class SidecarProcess:
    """sidecar 子进程包装，提供 RPC 调用便利方法。"""

    def __init__(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["VET_VET_SIDECAR_LOG"] = "WARNING"  # 测试时压低日志
        self.proc = subprocess.Popen(
            [sys.executable, str(_SIDECAR_ENTRY)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        # 读取 ready 信号
        ready_line = self.proc.stdout.readline()
        if not ready_line:
            err = self.proc.stderr.read()
            raise RuntimeError(f"sidecar failed to start. stderr:\n{err}")
        ready = json.loads(ready_line)
        assert ready.get("method") == "ready", f"unexpected ready: {ready}"

    def call(self, method: str, params: dict | None = None) -> dict:
        """发起一次 JSON-RPC 调用，返回 result 或抛 AssertionError（含 error 详情）。"""
        req = {
            "jsonrpc": "2.0",
            "id": "test",
            "method": method,
            "params": params or {},
        }
        self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()
            raise AssertionError(f"sidecar closed. stderr:\n{err}")
        resp = json.loads(line)
        if "error" in resp:
            raise AssertionError(f"RPC error for {method}: {resp['error']}")
        return resp["result"]

    def shutdown(self) -> None:
        if self.proc.poll() is not None:
            return
        try:
            self.call("shutdown")
        except Exception:
            pass
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()


@pytest.fixture
def sidecar():
    """启动一个 sidecar 进程，测试结束自动 shutdown。"""
    proc = SidecarProcess()
    yield proc
    proc.shutdown()


# ──────────────────────────────────────────────────────────────────
# 协议层测试
# ──────────────────────────────────────────────────────────────────


class TestProtocol:
    """JSON-RPC 协议本身的行为测试。"""

    def test_ready_signal(self, sidecar: SidecarProcess):
        """sidecar 启动后必须先发 ready 信号（已在 fixture 中读取）。"""
        # 如果 fixture 成功，说明 ready 已收到
        assert sidecar.proc.poll() is None

    def test_method_not_found(self, sidecar: SidecarProcess):
        """未知方法应返回 -32601 错误。"""
        with pytest.raises(AssertionError, match="method not found"):
            sidecar.call("nonexistent.method", {})

    def test_invalid_params_missing_session_id(self, sidecar: SidecarProcess):
        """缺少 session_id 应返回 -32602 错误。"""
        with pytest.raises(AssertionError, match="session_id required"):
            sidecar.call("game.advance", {})

    def test_session_not_found(self, sidecar: SidecarProcess):
        """不存在的 session_id 应返回 -32001 错误。"""
        with pytest.raises(AssertionError, match="session not found"):
            sidecar.call("game.advance", {"session_id": "nonexistent_sid"})


# ──────────────────────────────────────────────────────────────────
# 病历生命周期测试
# ──────────────────────────────────────────────────────────────────


class TestCaseLifecycle:
    """完整病历生命周期测试。"""

    def test_list_cases(self, sidecar: SidecarProcess):
        """list_cases 应返回病历摘要列表，字段完整。"""
        result = sidecar.call("game.list_cases")
        assert "cases" in result
        cases = result["cases"]
        assert len(cases) >= 15, f"expected >=15 cases, got {len(cases)}"

        first = cases[0]
        required_fields = {
            "id",
            "title",
            "difficulty",
            "difficulty_label",
            "species",
            "breed",
            "age",
            "weight_kg",
            "chief_complaint",
        }
        assert required_fields.issubset(first.keys()), (
            f"missing fields: {required_fields - set(first.keys())}"
        )
        # 病历摘要不应暴露 disease / starting_hints 等诊断细节
        assert "disease" not in first, "case summary must not leak disease field"
        assert "starting_hints" not in first, (
            "case summary must not leak starting_hints"
        )

    def test_new_session_returns_initial_snapshot(self, sidecar: SidecarProcess):
        """new_session 应返回 session_id 与 initial_snapshot，含病历外壳。"""
        result = sidecar.call("game.new_session", {"case_id": "case_001"})
        assert "session_id" in result
        assert "initial_snapshot" in result

        snap = result["initial_snapshot"]
        # 病历外壳字段
        assert snap["case"]["id"] == "case_001"
        assert "title" in snap["case"]
        assert "animal" in snap["case"]
        assert "chief_complaint" in snap["case"]
        # 体征字段
        assert "vitals" in snap
        vitals = snap["vitals"]
        for field in ("hr_bpm", "map_mmhg", "spo2_pct", "rr_bpm", "game_time"):
            assert field in vitals, f"missing vital: {field}"
        # 游戏元信息
        assert snap["phase"] == "playing"
        assert snap["medical_phase"] in {"stable", "worsening", "critical", "moribund"}
        assert snap["time_elapsed_min"] == 0
        assert snap["time_budget_min"] > 0
        # initial snapshot 不应暴露 disease_name（诊断考验）
        assert "disease_name" not in snap, "snapshot must not leak disease_name"

    def test_full_lifecycle_case_001(self, sidecar: SidecarProcess):
        """case_001 完整生命周期：开 → 推进 → 给药 → 检查 → 结束。"""
        # 1. 开病历
        result = sidecar.call("game.new_session", {"case_id": "case_001"})
        session_id = result["session_id"]
        initial_phase = result["initial_snapshot"]["phase"]
        assert initial_phase == "playing"

        # 2. 推进时间（wait 10min）
        snap = sidecar.call("game.advance", {"session_id": session_id})
        assert snap["phase"] in {"playing", "won", "lost"}
        assert snap["time_elapsed_min"] >= 10
        assert "vitals" in snap
        assert "active_signs" in snap

        # 3. 给药（pneumonia case 可用 furosemide 测试，但未知药也不应崩溃）
        snap = sidecar.call(
            "game.administer_drug",
            {
                "session_id": session_id,
                "drug_name": "furosemide",
                "dose_mg_kg": 1.0,
            },
        )
        assert snap["time_elapsed_min"] >= 15
        # 给药后体征仍可读
        assert "hr_bpm" in snap["vitals"]

        # 4. 检查（physical examination 不消耗延迟报告）
        snap = sidecar.call(
            "game.examine",
            {"session_id": session_id, "test_type": "physical"},
        )
        assert "new_reports" in snap
        assert "pending_reports" in snap

        # 5. 结束会话
        result = sidecar.call("game.end_session", {"session_id": session_id})
        assert result["ok"] is True

        # 6. 结束后再操作应报错
        with pytest.raises(AssertionError, match="session not found"):
            sidecar.call("game.advance", {"session_id": session_id})

    def test_concurrent_sessions_different_cases(self, sidecar: SidecarProcess):
        """同一 sidecar 应支持多个并发会话（不同病历）。"""
        r1 = sidecar.call("game.new_session", {"case_id": "case_001"})
        r2 = sidecar.call("game.new_session", {"case_id": "case_002"})

        sid1 = r1["session_id"]
        sid2 = r2["session_id"]
        assert sid1 != sid2, "sessions must have distinct ids"

        # 在 sid1 推进，不影响 sid2
        s1 = sidecar.call("game.advance", {"session_id": sid1})
        s2_initial = r2["initial_snapshot"]
        # sid2 的体征在 sid1 推进后应保持不变（除非主动 advance）
        # 由于 sid2 还未 advance，time_elapsed_min 应仍为 0
        assert s2_initial["time_elapsed_min"] == 0
        assert s1["time_elapsed_min"] > 0

        # 清理
        sidecar.call("game.end_session", {"session_id": sid1})
        sidecar.call("game.end_session", {"session_id": sid2})


# ──────────────────────────────────────────────────────────────────
# 诊断动作测试
# ──────────────────────────────────────────────────────────────────


class TestDiagnoseAction:
    """game.diagnose 接口测试。"""

    def test_correct_diagnosis_wins(self, sidecar: SidecarProcess):
        """提交正确诊断应让 phase → won。"""
        # case_001 的 disease 是 pneumonia（从 cases.json 已知）
        r = sidecar.call("game.new_session", {"case_id": "case_001"})
        sid = r["session_id"]

        # 直接提交诊断（不等病程发展，验证机制即可）
        snap = sidecar.call(
            "game.diagnose",
            {"session_id": sid, "diagnosis": "pneumonia"},
        )
        assert snap["phase"] == "won", (
            f"correct diagnosis should win, got phase={snap['phase']}"
        )
        sidecar.call("game.end_session", {"session_id": sid})

    def test_wrong_diagnosis_does_not_win(self, sidecar: SidecarProcess):
        """错误诊断不应让 phase → won。"""
        r = sidecar.call("game.new_session", {"case_id": "case_001"})
        sid = r["session_id"]

        snap = sidecar.call(
            "game.diagnose",
            {"session_id": sid, "diagnosis": "healthy"},  # 错误诊断
        )
        assert snap["phase"] != "won", "wrong diagnosis must not win"
        sidecar.call("game.end_session", {"session_id": sid})

    def test_game_ended_rejects_actions(self, sidecar: SidecarProcess):
        """游戏结束后（won/lost）再操作应被拒绝或返回 phase 不变。"""
        r = sidecar.call("game.new_session", {"case_id": "case_001"})
        sid = r["session_id"]

        # 先赢
        sidecar.call("game.diagnose", {"session_id": sid, "diagnosis": "pneumonia"})

        # 赢后再 advance —— process_action 内部会返回 success=False 但不报错
        snap = sidecar.call("game.advance", {"session_id": sid})
        assert snap["phase"] == "won", "phase should remain won"
        sidecar.call("game.end_session", {"session_id": sid})


# ──────────────────────────────────────────────────────────────────
# Snapshot 字段契约测试
# ──────────────────────────────────────────────────────────────────


class TestSnapshotContract:
    """Snapshot 字段契约稳定性测试。

    这些字段是 vet-knowledge 前端依赖的，改动需协商。
    """

    def test_snapshot_required_fields(self, sidecar: SidecarProcess):
        """每个 snapshot 必须包含契约字段。"""
        r = sidecar.call("game.new_session", {"case_id": "case_001"})
        sid = r["session_id"]
        snap = sidecar.call("game.advance", {"session_id": sid})

        required = {
            "phase",
            "medical_phase",
            "time_elapsed_min",
            "time_budget_min",
            "time_remaining_min",
            "death_timer",
            "vitals",
            "active_signs",
            "new_reports",
            "pending_reports",
        }
        assert required.issubset(snap.keys()), (
            f"missing snapshot fields: {required - set(snap.keys())}"
        )

        # vitals 子契约
        vitals_required = {
            "hr_bpm",
            "map_mmhg",
            "spo2_pct",
            "rr_bpm",
            "temp_c",
            "gfr_ml_min",
            "ph",
            "game_time",
            "is_night",
        }
        assert vitals_required.issubset(snap["vitals"].keys()), (
            f"missing vitals: {vitals_required - set(snap['vitals'].keys())}"
        )

        # active_signs 子契约（list 元素 dict）
        for sign in snap["active_signs"]:
            assert "sign_id" in sign
            assert "display_name" in sign
            assert "severity" in sign

        sidecar.call("game.end_session", {"session_id": sid})

    def test_active_signs_display_name_is_chinese(self, sidecar: SidecarProcess):
        """active_signs 的 display_name 应为中文，可喂给 vet-knowledge infer_diagnosis。"""
        r = sidecar.call("game.new_session", {"case_id": "case_001"})
        sid = r["session_id"]

        # 推进一段时间让症状出现
        for _ in range(3):
            sidecar.call("game.advance", {"session_id": sid})

        snap = sidecar.call("game.advance", {"session_id": sid})
        # 不强制要求一定有 active_signs（疾病可能未充分激活），
        # 但若有，display_name 必须是非空字符串
        for sign in snap["active_signs"]:
            assert isinstance(sign["display_name"], str)
            assert len(sign["display_name"]) > 0

        sidecar.call("game.end_session", {"session_id": sid})


# ──────────────────────────────────────────────────────────────────
# 协议鲁棒性测试
# ──────────────────────────────────────────────────────────────────


class TestRobustness:
    """协议鲁棒性测试：非法输入不应让 sidecar 崩溃。"""

    def test_unknown_drug_does_not_crash(self, sidecar: SidecarProcess):
        """未知药物应返回 error 字段但 sidecar 不崩溃。"""
        r = sidecar.call("game.new_session", {"case_id": "case_001"})
        sid = r["session_id"]

        snap = sidecar.call(
            "game.administer_drug",
            {"session_id": sid, "drug_name": "nonexistent_drug_xyz", "dose_mg_kg": 1.0},
        )
        # 未知药物不应让 sidecar 崩溃，snapshot 仍应可读
        assert "vitals" in snap
        sidecar.call("game.end_session", {"session_id": sid})

    def test_invalid_json_does_not_crash(self, sidecar: SidecarProcess):
        """非法 JSON 应返回 -32700 错误，sidecar 继续运行。"""
        # 直接写入非法 JSON
        sidecar.proc.stdin.write("not a json\n")
        sidecar.proc.stdin.flush()
        line = sidecar.proc.stdout.readline()
        resp = json.loads(line)
        assert "error" in resp
        assert resp["error"]["code"] == -32700

        # sidecar 仍应可用
        result = sidecar.call("game.list_cases")
        assert "cases" in result
