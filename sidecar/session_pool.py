"""会话池：session_id → SessionContext 的线程安全管理。

设计:
  - 模块级 `_registry_lock` 保护 4 个字典的原子初始化（参考 gui_app.py 同名锁）
  - 每个 session 有独立锁，保护该 session 内部状态修改（避免并发 advance/administer 冲突）
  - 会话锁与注册锁不嵌套，无死锁风险
  - 后台任务注册表 `_pending_jobs` 用于异步推进（阶段 3）
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from sidecar.case_loader import SessionContext, create_session
from sidecar.protocol import ERR_SESSION_NOT_FOUND, RpcError

# ── 全局会话存储 ──
_sessions: dict[str, SessionContext] = {}
_session_locks: dict[str, threading.Lock] = {}

# 保护字典写入的原子性（create_lock + populate 2 dicts）
_registry_lock = threading.Lock()


# ── 后台任务管理（阶段 3：异步推进）──

@dataclass
class JobInfo:
    """后台任务状态容器。"""
    thread: Optional[threading.Thread] = None
    progress: dict = field(default_factory=lambda: {"current": 0, "total": 0})
    snapshot: Optional[dict] = None
    error: Optional[str] = None
    done: bool = False


_pending_jobs: dict[str, JobInfo] = {}
_jobs_lock = threading.Lock()


def start_job(session_id: str, job_id: str, target_fn: Callable[[JobInfo], None]) -> JobInfo:
    """启动后台线程执行 target_fn。

    target_fn 接收 JobInfo 参数，内部更新其 progress/snapshot/error/done 字段。
    线程在 session 锁外运行（锁由 target_fn 内部管理）。
    """
    job = JobInfo()
    with _jobs_lock:
        _pending_jobs[job_id] = job

    def _worker():
        try:
            target_fn(job)
        except Exception as e:
            job.error = f"{type(e).__name__}: {e}"
        finally:
            job.done = True

    thread = threading.Thread(target=_worker, daemon=True, name=f"job_{job_id}")
    job.thread = thread
    thread.start()
    return job


def get_job(job_id: str) -> JobInfo:
    """返回任务状态；不存在抛 RpcError。"""
    with _jobs_lock:
        job = _pending_jobs.get(job_id)
    if job is None:
        raise RpcError(ERR_SESSION_NOT_FOUND, f"job not found: {job_id}")
    return job


def cancel_job(job_id: str) -> bool:
    """标记任务取消（本次简化为不可取消，仅清理注册表条目）。"""
    with _jobs_lock:
        _pending_jobs.pop(job_id, None)
    return True


def new_session(case_id: str) -> tuple[str, SessionContext]:
    """创建新会话，返回 (session_id, context)。

    session_id 使用 uuid4 而非 case_id —— 允许同一病历多次开（玩家对比处置策略）。
    """
    context = create_session(case_id)
    session_id = uuid.uuid4().hex[:12]

    with _registry_lock:
        lock = threading.Lock()
        _sessions[session_id] = context
        _session_locks[session_id] = lock

    return session_id, context


def get_session(session_id: str) -> SessionContext:
    """获取会话上下文；不存在则抛 RpcError(ERR_SESSION_NOT_FOUND)。"""
    with _registry_lock:
        if session_id not in _sessions:
            raise RpcError(
                ERR_SESSION_NOT_FOUND,
                f"session not found: {session_id}",
            )
        return _sessions[session_id]


def acquire_lock(session_id: str) -> threading.Lock:
    """获取会话锁；session 不存在抛 RpcError。

    返回的锁已由调用方负责 with 上下文管理。
    """
    with _registry_lock:
        lock = _session_locks.get(session_id)
        if lock is None:
            raise RpcError(
                ERR_SESSION_NOT_FOUND,
                f"session not found: {session_id}",
            )
        return lock


def end_session(session_id: str) -> bool:
    """结束会话，释放引擎资源。返回是否成功删除。"""
    with _registry_lock:
        _sessions.pop(session_id, None)
        _session_locks.pop(session_id, None)
    return True


def session_count() -> int:
    """当前活跃会话数（用于 shutdown 前的诊断）。"""
    with _registry_lock:
        return len(_sessions)


def clear_all() -> int:
    """清理所有会话（shutdown 时调用）。返回清理的数量。"""
    with _registry_lock:
        n = len(_sessions)
        _sessions.clear()
        _session_locks.clear()
        return n
