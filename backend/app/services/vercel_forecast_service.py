from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import gc
import hashlib
import json
import shutil
import tempfile
import time
from typing import Callable

import pandas as pd
from fastapi.concurrency import run_in_threadpool
from vercel.blob import AsyncBlobClient

from ml_engine.forecast_engine import (
    ENGINE_VERSION,
    ForecastEngine,
)


GENERATIONS_BLOB_PREFIX = "generations"
FORECAST_RUNS_BLOB_PREFIX = "forecast-runs"

MODEL_READY_FILENAME = (
    "model_ready_forecast_input.csv"
)

MANIFEST_FILENAME = "manifest.json"

FORECAST_FILENAME = "forecast.csv"
RUN_METADATA_FILENAME = "run_metadata.json"


ProgressCallback = Callable[[dict], None]


def _emit_progress(
    callback: ProgressCallback | None,
    payload: dict,
):
    if callback is None:
        return

    try:
        callback(payload)
    except Exception:
        # Progress reporting must never break forecasting.
        pass


def _validate_generation_id(
    generation_id: str,
) -> str:
    generation_id = str(
        generation_id
    ).strip()

    if (
        not generation_id.startswith("GEN-")
        or "/" in generation_id
        or "\\" in generation_id
        or ".." in generation_id
    ):
        raise ValueError(
            "Invalid generation_id."
        )

    return generation_id


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


def _build_engine() -> ForecastEngine:
    return ForecastEngine(
        load_clustering=False,
        inspect_runtime=False,
    )


async def forecast_generated_dataset(
    generation_id: str,
    horizon_steps: int = 96,
    progress_callback: ProgressCallback | None = None,
):
    request_started = time.perf_counter()

    generation_id = (
        _validate_generation_id(
            generation_id
        )
    )

    horizon_steps = int(
        horizon_steps
    )

    if horizon_steps not in {
        12,
        24,
        48,
        96,
    }:
        raise ValueError(
            "horizon_steps must be one of: "
            "12, 24, 48, 96"
        )

    generation_prefix = (
        f"{GENERATIONS_BLOB_PREFIX}/"
        f"{generation_id}"
    )

    manifest_pathname = (
        f"{generation_prefix}/"
        f"{MANIFEST_FILENAME}"
    )

    model_ready_pathname = (
        f"{generation_prefix}/"
        f"{MODEL_READY_FILENAME}"
    )

    download_started = (
        time.perf_counter()
    )

    manifest_bytes = (
        await _download_blob_bytes(
            manifest_pathname
        )
    )

    model_ready_bytes = (
        await _download_blob_bytes(
            model_ready_pathname
        )
    )

    blob_download_seconds = (
        time.perf_counter()
        - download_started
    )

    manifest = json.loads(
        manifest_bytes.decode("utf-8")
    )

    if (
        manifest.get("generation_id")
        != generation_id
    ):
        raise ValueError(
            "Generation manifest ID mismatch."
        )

    artifact = manifest.get(
        "model_ready"
    )

    if not artifact:
        raise ValueError(
            "Model-ready metadata missing "
            "from generation manifest."
        )

    if int(
        artifact.get("version", 0)
    ) != 1:
        raise ValueError(
            "Unsupported model-ready version."
        )

    manifest_cell_count = int(
        artifact.get(
            "cell_count",
            manifest.get(
                "cell_count",
                0,
            ),
        )
        or 0
    )

    _emit_progress(
        progress_callback,
        {
            "status": "running",
            "run_id": "",
            "stage": "feature_engineering",
            "stage_label": "Preparing Forecast Input",
            "current_step": 0,
            "total_steps": horizon_steps,
            "active_cells": manifest_cell_count,
            "total_cells": manifest_cell_count,
            "rows_generated": 0,
            "expected_rows": (
                manifest_cell_count
                * horizon_steps
            ),
            "failed_cells": 0,
            "progress_percent": 0.5,
            "elapsed_seconds": round(
                time.perf_counter()
                - request_started,
                2,
            ),
        },
    )

    expected_sha256 = str(
        artifact.get("sha256", "")
    ).strip()

    actual_sha256 = hashlib.sha256(
        model_ready_bytes
    ).hexdigest()

    if (
        not expected_sha256
        or actual_sha256
        != expected_sha256
    ):
        raise ValueError(
            "Model-ready artifact "
            "SHA256 mismatch."
        )

    history_max = pd.Timestamp(
        manifest[
            "history_max_timestamp"
        ]
    )

    ground_truth_min = pd.Timestamp(
        manifest[
            "ground_truth_min_timestamp"
        ]
    )

    if not (
        history_max
        < ground_truth_min
    ):
        raise ValueError(
            "DATA LEAKAGE: invalid "
            "history / ground-truth boundary."
        )

    load_started = time.perf_counter()

    ready = pd.read_csv(
        BytesIO(
            model_ready_bytes
        ),
        float_precision="round_trip",
    )

    del model_ready_bytes
    gc.collect()

    dataset_load_seconds = (
        time.perf_counter()
        - load_started
    )

    expected_columns = list(
        artifact.get(
            "columns",
            [],
        )
    )

    if (
        expected_columns
        and list(
            ready.columns
        ) != expected_columns
    ):
        raise ValueError(
            "Model-ready column "
            "schema mismatch."
        )

    expected_rows = int(
        artifact.get(
            "rows",
            -1,
        )
    )

    if (
        expected_rows >= 0
        and len(ready)
        != expected_rows
    ):
        raise ValueError(
            "Model-ready row "
            "count mismatch."
        )

    cell_col = str(
        artifact.get(
            "cell_column",
            "CELL_NAME",
        )
    )

    time_col = str(
        artifact.get(
            "time_column",
            "SDATE",
        )
    )

    kpis = list(
        artifact.get(
            "kpis",
            [],
        )
    )

    if not kpis:
        raise ValueError(
            "Model-ready KPI metadata "
            "is missing."
        )

    if cell_col not in ready.columns:
        raise ValueError(
            f"Cell column missing: "
            f"{cell_col}"
        )

    if time_col not in ready.columns:
        raise ValueError(
            f"Time column missing: "
            f"{time_col}"
        )

    ready[time_col] = pd.to_datetime(
        ready[time_col],
        format="mixed",
        errors="raise",
    )

    if ready[time_col].max() > history_max:
        raise ValueError(
            "DATA LEAKAGE: model-ready "
            "history exceeds cutoff."
        )

    total_cells = int(
        ready[cell_col].nunique(
            dropna=False
        )
    )

    expected_forecast_rows = (
        total_cells
        * horizon_steps
    )

    _emit_progress(
        progress_callback,
        {
            "status": "running",
            "run_id": "",
            "stage": "feature_engineering",
            "stage_label": "Forecast Input Ready",
            "current_step": 0,
            "total_steps": horizon_steps,
            "active_cells": total_cells,
            "total_cells": total_cells,
            "rows_generated": 0,
            "expected_rows": expected_forecast_rows,
            "failed_cells": 0,
            "progress_percent": 1.0,
            "elapsed_seconds": round(
                time.perf_counter()
                - request_started,
                2,
            ),
        },
    )

    engine = _build_engine()

    def engine_progress(
        event: dict,
    ):
        stage = str(
            event.get(
                "stage",
                "recursive_forecasting",
            )
        )

        stage_labels = {
            "feature_engineering": (
                "Preparing Forecast Engine"
            ),
            "recursive_forecasting": (
                "Recursive Forecasting"
            ),
            "finalizing": (
                "Finalizing Forecast Output"
            ),
        }

        raw_progress = float(
            event.get(
                "progress_percent",
                0.0,
            )
            or 0.0
        )

        if stage == "feature_engineering":
            progress_percent = max(
                1.0,
                min(
                    raw_progress,
                    2.0,
                ),
            )
        elif stage == "finalizing":
            progress_percent = min(
                98.0,
                max(
                    raw_progress,
                    98.0,
                ),
            )
        else:
            progress_percent = min(
                raw_progress,
                97.5,
            )

        _emit_progress(
            progress_callback,
            {
                "status": "running",
                "run_id": "",
                "stage": stage,
                "stage_label": (
                    stage_labels.get(
                        stage,
                        "Running Forecast",
                    )
                ),
                "current_step": int(
                    event.get(
                        "current_step",
                        0,
                    )
                    or 0
                ),
                "total_steps": int(
                    event.get(
                        "total_steps",
                        horizon_steps,
                    )
                    or horizon_steps
                ),
                "active_cells": int(
                    event.get(
                        "active_cells",
                        total_cells,
                    )
                    or 0
                ),
                "total_cells": int(
                    event.get(
                        "total_cells",
                        total_cells,
                    )
                    or total_cells
                ),
                "rows_generated": int(
                    event.get(
                        "rows_generated",
                        0,
                    )
                    or 0
                ),
                "expected_rows": int(
                    event.get(
                        "expected_rows",
                        expected_forecast_rows,
                    )
                    or expected_forecast_rows
                ),
                "failed_cells": int(
                    event.get(
                        "failed_cells",
                        0,
                    )
                    or 0
                ),
                "progress_percent": round(
                    progress_percent,
                    2,
                ),
                "elapsed_seconds": round(
                    time.perf_counter()
                    - request_started,
                    2,
                ),
            },
        )

    forecast_started = (
        time.perf_counter()
    )

    result = await run_in_threadpool(
        engine.forecast,
        ready,
        horizon_steps,
        progress_callback=engine_progress,
        prepared_columns=(
            cell_col,
            time_col,
            kpis,
        ),
        resident_models=True,
    )

    forecast_seconds = (
        time.perf_counter()
        - forecast_started
    )

    run_id = datetime.now(
        timezone.utc
    ).strftime(
        "FR-%Y%m%dT%H%M%S%fZ"
    )

    _emit_progress(
        progress_callback,
        {
            "status": "running",
            "run_id": run_id,
            "stage": "finalizing",
            "stage_label": "Preparing Forecast Output",
            "current_step": horizon_steps,
            "total_steps": horizon_steps,
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
                * horizon_steps
            ),
            "failed_cells": int(
                result[
                    "failed_cells"
                ]
            ),
            "progress_percent": 98.0,
            "elapsed_seconds": round(
                time.perf_counter()
                - request_started,
                2,
            ),
        },
    )

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="baps-forecast-",
            dir=tempfile.gettempdir(),
        )
    )

    try:
        forecast_path = (
            work_dir
            / FORECAST_FILENAME
        )

        metadata_path = (
            work_dir
            / RUN_METADATA_FILENAME
        )

        result[
            "export_df"
        ].to_csv(
            forecast_path,
            index=False,
        )

        run_metadata = {
            "run_id": run_id,
            "status": "completed",
            "engine": ENGINE_VERSION,
            "source_type": "generated",
            "generation_id": (
                generation_id
            ),
            "horizon_steps": (
                horizon_steps
            ),
            "horizon_minutes": (
                horizon_steps * 15
            ),
            "input_rows": int(
                manifest[
                    "forecast_input_rows"
                ]
            ),
            "model_ready_rows": int(
                len(ready)
            ),
            "total_cells": int(
                result[
                    "total_cells"
                ]
            ),
            "successful_cells": int(
                result[
                    "successful_cells"
                ]
            ),
            "failed_cells": int(
                result[
                    "failed_cells"
                ]
            ),
            "forecast_rows": int(
                result[
                    "forecast_rows"
                ]
            ),
            "forecast_signature": (
                result["signature"]
            ),
            "kpis": list(
                result["kpis"]
            ),
            "output_columns": list(
                result[
                    "export_df"
                ].columns
            ),
            "generation_manifest": (
                manifest_pathname
            ),
            "generation_model_ready": (
                model_ready_pathname
            ),
            "model_ready_sha256": (
                actual_sha256
            ),
            "history_max_timestamp": str(
                history_max
            ),
            "ground_truth_min_timestamp": (
                str(
                    ground_truth_min
                )
            ),
        }

        metadata_path.write_text(
            json.dumps(
                run_metadata,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        run_prefix = (
            f"{FORECAST_RUNS_BLOB_PREFIX}/"
            f"{run_id}"
        )

        forecast_blob_pathname = (
            f"{run_prefix}/"
            f"{FORECAST_FILENAME}"
        )

        metadata_blob_pathname = (
            f"{run_prefix}/"
            f"{RUN_METADATA_FILENAME}"
        )

        _emit_progress(
            progress_callback,
            {
                "status": "running",
                "run_id": run_id,
                "stage": "finalizing",
                "stage_label": "Uploading Forecast Output",
                "current_step": horizon_steps,
                "total_steps": horizon_steps,
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
                    * horizon_steps
                ),
                "failed_cells": int(
                    result[
                        "failed_cells"
                    ]
                ),
                "progress_percent": 99.0,
                "elapsed_seconds": round(
                    time.perf_counter()
                    - request_started,
                    2,
                ),
            },
        )

        upload_started = (
            time.perf_counter()
        )

        async with AsyncBlobClient() as client:
            forecast_blob = (
                await client.upload_file(
                    str(
                        forecast_path
                    ),
                    forecast_blob_pathname,
                    access="private",
                    add_random_suffix=False,
                    overwrite=False,
                    multipart=(
                        forecast_path
                        .stat()
                        .st_size
                        >= 5
                        * 1024
                        * 1024
                    ),
                )
            )

            metadata_blob = (
                await client.upload_file(
                    str(
                        metadata_path
                    ),
                    metadata_blob_pathname,
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

        _emit_progress(
            progress_callback,
            {
                "status": "running",
                "run_id": run_id,
                "stage": "finalizing",
                "stage_label": "Forecast Output Stored",
                "current_step": horizon_steps,
                "total_steps": horizon_steps,
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
                    * horizon_steps
                ),
                "failed_cells": int(
                    result[
                        "failed_cells"
                    ]
                ),
                "progress_percent": 99.8,
                "elapsed_seconds": round(
                    time.perf_counter()
                    - request_started,
                    2,
                ),
            },
        )

        response = {
            **run_metadata,
            "artifacts": {
                "forecast": {
                    "pathname": (
                        forecast_blob.pathname
                    ),
                    "size": (
                        forecast_path
                        .stat()
                        .st_size
                    ),
                },
                "metadata": {
                    "pathname": (
                        metadata_blob.pathname
                    ),
                    "size": (
                        metadata_path
                        .stat()
                        .st_size
                    ),
                },
            },
            "runtime_seconds": {
                "blob_download": round(
                    blob_download_seconds,
                    4,
                ),
                "dataset_load": round(
                    dataset_load_seconds,
                    4,
                ),
                "preprocessing": round(
                    float(
                        result[
                            "preprocess_seconds"
                        ]
                    ),
                    4,
                ),
                "forecast_engine": round(
                    float(
                        result[
                            "forecast_seconds"
                        ]
                    ),
                    4,
                ),
                "endpoint_forecast": round(
                    forecast_seconds,
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
            },
            "calls": {
                "forecast_model_predict": int(
                    result[
                        "performance"
                    ][
                        "forecast"
                    ].get(
                        "model_predict_calls",
                        0,
                    )
                ),
                "recursive_state_update": int(
                    result[
                        "performance"
                    ][
                        "forecast"
                    ].get(
                        "state_update_calls",
                        0,
                    )
                ),
            },
        }

        return response

    finally:
        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )

        try:
            del result
        except Exception:
            pass

        try:
            del ready
        except Exception:
            pass

        gc.collect()