"""JSON-RPC 2.0 over stdio 协议封装。

约束:
  - 单向请求-响应（无通知、无批量）
  - 错误码遵循 JSON-RPC 2.0 标准（-32700 ~ -32099 服务端自定义区间）
  - stderr 不参与协议，仅供调试日志（vet-knowledge 端可重定向到日志文件）

参考: https://www.jsonrpc.org/specification
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# ── JSON-RPC 标准错误码 ──
ERR_PARSE_ERROR = -32700      # JSON 解析失败
ERR_INVALID_REQUEST = -32600  # 请求对象不合法
ERR_METHOD_NOT_FOUND = -32601  # 方法不存在
ERR_INVALID_PARAMS = -32602   # 参数非法
ERR_INTERNAL = -32603         # 内部错误

# ── 服务端自定义错误码（-32000 ~ -32099）──
ERR_SESSION_NOT_FOUND = -32001
ERR_CASE_NOT_FOUND = -32002
ERR_INVALID_ACTION = -32003
ERR_GAME_ENDED = -32004


@dataclass(frozen=True)
class RpcError(Exception):
    """JSON-RPC 错误异常。

    `Exception` 不是 frozen 的，但 dataclass(frozen=True) 阻止对 code/message 字段
    的赋值；继承 Exception 仅为复用 raise 语法，不破坏不可变性。
    """
    code: int
    message: str
    data: Any = None

    def __str__(self) -> str:
        return f"[{self.code}] {self.message}"


def make_response(req_id: str | int | None, result: Any) -> str:
    """构造成功响应并序列化为单行 JSON（无尾随换行）。"""
    return json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "result": result},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def make_error_response(
    req_id: str | int | None, code: int, message: str, data: Any = None
) -> str:
    """构造错误响应。req_id 为 None 表示无法解析请求时使用。"""
    err: dict[str, Any] = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return json.dumps(
        {"jsonrpc": "2.0", "id": req_id, "error": err},
        ensure_ascii=False,
        separators=(",", ":"),
    )


def parse_request(line: str) -> tuple[str | int | None, str, dict]:
    """解析一行 JSON-RPC 请求。

    Returns:
        (id, method, params)

    Raises:
        RpcError: 解析失败或字段缺失
    """
    try:
        obj = json.loads(line)
    except json.JSONDecodeError as e:
        raise RpcError(ERR_PARSE_ERROR, "Parse error", str(e))

    if not isinstance(obj, dict):
        raise RpcError(ERR_INVALID_REQUEST, "Invalid Request", "not an object")

    req_id = obj.get("id")
    method = obj.get("method")
    params = obj.get("params", {})

    if not isinstance(method, str):
        raise RpcError(ERR_INVALID_REQUEST, "Invalid Request", "method missing")

    if not isinstance(params, dict):
        raise RpcError(ERR_INVALID_PARAMS, "Invalid params", "params must be object")

    return req_id, method, params
