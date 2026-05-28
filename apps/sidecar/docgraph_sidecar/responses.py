from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import Request


@dataclass(frozen=True)
class RequestContext:
    trace_id: str
    started_at: float


def request_context(request: Request) -> RequestContext:
    trace_id = request.headers.get("x-trace-id") or f"dg-{uuid4().hex[:16]}"
    return RequestContext(trace_id=trace_id, started_at=perf_counter())


def elapsed_ms(context: RequestContext) -> int:
    return round((perf_counter() - context.started_at) * 1000)


def ok_response(data: dict[str, Any], context: RequestContext) -> dict[str, Any]:
    return {
        "ok": True,
        "data": data,
        "error": None,
        "trace_id": context.trace_id,
        "elapsed_ms": elapsed_ms(context),
    }


def error_response(
    *,
    code: str,
    message: str,
    retryable: bool,
    context: RequestContext,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "ok": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details or {},
        },
        "trace_id": context.trace_id,
        "elapsed_ms": elapsed_ms(context),
    }

