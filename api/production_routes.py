from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import gc
import json

from fastapi import (
    APIRouter,
    HTTPException,
    Query,
)

from fastapi.concurrency import (
    run_in_threadpool,
)

from fastapi.responses import (
    StreamingResponse,
)

from pydantic import (
    BaseModel,
    Field,
)

from vercel.blob import (
    AsyncBlobClient,
    delete,
    list_objects,
)

from backend.app.services.vercel_generation_service import (
    generate_dataset_from_blob,
)

from backend.app.services.vercel_forecast_service import (
    forecast_generated_dataset,
)

from backend.app.services.vercel_chart_service import (
    get_forecast_chart_data,
    get_validation_chart_data,
)


router = APIRouter()


WORKING_BLOB_PREFIXES = (
    "generations/",
    "forecast-runs/",
    "validation-runs/",
    "son-runs/",
)

WORKING_BLOB_TTL_SECONDS = (
    2 * 60 * 60
)

GENERATION_BLOB_FILES = (
    "forecast_input.csv",
    "ground_truth.csv",
    "model_ready_forecast_input.csv",
    "manifest.json",
)

FORECAST_BLOB_FILES = (
    "forecast.csv",
    "run_metadata.json",
)


class DatasetGenerateRequest(
    BaseModel
):
    cell_count: int = Field(
        100,
        ge=1,
        le=2000,
    )

    seed: int | None = Field(
        None,
        ge=0,
        le=2_147_483_647,
    )


class GeneratedForecastRequest(
    BaseModel
):
    generation_id: str = Field(
        ...,
        min_length=5,
    )

    horizon_steps: int = Field(
        96,
    )


class SessionCleanupRequest(
    BaseModel
):
    generation_id: str | None = None
    forecast_run_id: str | None = None


def _validate_generation_id(
    generation_id: str,
) -> str:
    clean_generation_id = (
        str(generation_id).strip()
    )

    if (
        not clean_generation_id.startswith(
            "GEN-"
        )
        or "/" in clean_generation_id
        or "\\" in clean_generation_id
        or ".." in clean_generation_id
    ):
        raise ValueError(
            "Invalid generation_id."
        )

    return clean_generation_id


def _delete_blob_paths_sync(
    paths: list[str],
):
    unique_paths = list(
        dict.fromkeys(
            path
            for path in paths
            if path
        )
    )

    if not unique_paths:
        return 0

    delete(
        unique_paths
    )

    return len(
        unique_paths
    )


def _cleanup_expired_working_blobs_sync(
    ttl_seconds: int = WORKING_BLOB_TTL_SECONDS,
):
    cutoff = (
        datetime.now(
            timezone.utc
        )
        - timedelta(
            seconds=max(
                int(ttl_seconds),
                60,
            )
        )
    )

    cursor = None
    expired_paths: list[str] = []
    expired_bytes = 0

    while True:
        page = list_objects(
            limit=1000,
            cursor=cursor,
        )

        for item in page.blobs:
            pathname = str(
                item.pathname
            )

            if not pathname.startswith(
                WORKING_BLOB_PREFIXES
            ):
                continue

            uploaded_at = (
                item.uploaded_at
            )

            if uploaded_at.tzinfo is None:
                uploaded_at = (
                    uploaded_at.replace(
                        tzinfo=timezone.utc
                    )
                )

            if uploaded_at <= cutoff:
                expired_paths.append(
                    pathname
                )
                expired_bytes += int(
                    item.size
                )

        if not page.has_more:
            break

        cursor = page.cursor

        if not cursor:
            break

    deleted_count = (
        _delete_blob_paths_sync(
            expired_paths
        )
    )

    return {
        "deleted_count": deleted_count,
        "deleted_bytes": expired_bytes,
        "ttl_seconds": int(
            ttl_seconds
        ),
    }


async def _cleanup_expired_working_blobs():
    try:
        return await run_in_threadpool(
            _cleanup_expired_working_blobs_sync
        )
    except Exception as exc:
        # Cleanup is a safety net. A temporary list/delete
        # failure must not make dataset generation unusable.
        return {
            "deleted_count": 0,
            "deleted_bytes": 0,
            "ttl_seconds": (
                WORKING_BLOB_TTL_SECONDS
            ),
            "warning": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }


def _session_blob_paths(
    generation_id: str | None,
    forecast_run_id: str | None,
) -> list[str]:
    paths: list[str] = []

    if generation_id:
        clean_generation_id = (
            _validate_generation_id(
                generation_id
            )
        )

        generation_prefix = (
            f"generations/"
            f"{clean_generation_id}"
        )

        paths.extend(
            f"{generation_prefix}/{filename}"
            for filename in (
                GENERATION_BLOB_FILES
            )
        )

    if forecast_run_id:
        clean_run_id = (
            _validate_forecast_run_id(
                forecast_run_id
            )
        )

        forecast_prefix = (
            f"forecast-runs/"
            f"{clean_run_id}"
        )

        paths.extend(
            f"{forecast_prefix}/{filename}"
            for filename in (
                FORECAST_BLOB_FILES
            )
        )

    return paths


async def _read_json_blob(
    pathname: str,
):
    async with AsyncBlobClient() as client:
        result = await client.get(
            pathname,
            access="private",
            timeout=60,
        )

    if result is None:
        raise FileNotFoundError(
            f"Blob not found: {pathname}"
        )

    content = result.content

    if isinstance(
        content,
        bytes,
    ):
        text = content.decode(
            "utf-8"
        )

    else:
        text = str(
            content
        )

    return json.loads(
        text
    )


def _manifest_path_from_generation(
    result: dict,
):
    artifacts = (
        result.get(
            "artifacts"
        )
        or {}
    )

    manifest_artifact = (
        artifacts.get(
            "manifest.json"
        )
        or {}
    )

    pathname = (
        manifest_artifact.get(
            "pathname"
        )
    )

    if not pathname:
        generation_id = (
            result.get(
                "generation_id"
            )
        )

        if generation_id:
            pathname = (
                f"generations/"
                f"{generation_id}/"
                f"manifest.json"
            )

    if not pathname:
        raise ValueError(
            "Generation manifest pathname "
            "could not be resolved."
        )

    return str(
        pathname
    )


def _frontend_generation_response(
    raw_result: dict,
    manifest: dict,
):
    generation_id = (
        raw_result.get(
            "generation_id"
        )
        or manifest.get(
            "generation_id"
        )
    )

    if not generation_id:
        raise ValueError(
            "Generation result does not "
            "contain generation_id."
        )

    model_ready = (
        manifest.get(
            "model_ready"
        )
        or {}
    )

    model_ready_rows = (
        raw_result.get(
            "model_ready_rows"
        )
    )

    if model_ready_rows is None:
        model_ready_rows = (
            model_ready.get(
                "rows"
            )
        )

    return {
        "status": "completed",

        "generation_id": (
            generation_id
        ),

        "cell_count": int(
            raw_result.get(
                "cell_count",
                manifest.get(
                    "cell_count",
                    0,
                ),
            )
        ),

        "seed": int(
            raw_result.get(
                "seed",
                manifest.get(
                    "seed",
                    0,
                ),
            )
        ),

        "eligible_cell_count": int(
            raw_result.get(
                "eligible_cell_count",
                manifest.get(
                    "eligible_cell_count",
                    0,
                ),
            )
        ),

        "coverage_threshold": float(
            manifest.get(
                "coverage_threshold",
                0.0,
            )
        ),

        "resolution_minutes": int(
            manifest.get(
                "resolution_minutes",
                15,
            )
        ),

        "history_start": str(
            manifest.get(
                "history_start",
                "",
            )
        ),

        "history_end": str(
            manifest.get(
                "history_end",
                "",
            )
        ),

        "cutoff": str(
            manifest.get(
                "cutoff",
                manifest.get(
                    "history_end",
                    "",
                ),
            )
        ),

        "ground_truth_start": str(
            manifest.get(
                "ground_truth_start",
                "",
            )
        ),

        "ground_truth_end": str(
            manifest.get(
                "ground_truth_end",
                "",
            )
        ),

        "forecast_input_rows": int(
            raw_result.get(
                "forecast_input_rows",
                manifest.get(
                    "forecast_input_rows",
                    0,
                ),
            )
        ),

        "ground_truth_rows": int(
            raw_result.get(
                "ground_truth_rows",
                manifest.get(
                    "ground_truth_rows",
                    0,
                ),
            )
        ),

        "model_ready_rows": (
            int(
                model_ready_rows
            )
            if model_ready_rows
            is not None
            else None
        ),

        "minimum_history_coverage": float(
            manifest.get(
                "minimum_selected_history_coverage",
                0.0,
            )
        ),

        "minimum_ground_truth_coverage": float(
            manifest.get(
                "minimum_selected_ground_truth_coverage",
                0.0,
            )
        ),

        "cells": list(
            manifest.get(
                "selected_cells",
                [],
            )
        ),

        "forecast_input_download": (
            f"/api/dataset-generator/"
            f"{generation_id}/"
            f"forecast-input"
        ),

        "ground_truth_download": (
            f"/api/dataset-generator/"
            f"{generation_id}/"
            f"ground-truth"
        ),

        "manifest_download": (
            f"/api/dataset-generator/"
            f"{generation_id}/"
            f"manifest"
        ),

        "artifacts": (
            raw_result.get(
                "artifacts",
                {},
            )
        ),

        "runtime_seconds": (
            raw_result.get(
                "runtime_seconds",
                {},
            )
        ),
    }


def _frontend_forecast_response(
    raw_result: dict,
    manifest: dict,
):
    generation_id = (
        raw_result.get(
            "generation_id"
        )
    )

    run_id = (
        raw_result.get(
            "run_id"
        )
    )

    if not run_id:
        raise ValueError(
            "Forecast result does not "
            "contain run_id."
        )

    selected_cells = list(
        manifest.get(
            "selected_cells",
            [],
        )
    )

    runtime = (
        raw_result.get(
            "runtime_seconds"
        )
        or {}
    )

    calls = (
        raw_result.get(
            "calls"
        )
        or {}
    )

    return {
        "status": (
            raw_result.get(
                "status",
                "completed",
            )
        ),

        "run_id": run_id,

        "engine": (
            raw_result.get(
                "engine"
            )
        ),

        "generation_id": (
            generation_id
        ),

        "source_type": (
            "generated"
        ),

        "input_filename": (
            f"generated_"
            f"{generation_id}_"
            f"forecast_input.csv"
        ),

        "horizon_steps": int(
            raw_result.get(
                "horizon_steps",
                96,
            )
        ),

        "horizon_minutes": int(
            raw_result.get(
                "horizon_minutes",
                1440,
            )
        ),

        "input_rows": int(
            raw_result.get(
                "input_rows",
                0,
            )
        ),

        "input_date_range": {
            "start": (
                manifest.get(
                    "history_start"
                )
            ),
            "end": (
                manifest.get(
                    "history_end"
                )
            ),
        },

        "total_cells": int(
            raw_result.get(
                "total_cells",
                len(
                    selected_cells
                ),
            )
        ),

        "successful_cells": int(
            raw_result.get(
                "successful_cells",
                0,
            )
        ),

        "failed_cells": int(
            raw_result.get(
                "failed_cells",
                0,
            )
        ),

        "kpis": list(
            raw_result.get(
                "kpis",
                [],
            )
        ),

        "cells": (
            selected_cells
        ),

        "forecast_rows": int(
            raw_result.get(
                "forecast_rows",
                0,
            )
        ),

        "forecast_signature": (
            raw_result.get(
                "forecast_signature",
                ""
            )
        ),

        "output_columns": list(
            raw_result.get(
                "output_columns",
                [],
            )
        ),

        "runtime_seconds": {
            "preprocessing": float(
                runtime.get(
                    "preprocessing",
                    0.0,
                )
            ),

            "forecast_engine": float(
                runtime.get(
                    "forecast_engine",
                    0.0,
                )
            ),

            "total": float(
                runtime.get(
                    "total",
                    0.0,
                )
            ),
        },

        "calls": {
            "forecast_model_predict": int(
                calls.get(
                    "forecast_model_predict",
                    0,
                )
            ),

            "recursive_state_update": int(
                calls.get(
                    "recursive_state_update",
                    0,
                )
            ),

            "clustering_predict": int(
                calls.get(
                    "clustering_predict",
                    0,
                )
            ),
        },

        "preview": [],

        "download_url": (
            f"/forecast/"
            f"{run_id}/csv"
        ),

        "forecast_start": (
            manifest.get(
                "ground_truth_start"
            )
        ),

        "forecast_end": (
            manifest.get(
                "ground_truth_end"
            )
        ),

        "artifacts": (
            raw_result.get(
                "artifacts",
                {},
            )
        ),

        "model_ready_sha256": (
            raw_result.get(
                "model_ready_sha256"
            )
        ),
    }


def _validate_forecast_run_id(
    run_id: str,
):
    clean_run_id = (
        run_id.strip()
    )

    if (
        not clean_run_id.startswith(
            "FR-"
        )
        or "/"
        in clean_run_id
        or "\\"
        in clean_run_id
        or ".."
        in clean_run_id
    ):
        raise ValueError(
            "Invalid forecast run_id."
        )

    return clean_run_id


def _iter_bytes(
    payload: bytes,
    chunk_size: int = 1024 * 1024,
):
    for offset in range(
        0,
        len(payload),
        chunk_size,
    ):
        yield payload[
            offset:
            offset + chunk_size
        ]


def _ndjson_event(
    event_type: str,
    data,
) -> bytes:
    """Build one NDJSON streaming chunk.

    Small HTTP chunks may be buffered by the browser/proxy stack.
    Padding every progress event to a minimum chunk size forces the
    event to become visible to ``ReadableStream.getReader()`` while
    the request is still running.  The frontend trims whitespace
    before JSON parsing, so the padding is transport-only.
    """

    payload = json.dumps(
        {
            "type": event_type,
            "data": data,
        },
        ensure_ascii=False,
        default=str,
    ).encode(
        "utf-8"
    )

    # 8 KiB is intentionally larger than the common buffering
    # thresholds used by browsers and reverse proxies.  Forecast
    # progress still remains comfortably below normal response-size
    # limits because only status metadata is streamed.
    minimum_chunk_bytes = 8 * 1024

    padding_length = max(
        0,
        minimum_chunk_bytes
        - len(payload)
        - 1,
    )

    return (
        payload
        + (b" " * padding_length)
        + b"\n"
    )


def _sse_event(
    event_type: str,
    data,
) -> str:
    """Build one Server-Sent Events message."""
    payload = json.dumps(
        {
            "type": event_type,
            "data": data,
        },
        ensure_ascii=False,
        default=str,
    )

    return (
        f"data: {payload}\n\n"
    )


@router.post(
    "/api/session/cleanup"
)
async def cleanup_session_artifacts(
    payload: SessionCleanupRequest,
):
    try:
        paths = _session_blob_paths(
            payload.generation_id,
            payload.forecast_run_id,
        )

        deleted_count = (
            await run_in_threadpool(
                _delete_blob_paths_sync,
                paths,
            )
        )

        gc.collect()

        return {
            "status": "completed",
            "deleted_count": (
                deleted_count
            ),
        }

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


@router.post(
    "/api/dataset-generator/generate/stream"
)
async def generate_dataset_stream(
    payload: DatasetGenerateRequest,
):
    async def event_stream():
        loop = (
            asyncio.get_running_loop()
        )

        queue: asyncio.Queue = (
            asyncio.Queue()
        )

        def on_progress(
            progress: dict,
        ):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "progress",
                    progress,
                ),
            )

        async def worker():
            try:
                cleanup_result = (
                    await _cleanup_expired_working_blobs()
                )

                raw_result = (
                    await generate_dataset_from_blob(
                        cell_count=(
                            payload.cell_count
                        ),
                        seed=(
                            payload.seed
                        ),
                        progress_callback=(
                            on_progress
                        ),
                    )
                )

                manifest_path = (
                    _manifest_path_from_generation(
                        raw_result
                    )
                )

                manifest = (
                    await _read_json_blob(
                        manifest_path
                    )
                )

                result = (
                    _frontend_generation_response(
                        raw_result,
                        manifest,
                    )
                )

                result[
                    "cleanup"
                ] = cleanup_result

                await queue.put(
                    (
                        "result",
                        result,
                    )
                )

            except Exception as exc:
                await queue.put(
                    (
                        "error",
                        {
                            "message": (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                        },
                    )
                )

            finally:
                await queue.put(
                    (
                        "done",
                        None,
                    )
                )

        task = asyncio.create_task(
            worker()
        )

        yield _ndjson_event(
            "connected",
            {
                "status": "running",
            },
        )

        try:
            while True:
                event_type, data = (
                    await queue.get()
                )

                if event_type == "done":
                    break

                yield _ndjson_event(
                    event_type,
                    data,
                )

        finally:
            if not task.done():
                task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            gc.collect()

    return StreamingResponse(
        event_stream(),
        media_type=(
            "application/x-ndjson"
        ),
        headers={
            "Cache-Control": (
                "no-cache, no-store, no-transform"
            ),
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": (
                "nosniff"
            ),
        },
    )


@router.get(
    "/api/dataset-generator/generate/events"
)
async def generate_dataset_events(
    cell_count: int = Query(
        100,
        ge=1,
        le=2000,
    ),
    seed: int | None = Query(
        None,
        ge=0,
        le=2_147_483_647,
    ),
):
    """Generate a dataset and stream real progress with native SSE."""

    async def event_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_progress(
            progress: dict,
        ):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "progress",
                    progress,
                ),
            )

        async def worker():
            try:
                cleanup_result = (
                    await _cleanup_expired_working_blobs()
                )

                raw_result = (
                    await generate_dataset_from_blob(
                        cell_count=cell_count,
                        seed=seed,
                        progress_callback=(
                            on_progress
                        ),
                    )
                )

                manifest_path = (
                    _manifest_path_from_generation(
                        raw_result
                    )
                )

                manifest = (
                    await _read_json_blob(
                        manifest_path
                    )
                )

                result = (
                    _frontend_generation_response(
                        raw_result,
                        manifest,
                    )
                )

                result["cleanup"] = (
                    cleanup_result
                )

                await queue.put(
                    (
                        "result",
                        result,
                    )
                )

            except Exception as exc:
                await queue.put(
                    (
                        "error",
                        {
                            "message": (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                        },
                    )
                )

            finally:
                await queue.put(
                    (
                        "done",
                        None,
                    )
                )

        task = asyncio.create_task(
            worker()
        )

        # Native EventSource receives this immediately and keeps
        # the connection open while backend progress is produced.
        yield _sse_event(
            "connected",
            {
                "status": "running",
            },
        )

        try:
            while True:
                event_type, data = (
                    await queue.get()
                )

                if event_type == "done":
                    break

                yield _sse_event(
                    event_type,
                    data,
                )

        finally:
            if not task.done():
                task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            gc.collect()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": (
                "no-cache, no-store, no-transform"
            ),
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": (
                "nosniff"
            ),
        },
    )


@router.post(
    "/api/dataset-generator/generate"
)
async def generate_dataset(
    payload: DatasetGenerateRequest,
):
    try:
        await _cleanup_expired_working_blobs()

        raw_result = (
            await generate_dataset_from_blob(
                cell_count=(
                    payload.cell_count
                ),
                seed=(
                    payload.seed
                ),
            )
        )

        manifest_path = (
            _manifest_path_from_generation(
                raw_result
            )
        )

        manifest = (
            await _read_json_blob(
                manifest_path
            )
        )

        result = (
            _frontend_generation_response(
                raw_result,
                manifest,
            )
        )

        gc.collect()

        return result

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


@router.post(
    "/api/forecast/generated"
)
async def forecast_generated(
    payload: GeneratedForecastRequest,
):
    if (
        payload.horizon_steps
        not in {
            12,
            24,
            48,
            96,
        }
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "horizon_steps must be "
                "one of: 12, 24, 48, 96"
            ),
        )

    generation_id = (
        payload.generation_id.strip()
    )

    if (
        not generation_id.startswith(
            "GEN-"
        )
        or "/"
        in generation_id
        or "\\"
        in generation_id
        or ".."
        in generation_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid generation_id."
            ),
        )

    try:
        raw_result = (
            await forecast_generated_dataset(
                generation_id=(
                    generation_id
                ),
                horizon_steps=(
                    payload.horizon_steps
                ),
            )
        )

        manifest_path = (
            raw_result.get(
                "generation_manifest"
            )
            or (
                f"generations/"
                f"{generation_id}/"
                f"manifest.json"
            )
        )

        manifest = (
            await _read_json_blob(
                str(
                    manifest_path
                )
            )
        )

        result = (
            _frontend_forecast_response(
                raw_result,
                manifest,
            )
        )

        gc.collect()

        return result

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


@router.post(
    "/api/forecast/generated/stream"
)
async def forecast_generated_stream(
    payload: GeneratedForecastRequest,
):
    if (
        payload.horizon_steps
        not in {
            12,
            24,
            48,
            96,
        }
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "horizon_steps must be "
                "one of: 12, 24, 48, 96"
            ),
        )

    generation_id = (
        payload.generation_id.strip()
    )

    if (
        not generation_id.startswith(
            "GEN-"
        )
        or "/"
        in generation_id
        or "\\"
        in generation_id
        or ".."
        in generation_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid generation_id."
            ),
        )

    async def event_stream():
        loop = (
            asyncio.get_running_loop()
        )

        queue: asyncio.Queue = (
            asyncio.Queue()
        )

        def on_progress(
            progress: dict,
        ):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "progress",
                    progress,
                ),
            )

        async def worker():
            try:
                raw_result = (
                    await forecast_generated_dataset(
                        generation_id=(
                            generation_id
                        ),
                        horizon_steps=(
                            payload.horizon_steps
                        ),
                        progress_callback=(
                            on_progress
                        ),
                    )
                )

                manifest_path = (
                    raw_result.get(
                        "generation_manifest"
                    )
                    or (
                        f"generations/"
                        f"{generation_id}/"
                        f"manifest.json"
                    )
                )

                manifest = (
                    await _read_json_blob(
                        str(
                            manifest_path
                        )
                    )
                )

                result = (
                    _frontend_forecast_response(
                        raw_result,
                        manifest,
                    )
                )

                await queue.put(
                    (
                        "progress",
                        {
                            "status": "completed",
                            "run_id": result[
                                "run_id"
                            ],
                            "stage": "completed",
                            "stage_label": (
                                "Completed"
                            ),
                            "current_step": int(
                                result[
                                    "horizon_steps"
                                ]
                            ),
                            "total_steps": int(
                                result[
                                    "horizon_steps"
                                ]
                            ),
                            "active_cells": int(
                                result[
                                    "successful_cells"
                                ]
                            ),
                            "total_cells": int(
                                result[
                                    "total_cells"
                                ]
                            ),
                            "rows_generated": int(
                                result[
                                    "forecast_rows"
                                ]
                            ),
                            "expected_rows": (
                                int(
                                    result[
                                        "total_cells"
                                    ]
                                )
                                * int(
                                    result[
                                        "horizon_steps"
                                    ]
                                )
                            ),
                            "failed_cells": int(
                                result[
                                    "failed_cells"
                                ]
                            ),
                            "progress_percent": 100.0,
                            "elapsed_seconds": float(
                                result[
                                    "runtime_seconds"
                                ].get(
                                    "total",
                                    0.0,
                                )
                            ),
                            "result": None,
                            "error": None,
                        },
                    )
                )

                await queue.put(
                    (
                        "result",
                        result,
                    )
                )

            except Exception as exc:
                await queue.put(
                    (
                        "error",
                        {
                            "message": (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                        },
                    )
                )

            finally:
                await queue.put(
                    (
                        "done",
                        None,
                    )
                )

        task = asyncio.create_task(
            worker()
        )

        # Send one small event immediately so the browser
        # receives the streaming response headers without
        # waiting for the first backend progress callback.
        yield _ndjson_event(
            "connected",
            {
                "status": "running",
            },
        )

        try:
            while True:
                event_type, data = (
                    await queue.get()
                )

                if event_type == "done":
                    break

                yield _ndjson_event(
                    event_type,
                    data,
                )

        finally:
            if not task.done():
                task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            gc.collect()

    return StreamingResponse(
        event_stream(),
        media_type=(
            "application/x-ndjson"
        ),
        headers={
            "Cache-Control": (
                "no-cache, no-store, no-transform"
            ),
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": (
                "nosniff"
            ),
        },
    )


@router.get(
    "/api/forecast/generated/events"
)
async def forecast_generated_events(
    generation_id: str = Query(
        ...,
        min_length=5,
    ),
    horizon_steps: int = Query(
        96,
    ),
):
    """Run generated-data forecasting and stream real progress with SSE."""

    generation_id = (
        generation_id.strip()
    )

    if (
        horizon_steps
        not in {
            12,
            24,
            48,
            96,
        }
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "horizon_steps must be "
                "one of: 12, 24, 48, 96"
            ),
        )

    if (
        not generation_id.startswith(
            "GEN-"
        )
        or "/"
        in generation_id
        or "\\"
        in generation_id
        or ".."
        in generation_id
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Invalid generation_id."
            ),
        )

    async def event_stream():
        loop = (
            asyncio.get_running_loop()
        )

        queue: asyncio.Queue = (
            asyncio.Queue()
        )

        def on_progress(
            progress: dict,
        ):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                (
                    "progress",
                    progress,
                ),
            )

        async def worker():
            try:
                raw_result = (
                    await forecast_generated_dataset(
                        generation_id=(
                            generation_id
                        ),
                        horizon_steps=(
                            horizon_steps
                        ),
                        progress_callback=(
                            on_progress
                        ),
                    )
                )

                manifest_path = (
                    raw_result.get(
                        "generation_manifest"
                    )
                    or (
                        f"generations/"
                        f"{generation_id}/"
                        f"manifest.json"
                    )
                )

                manifest = (
                    await _read_json_blob(
                        str(
                            manifest_path
                        )
                    )
                )

                result = (
                    _frontend_forecast_response(
                        raw_result,
                        manifest,
                    )
                )

                await queue.put(
                    (
                        "progress",
                        {
                            "status": "completed",
                            "run_id": result[
                                "run_id"
                            ],
                            "stage": "completed",
                            "stage_label": (
                                "Completed"
                            ),
                            "current_step": int(
                                result[
                                    "horizon_steps"
                                ]
                            ),
                            "total_steps": int(
                                result[
                                    "horizon_steps"
                                ]
                            ),
                            "active_cells": int(
                                result[
                                    "successful_cells"
                                ]
                            ),
                            "total_cells": int(
                                result[
                                    "total_cells"
                                ]
                            ),
                            "rows_generated": int(
                                result[
                                    "forecast_rows"
                                ]
                            ),
                            "expected_rows": (
                                int(
                                    result[
                                        "total_cells"
                                    ]
                                )
                                * int(
                                    result[
                                        "horizon_steps"
                                    ]
                                )
                            ),
                            "failed_cells": int(
                                result[
                                    "failed_cells"
                                ]
                            ),
                            "progress_percent": 100.0,
                            "elapsed_seconds": float(
                                result[
                                    "runtime_seconds"
                                ].get(
                                    "total",
                                    0.0,
                                )
                            ),
                            "result": None,
                            "error": None,
                        },
                    )
                )

                await queue.put(
                    (
                        "result",
                        result,
                    )
                )

            except Exception as exc:
                await queue.put(
                    (
                        "error",
                        {
                            "message": (
                                f"{type(exc).__name__}: "
                                f"{exc}"
                            ),
                        },
                    )
                )

            finally:
                await queue.put(
                    (
                        "done",
                        None,
                    )
                )

        task = asyncio.create_task(
            worker()
        )

        # Send one event immediately so EventSource establishes
        # the live connection before forecasting begins.
        yield _sse_event(
            "connected",
            {
                "status": "running",
            },
        )

        try:
            while True:
                event_type, data = (
                    await queue.get()
                )

                if event_type == "done":
                    break

                yield _sse_event(
                    event_type,
                    data,
                )

        finally:
            if not task.done():
                task.cancel()

            try:
                await task
            except asyncio.CancelledError:
                pass

            gc.collect()

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": (
                "no-cache, no-store, no-transform"
            ),
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": (
                "nosniff"
            ),
        },
    )


@router.get(
    "/api/forecast/{run_id}/csv"
)
async def forecast_csv(
    run_id: str,
):
    try:
        clean_run_id = (
            _validate_forecast_run_id(
                run_id
            )
        )

        pathname = (
            f"forecast-runs/"
            f"{clean_run_id}/"
            f"forecast.csv"
        )

        async with AsyncBlobClient() as client:
            result = await client.get(
                pathname,
                access="private",
                timeout=120,
            )

        if result is None:
            raise FileNotFoundError(
                f"Forecast CSV not found: "
                f"{clean_run_id}"
            )

        content = result.content

        if isinstance(
            content,
            bytes,
        ):
            payload = content
        elif isinstance(
            content,
            bytearray,
        ):
            payload = bytes(
                content
            )
        else:
            payload = str(
                content
            ).encode(
                "utf-8"
            )

        filename = (
            f"{clean_run_id}_forecast.csv"
        )

        response = StreamingResponse(
            _iter_bytes(
                payload
            ),
            media_type=(
                "text/csv; charset=utf-8"
            ),
            headers={
                "Content-Disposition": (
                    f'attachment; '
                    f'filename="{filename}"'
                ),
                "Cache-Control": (
                    "private, no-store"
                ),
                "X-Content-Type-Options": (
                    "nosniff"
                ),
            },
        )

        gc.collect()

        return response

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


@router.get(
    "/api/forecast/{run_id}/chart"
)
async def forecast_chart(
    run_id: str,
    cell_name: str = Query(
        ...,
        min_length=1,
    ),
    kpi: str = Query(
        ...,
        min_length=1,
    ),
    history_points: int = Query(
        96,
        ge=1,
        le=500,
    ),
):
    try:
        result = (
            await get_forecast_chart_data(
                run_id=run_id,
                cell_name=cell_name,
                kpi=kpi,
                history_points=(
                    history_points
                ),
            )
        )

        gc.collect()

        return result

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc

@router.get("/api/validation/{validation_id}/chart")
async def validation_chart(
    validation_id: str,
    cell_name: str = Query(..., min_length=1),
    kpi: str = Query(..., min_length=1),
):
    try:
        return await get_validation_chart_data(validation_id, cell_name, kpi)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Validation run not found.") from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail="Could not load validation chart.") from exc
