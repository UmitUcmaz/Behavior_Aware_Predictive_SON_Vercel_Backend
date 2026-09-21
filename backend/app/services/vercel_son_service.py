from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import gc
import json
import shutil
import tempfile
import threading
import time

import pandas as pd

from fastapi.concurrency import run_in_threadpool
from vercel.blob import AsyncBlobClient

from backend.app.services import (
    son_service,
)


FORECAST_RUNS_BLOB_PREFIX = "forecast-runs"
SON_RUNS_BLOB_PREFIX = "son-runs"

FORECAST_FILENAME = "forecast.csv"
RECOMMENDATIONS_FILENAME = "recommendations.csv"
SUMMARY_FILENAME = "summary.json"

SON_LOCK = threading.Lock()


def _validate_run_id(
    run_id: str,
) -> str:
    run_id = str(run_id).strip()

    if (
        not run_id.startswith("FR-")
        or "/" in run_id
        or "\\" in run_id
        or ".." in run_id
    ):
        raise ValueError(
            "Invalid forecast run_id."
        )

    return run_id


async def _download_blob_bytes(
    pathname: str,
) -> bytes:
    async with AsyncBlobClient() as client:
        result = await client.get(
            pathname,
            access="private",
            timeout=120,
        )

    if result is None:
        raise FileNotFoundError(
            f"Blob not found: {pathname}"
        )

    if result.status_code != 200:
        raise RuntimeError(
            "Blob download failed: "
            f"{pathname} "
            f"(HTTP {result.status_code})"
        )

    if not result.content:
        raise RuntimeError(
            f"Blob is empty: {pathname}"
        )

    return result.content


def _run_existing_son_service(
    run_id: str,
    temporary_runs_dir: Path,
    rules: dict | None,
):
    original_runs_dir = (
        son_service.RUNS_DIR
    )

    try:
        with SON_LOCK:
            son_service.RUNS_DIR = (
                temporary_runs_dir
            )

            return (
                son_service.evaluate_son_run(
                    run_id,
                    rules,
                )
            )

    finally:
        son_service.RUNS_DIR = (
            original_runs_dir
        )


async def evaluate_son_blob_run(
    run_id: str,
    rules: dict | None = None,
):
    request_started = time.perf_counter()

    run_id = _validate_run_id(
        run_id
    )

    forecast_blob_pathname = (
        f"{FORECAST_RUNS_BLOB_PREFIX}/"
        f"{run_id}/"
        f"{FORECAST_FILENAME}"
    )

    download_started = (
        time.perf_counter()
    )

    forecast_bytes = (
        await _download_blob_bytes(
            forecast_blob_pathname
        )
    )

    blob_download_seconds = (
        time.perf_counter()
        - download_started
    )

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="baps-son-",
            dir=tempfile.gettempdir(),
        )
    )

    temporary_runs_dir = (
        work_dir
        / "runs"
    )

    run_dir = (
        temporary_runs_dir
        / run_id
    )

    run_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    forecast_path = (
        run_dir
        / FORECAST_FILENAME
    )

    forecast_path.write_bytes(
        forecast_bytes
    )

    del forecast_bytes
    gc.collect()

    try:
        evaluate_started = (
            time.perf_counter()
        )

        result = await run_in_threadpool(
            _run_existing_son_service,
            run_id,
            temporary_runs_dir,
            rules,
        )

        evaluate_seconds = (
            time.perf_counter()
            - evaluate_started
        )

        son_id = datetime.now(
            timezone.utc
        ).strftime(
            "SON-%Y%m%dT%H%M%S%fZ"
        )

        recommendations = (
            result.get(
                "recommendations",
                [],
            )
        )

        recommendation_columns = [
            "cell_name",
            "recommendation",
            "module_label",
            "triggering_condition",
            "time_window",
            "recommended_action",
            "evidence",
        ]

        recommendations_df = (
            pd.DataFrame(
                recommendations,
                columns=(
                    recommendation_columns
                ),
            )
        )

        recommendations_path = (
            work_dir
            / RECOMMENDATIONS_FILENAME
        )

        summary_path = (
            work_dir
            / SUMMARY_FILENAME
        )

        recommendations_df.to_csv(
            recommendations_path,
            index=False,
        )

        response = {
            **result,
            "son_id": son_id,
            "source": (
                "vercel-private-blob"
            ),
            "forecast_blob_pathname": (
                forecast_blob_pathname
            ),
        }

        summary_path.write_text(
            json.dumps(
                response,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        son_prefix = (
            f"{SON_RUNS_BLOB_PREFIX}/"
            f"{son_id}"
        )

        recommendations_blob_pathname = (
            f"{son_prefix}/"
            f"{RECOMMENDATIONS_FILENAME}"
        )

        summary_blob_pathname = (
            f"{son_prefix}/"
            f"{SUMMARY_FILENAME}"
        )

        upload_started = (
            time.perf_counter()
        )

        async with AsyncBlobClient() as client:
            recommendations_blob = (
                await client.upload_file(
                    str(
                        recommendations_path
                    ),
                    recommendations_blob_pathname,
                    access="private",
                    add_random_suffix=False,
                    overwrite=False,
                    multipart=(
                        recommendations_path
                        .stat()
                        .st_size
                        >= 5
                        * 1024
                        * 1024
                    ),
                )
            )

            summary_blob = (
                await client.upload_file(
                    str(
                        summary_path
                    ),
                    summary_blob_pathname,
                    access="private",
                    add_random_suffix=False,
                    overwrite=False,
                    multipart=False,
                )
            )

        blob_upload_seconds = (
            time.perf_counter()
            - upload_started
        )

        response[
            "artifacts"
        ] = {
            "recommendations": {
                "pathname": (
                    recommendations_blob
                    .pathname
                ),
                "size": (
                    recommendations_path
                    .stat()
                    .st_size
                ),
            },
            "summary": {
                "pathname": (
                    summary_blob.pathname
                ),
                "size": (
                    summary_path
                    .stat()
                    .st_size
                ),
            },
        }

        response[
            "runtime_seconds"
        ] = {
            "blob_download": round(
                blob_download_seconds,
                4,
            ),
            "son_evaluation": round(
                evaluate_seconds,
                4,
            ),
            "blob_upload": round(
                blob_upload_seconds,
                4,
            ),
            "total": round(
                time.perf_counter()
                - request_started,
                4,
            ),
        }

        return response

    finally:
        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )

        gc.collect()