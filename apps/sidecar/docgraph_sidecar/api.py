from __future__ import annotations

import platform
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from docgraph_sidecar import __version__
from docgraph_sidecar.logging import configure_logging, log_event
from docgraph_sidecar.responses import error_response, ok_response, request_context


SERVICE_NAME = "docgraph-sidecar"


def create_app() -> FastAPI:
    configure_logging()
    app = FastAPI(title="DocGraph Sidecar", version=__version__)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "tauri://localhost"],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        context = request_context(request)
        data = {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": __version__,
            "mode": "local",
            "features": {
                "llm": False,
                "ocr": False,
                "vector_search": False,
                "watchdog": False,
            },
        }
        log_event(
            "api.request",
            path="/api/health",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.get("/api/system/info")
    async def system_info(request: Request) -> dict[str, Any]:
        context = request_context(request)
        data = {
            "service": SERVICE_NAME,
            "version": __version__,
            "python_version": sys.version.split()[0],
            "platform": platform.system(),
            "platform_release": platform.release(),
            "machine": platform.machine(),
        }
        log_event(
            "api.request",
            path="/api/system/info",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.exception_handler(Exception)
    async def unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        context = request_context(request)
        log_event(
            "api.error",
            path=str(request.url.path),
            trace_id=context.trace_id,
            error_type=type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content=error_response(
                code="INTERNAL_ERROR",
                message="Sidecar encountered an unexpected error.",
                retryable=True,
                context=context,
            ),
        )

    return app


app = create_app()

