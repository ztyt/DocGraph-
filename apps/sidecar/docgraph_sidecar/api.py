from __future__ import annotations

import platform
import sys
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from docgraph_sidecar import __version__
from docgraph_sidecar.core.files import FileCatalog, FileCatalogError, parse_file_list_filters
from docgraph_sidecar.core.scan_jobs import ScanJobError, ScanJobStore
from docgraph_sidecar.core.snapshots import (
    SnapshotError,
    create_snapshot,
    database_status,
    restore_snapshot,
)
from docgraph_sidecar.logging import configure_logging, log_event
from docgraph_sidecar.responses import error_response, ok_response, request_context
from docgraph_sidecar.settings_store import SettingsStore, SettingsValidationError


SERVICE_NAME = "docgraph-sidecar"


def create_app(settings_store: SettingsStore | None = None) -> FastAPI:
    configure_logging()
    app = FastAPI(title="DocGraph Sidecar", version=__version__)
    app.state.settings_store = settings_store or SettingsStore()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["tauri://localhost"],
        allow_origin_regex=r"^http://(localhost|127\.0\.0\.1):\d+$",
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    async def health(request: Request) -> dict[str, Any]:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        features = store.features()
        data = {
            "status": "ok",
            "service": SERVICE_NAME,
            "version": __version__,
            "mode": "local",
            "features": features,
        }
        log_event(
            "api.request",
            path="/api/health",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.get("/api/settings")
    async def get_settings(request: Request) -> dict[str, Any]:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        data = store.load()
        log_event(
            "api.request",
            path="/api/settings",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.put("/api/settings")
    async def put_settings(request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise SettingsValidationError({"payload": "Settings payload must be an object."})
            data = store.save(payload)
        except SettingsValidationError as exc:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    code="SETTINGS_VALIDATION_ERROR",
                    message="Settings payload is invalid.",
                    retryable=False,
                    details=exc.details,
                    context=context,
                ),
            )

        log_event(
            "api.request",
            path="/api/settings",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.get("/api/features")
    async def get_features(request: Request) -> dict[str, Any]:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        data = store.features()
        log_event(
            "api.request",
            path="/api/features",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.put("/api/features")
    async def put_features(request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise SettingsValidationError({"payload": "Feature payload must be an object."})
            data = store.save_features(payload)
        except SettingsValidationError as exc:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    code="FEATURE_VALIDATION_ERROR",
                    message="Feature flag payload is invalid.",
                    retryable=False,
                    details=exc.details,
                    context=context,
                ),
            )

        log_event(
            "api.request",
            path="/api/features",
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

    @app.get("/api/files")
    async def list_files(request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            filters = parse_file_list_filters(
                {
                    "type": request.query_params.get("type"),
                    "status": request.query_params.get("status"),
                    "source": request.query_params.get("source"),
                    "keyword": request.query_params.get("keyword"),
                    "limit": request.query_params.get("limit"),
                    "offset": request.query_params.get("offset"),
                }
            )
            data = FileCatalog(data_dir=store.data_dir).list_files(filters).to_dict()
        except FileCatalogError as exc:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    code="FILES_QUERY_VALIDATION_ERROR",
                    message=str(exc),
                    retryable=False,
                    details=exc.details,
                    context=context,
                ),
            )

        log_event(
            "api.request",
            path="/api/files",
            trace_id=context.trace_id,
            status_code=200,
            total=data["total"],
        )
        return ok_response(data, context)

    @app.get("/api/db/status")
    async def db_status(request: Request) -> dict[str, Any]:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        data = database_status(data_dir=store.data_dir).to_dict()
        log_event(
            "api.request",
            path="/api/db/status",
            trace_id=context.trace_id,
            status_code=200,
        )
        return ok_response(data, context)

    @app.post("/api/db/snapshot")
    async def db_snapshot(request: Request) -> dict[str, Any]:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        data = create_snapshot(data_dir=store.data_dir, settings_store=store).to_dict()
        log_event(
            "api.request",
            path="/api/db/snapshot",
            trace_id=context.trace_id,
            status_code=200,
            snapshot_id=data["snapshot_id"],
        )
        return ok_response(data, context)

    @app.post("/api/db/restore/{snapshot_id}")
    async def db_restore(snapshot_id: str, request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            data = restore_snapshot(
                snapshot_id,
                data_dir=store.data_dir,
                settings_store=store,
            ).to_dict()
        except SnapshotError as exc:
            return JSONResponse(
                status_code=404,
                content=error_response(
                    code="SNAPSHOT_NOT_FOUND",
                    message=str(exc),
                    retryable=False,
                    details={"snapshot_id": snapshot_id},
                    context=context,
                ),
            )

        log_event(
            "api.request",
            path=f"/api/db/restore/{snapshot_id}",
            trace_id=context.trace_id,
            status_code=200,
            snapshot_id=snapshot_id,
        )
        return ok_response(data, context)

    @app.post("/api/scan/jobs")
    async def create_scan_job(request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            payload = await request.json()
            if not isinstance(payload, dict):
                raise ScanJobError(
                    "Scan job payload must be an object.",
                    details={"payload": "Expected a JSON object."},
                )
            root_path = payload.get("root_path")
            if not isinstance(root_path, str):
                raise ScanJobError(
                    "Scan root path is required.",
                    details={"root_path": "Expected a string path."},
                )
            compute_hash = payload.get("compute_hash", False)
            if not isinstance(compute_hash, bool):
                raise ScanJobError(
                    "compute_hash must be a boolean.",
                    details={"compute_hash": "Expected true or false."},
                )
            priority = payload.get("priority", 100)
            if isinstance(priority, bool) or not isinstance(priority, int):
                raise ScanJobError(
                    "priority must be an integer.",
                    details={"priority": "Expected an integer."},
                )

            data = ScanJobStore(data_dir=store.data_dir).create(
                root_path,
                compute_hash=compute_hash,
                priority=priority,
            ).to_dict()
        except ValueError:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    code="SCAN_JOB_VALIDATION_ERROR",
                    message="Scan job payload must be valid JSON.",
                    retryable=False,
                    details={"payload": "Invalid JSON."},
                    context=context,
                ),
            )
        except ScanJobError as exc:
            return JSONResponse(
                status_code=400,
                content=error_response(
                    code="SCAN_JOB_VALIDATION_ERROR",
                    message=str(exc),
                    retryable=False,
                    details=exc.details,
                    context=context,
                ),
            )

        log_event(
            "api.request",
            path="/api/scan/jobs",
            trace_id=context.trace_id,
            status_code=200,
            job_id=data["job_id"],
        )
        return ok_response(data, context)

    @app.get("/api/scan/jobs/{job_id}")
    async def get_scan_job(job_id: str, request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        data = ScanJobStore(data_dir=store.data_dir).get(job_id)
        if data is None:
            return JSONResponse(
                status_code=404,
                content=error_response(
                    code="SCAN_JOB_NOT_FOUND",
                    message="Scan job not found.",
                    retryable=False,
                    details={"job_id": job_id},
                    context=context,
                ),
            )

        log_event(
            "api.request",
            path=f"/api/scan/jobs/{job_id}",
            trace_id=context.trace_id,
            status_code=200,
            job_id=job_id,
        )
        return ok_response(data.to_dict(), context)

    @app.post("/api/scan/jobs/{job_id}/pause")
    async def pause_scan_job(job_id: str, request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            data = ScanJobStore(data_dir=store.data_dir).pause(job_id).to_dict()
        except ScanJobError as exc:
            return _scan_job_error_response(exc, context)

        log_event(
            "api.request",
            path=f"/api/scan/jobs/{job_id}/pause",
            trace_id=context.trace_id,
            status_code=200,
            job_id=job_id,
        )
        return ok_response(data, context)

    @app.post("/api/scan/jobs/{job_id}/resume")
    async def resume_scan_job(job_id: str, request: Request) -> Any:
        context = request_context(request)
        store: SettingsStore = request.app.state.settings_store
        try:
            data = ScanJobStore(data_dir=store.data_dir).resume(job_id).to_dict()
        except ScanJobError as exc:
            return _scan_job_error_response(exc, context)

        log_event(
            "api.request",
            path=f"/api/scan/jobs/{job_id}/resume",
            trace_id=context.trace_id,
            status_code=200,
            job_id=job_id,
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


def _scan_job_error_response(exc: ScanJobError, context: Any) -> JSONResponse:
    details = exc.details
    missing = str(exc).casefold().endswith("not found.")
    return JSONResponse(
        status_code=404 if missing else 400,
        content=error_response(
            code="SCAN_JOB_NOT_FOUND" if missing else "SCAN_JOB_STATE_ERROR",
            message=str(exc),
            retryable=False,
            details=details,
            context=context,
        ),
    )


app = create_app()
