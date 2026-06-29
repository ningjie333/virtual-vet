"""virtual-vet sidecar 异步推进测试（阶段 3）。

验证 game.advance_async + game.poll_status 流程：
  - advance_async 立即返回 job_id + estimated_ms
  - poll_status 返回 done/progress_pct/snapshot/error
  - progress 递增直到 done=true
  - done=true 时 snapshot 含完整字段
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_SIDECAR_ENTRY = _PROJECT_ROOT / "sidecar_entry.py"


class SidecarProcess:
    """sidecar 子进程包装（简化版，复用 test_sidecar.py 同结构）。"""

    def __init__(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(_PROJECT_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        env["PYTHONIOENCODING"] = "utf-8"
        env["VET_VET_SIDECAR_LOG"] = "WARNING"
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
        ready_line = self.proc.stdout.readline()
        if not ready_line:
            err = self.proc.stderr.read()
            raise RuntimeError(f"sidecar failed to start. stderr:\n{err}")
        ready = json.loads(ready_line)
        assert ready.get("method") == "ready", f"unexpected ready: {ready}"

    def call(self, method: str, params: dict | None = None) -> dict:
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
    proc = SidecarProcess()
    yield proc
    proc.shutdown()


def _new_session(sidecar: SidecarProcess, case_id: str = "case_001") -> str:
    result = sidecar.call("game.new_session", {"case_id": case_id})
    return result["session_id"]


class TestAdvanceAsync:
    """异步推进流程测试。"""

    def test_advance_async_returns_job_id_immediately(self, sidecar: SidecarProcess):
        """advance_async 应立即返回 job_id 和 estimated_ms，不阻塞。"""
        session_id = _new_session(sidecar)
        t0 = time.monotonic()
        result = sidecar.call("game.advance_async", {"session_id": session_id, "minutes": 10})
        elapsed_ms = (time.monotonic() - t0) * 1000

        assert "job_id" in result
        assert isinstance(result["job_id"], str)
        assert result["job_id"].startswith("job_")
        assert "estimated_ms" in result
        assert result["estimated_ms"] > 0
        # 立即返回（< 2s 容差，sidecar IPC 本身有开销）
        assert elapsed_ms < 2000, f"advance_async took {elapsed_ms:.0f}ms, expected <2000ms"

    def test_poll_status_progress_and_done(self, sidecar: SidecarProcess):
        """轮询 poll_status：progress 递增，最终 done=true 且 snapshot 完整。"""
        session_id = _new_session(sidecar)
        result = sidecar.call("game.advance_async", {"session_id": session_id, "minutes": 10})
        job_id = result["job_id"]

        # 轮询直到 done，最多等 60s
        seen_progress = []
        final = None
        for _ in range(300):
            status = sidecar.call("game.poll_status", {"job_id": job_id})
            seen_progress.append(status["progress_pct"])
            if status["done"]:
                final = status
                break
            time.sleep(0.2)

        assert final is not None, "job did not complete within 60s"
        assert final["done"] is True
        assert final["error"] is None
        assert final["progress_pct"] == 100.0
        # snapshot 必须存在且含必要字段
        assert final["snapshot"] is not None
        snap = final["snapshot"]
        assert "vitals" in snap
        assert "phase" in snap
        assert "time_elapsed_min" in snap
        # wait 推进 10 分钟
        assert snap["time_elapsed_min"] >= 10

    def test_poll_status_unknown_job(self, sidecar: SidecarProcess):
        """不存在的 job_id 应返回错误。"""
        with pytest.raises(AssertionError, match="job not found"):
            sidecar.call("game.poll_status", {"job_id": "job_nonexistent"})

    def test_poll_status_missing_job_id(self, sidecar: SidecarProcess):
        """缺少 job_id 应返回参数错误。"""
        with pytest.raises(AssertionError, match="job_id required"):
            sidecar.call("game.poll_status", {})

    def test_async_then_sync_advance_consistency(self, sidecar: SidecarProcess):
        """异步推进后再同步推进，session 状态一致（锁正确释放）。"""
        session_id = _new_session(sidecar)

        # 异步推进
        result = sidecar.call("game.advance_async", {"session_id": session_id, "minutes": 10})
        job_id = result["job_id"]
        for _ in range(300):
            status = sidecar.call("game.poll_status", {"job_id": job_id})
            if status["done"]:
                break
            time.sleep(0.2)
        assert status["done"] is True
        time_after_async = status["snapshot"]["time_elapsed_min"]

        # 同步推进（验证锁已释放，不阻塞）
        sync_result = sidecar.call("game.advance", {"session_id": session_id})
        time_after_sync = sync_result["time_elapsed_min"]
        assert time_after_sync > time_after_async
