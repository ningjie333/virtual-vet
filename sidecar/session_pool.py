"""会话池：session_id → SessionContext 的线程安全管理。

设计:
  - 模块级 `_registry_lock` 保护 4 个字典的原子初始化（参考 gui_app.py 同名锁）
  - 每个 session 有独立锁，保护该 session 内部状态修改（避免并发 advance/administer 冲突）
  - 会话锁与注册锁不嵌套，无死锁风险
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

from sidecar.case_loader import SessionContext, create_session
from sidecar.protocol import ERR_SESSION_NOT_FOUND, RpcError

# ── 全局会话存储 ──
_sessions: dict[str, SessionContext] = {}
_session_locks: dict[str, threading.Lock] = {}

# 保护字典写入的原子性（create_lock + populate 2 dicts）
_registry_lock = threading.Lock()


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
