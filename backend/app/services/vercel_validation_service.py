from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import gc
import json
import re
import shutil
import tempfile
import time

import numpy as np
import pandas as pd

from vercel.blob import AsyncBlobClient

from ml_engine.forecast_engine import (
    ForecastMetadata,
)


FORECAST_RUNS_BLOB_PREFIX = "forecast-runs"
GENERATIONS_BLOB_PREFIX = "generations"
VALIDATION_RUNS_BLOB_PREFIX = "validation-runs"

FORECAST_FILENAME = "forecast.csv"
RUN_METADATA_FILENAME = "run_metadata.json"
GROUND_TRUTH_FILENAME = "ground_truth.csv"

VALIDATION_FILENAME = "validation_matched.csv"
SUMMARY_FILENAME = "summary.json"

MAX_ACTUAL_UPLOAD_BYTES = 50 * 1024 * 1024

ACTUAL_UPLOAD_PATTERN = re.compile(
    r"validation-runs/uploads/"
    r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-"
    r"[89ab][0-9a-f]{3}-[0-9a-f]{12}/actual\.csv"
)

ACTUAL_UPLOAD_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
}


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


def _validate_actual_upload_reference(
    pathname: str,
    filename: str,
) -> str:
    pathname = str(
        pathname
    ).strip()

    filename = str(
        filename
    ).strip()

    if not ACTUAL_UPLOAD_PATTERN.fullmatch(
        pathname
    ):
        raise ValueError(
            "Invalid uploaded actual CSV "
            "reference."
        )

    if (
        not filename.lower().endswith(
            ".csv"
        )
        or len(filename) > 255
        or re.search(
            r"[\\/\x00-\x1f]",
            filename,
        )
    ):
        raise ValueError(
            "Invalid actual CSV filename."
        )

    return pathname


def _safe_metric(
    value,
):
    if value is None:
        return None

    value = float(value)

    if not np.isfinite(value):
        return None

    return round(
        value,
        6,
    )


def _calculate_metrics(
    actual,
    forecast,
):
    actual = np.asarray(
        actual,
        dtype=float,
    )

    forecast = np.asarray(
        forecast,
        dtype=float,
    )

    mask = (
        np.isfinite(actual)
        & np.isfinite(forecast)
    )

    actual = actual[mask]
    forecast = forecast[mask]

    count = int(len(actual))

    if count == 0:
        return {
            "count": 0,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r2": None,
        }

    error = forecast - actual

    mae = np.mean(
        np.abs(error)
    )

    rmse = np.sqrt(
        np.mean(
            np.square(error)
        )
    )

    non_zero = (
        np.abs(actual)
        > 1e-12
    )

    if bool(non_zero.any()):
        mape = (
            np.mean(
                np.abs(
                    error[non_zero]
                    / actual[non_zero]
                )
            )
            * 100.0
        )
    else:
        mape = None

    if count >= 2:
        mean_actual = np.mean(
            actual
        )

        ss_res = np.sum(
            np.square(
                actual - forecast
            )
        )

        ss_tot = np.sum(
            np.square(
                actual - mean_actual
            )
        )

        r2 = (
            1.0
            - ss_res / ss_tot
            if ss_tot > 0
            else None
        )

    else:
        r2 = None

    return {
        "count": count,
        "mae": _safe_metric(mae),
        "rmse": _safe_metric(rmse),
        "mape": _safe_metric(mape),
        "r2": _safe_metric(r2),
    }


def _get_kpi_mapping():
    metadata = ForecastMetadata()

    mapping_df = metadata.mapping_df

    source_col = (
        "SOURCE_COLUMN"
        if "SOURCE_COLUMN"
        in mapping_df.columns
        else mapping_df.columns[0]
    )

    if (
        "CONFIRMED_ROLE"
        in mapping_df.columns
    ):
        role_col = "CONFIRMED_ROLE"

    elif (
        "STANDARDIZED_NAME"
        in mapping_df.columns
    ):
        role_col = "STANDARDIZED_NAME"

    else:
        role_col = "PROPOSED_KPI_ROLE"

    mapping = {}

    for _, row in mapping_df.iterrows():
        source = str(
            row[source_col]
        ).strip()

        role = str(
            row[role_col]
        ).strip()

        if (
            source
            and role
            and source.lower() != "nan"
            and role.lower() != "nan"
        ):
            mapping[role] = source

    return (
        metadata,
        mapping,
    )


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


async def _download_uploaded_actual_bytes(
    pathname: str,
    filename: str,
) -> bytes:
    pathname = (
        _validate_actual_upload_reference(
            pathname,
            filename,
        )
    )

    async with AsyncBlobClient() as client:
        info = await client.head(
            pathname
        )

    if (
        info.size <= 0
        or info.size
        > MAX_ACTUAL_UPLOAD_BYTES
    ):
        raise ValueError(
            "Actual CSV must be non-empty "
            "and no larger than 50 MiB."
        )

    content_type = (
        str(
            info.content_type
            or ""
        )
        .split(
            ";",
            1,
        )[0]
        .strip()
        .lower()
    )

    if (
        content_type
        not in ACTUAL_UPLOAD_CONTENT_TYPES
    ):
        raise ValueError(
            "Uploaded actual object must "
            "have CSV content type."
        )

    content = await _download_blob_bytes(
        pathname
    )

    if (
        len(content)
        > MAX_ACTUAL_UPLOAD_BYTES
    ):
        raise ValueError(
            "Actual CSV exceeds the "
            "50 MiB upload limit."
        )

    return content


async def validate_forecast_run(
    run_id: str,
    actual_pathname: str | None = None,
    actual_filename: str | None = None,
):
    request_started = time.perf_counter()

    run_id = _validate_run_id(
        run_id
    )

    run_prefix = (
        f"{FORECAST_RUNS_BLOB_PREFIX}/"
        f"{run_id}"
    )

    metadata_pathname = (
        f"{run_prefix}/"
        f"{RUN_METADATA_FILENAME}"
    )

    forecast_pathname = (
        f"{run_prefix}/"
        f"{FORECAST_FILENAME}"
    )

    download_started = (
        time.perf_counter()
    )

    metadata_bytes = (
        await _download_blob_bytes(
            metadata_pathname
        )
    )

    run_metadata = json.loads(
        metadata_bytes.decode("utf-8")
    )

    if (
        run_metadata.get("run_id")
        != run_id
    ):
        raise ValueError(
            "Forecast run metadata "
            "ID mismatch."
        )

    raw_generation_id = (
        run_metadata.get(
            "generation_id"
        )
    )

    generation_id = (
        str(
            raw_generation_id
        ).strip()
        if raw_generation_id
        else None
    )

    use_uploaded_actual = (
        actual_pathname is not None
        or actual_filename is not None
    )

    if use_uploaded_actual:
        if (
            not actual_pathname
            or not actual_filename
        ):
            raise ValueError(
                "Uploaded actual CSV requires "
                "both pathname and filename."
            )

        actual_source = (
            "uploaded_actual"
        )

        actual_source_label = (
            "Uploaded Actual Network Data"
        )

        resolved_actual_filename = (
            str(actual_filename).strip()
        )

    else:
        if not generation_id:
            raise ValueError(
                "Forecast run is not linked "
                "to a generated dataset. "
                "Upload actual network data "
                "for this forecast."
            )

        if (
            not generation_id.startswith(
                "GEN-"
            )
            or "/" in generation_id
            or "\\" in generation_id
            or ".." in generation_id
        ):
            raise ValueError(
                "Invalid generation_id in "
                "forecast metadata."
            )

        ground_truth_pathname = (
            f"{GENERATIONS_BLOB_PREFIX}/"
            f"{generation_id}/"
            f"{GROUND_TRUTH_FILENAME}"
        )

        actual_source = (
            "generated_ground_truth"
        )

        actual_source_label = (
            "Generated Ground Truth"
        )

        resolved_actual_filename = (
            GROUND_TRUTH_FILENAME
        )

    forecast_bytes = (
        await _download_blob_bytes(
            forecast_pathname
        )
    )

    if use_uploaded_actual:
        actual_bytes = (
            await _download_uploaded_actual_bytes(
                actual_pathname,
                actual_filename,
            )
        )

    else:
        actual_bytes = (
            await _download_blob_bytes(
                ground_truth_pathname
            )
        )

    blob_download_seconds = (
        time.perf_counter()
        - download_started
    )

    load_started = time.perf_counter()

    forecast_df = pd.read_csv(
        Path(
            tempfile.mkstemp(
                suffix=".csv"
            )[1]
        )
    ) if False else None

    from io import BytesIO

    forecast_df = pd.read_csv(
        BytesIO(forecast_bytes)
    )

    actual_df = pd.read_csv(
        BytesIO(actual_bytes)
    )

    del forecast_bytes
    del actual_bytes
    gc.collect()

    dataset_load_seconds = (
        time.perf_counter()
        - load_started
    )

    if actual_df.empty:
        raise ValueError(
            "Actual dataset contains "
            "no data rows."
        )

    validation_started = (
        time.perf_counter()
    )

    metadata, mapping = (
        _get_kpi_mapping()
    )

    time_col = metadata.schema.get(
        "selected_date_column",
        "SDATE",
    )

    cell_cols = metadata.schema.get(
        "cell_columns",
        [],
    )

    cell_col = (
        cell_cols[0]
        if cell_cols
        else "CELL_NAME"
    )

    kpis = [
        kpi
        for kpi in mapping
        if (
            f"{kpi}_FORECAST"
            in forecast_df.columns
        )
    ]

    if not kpis:
        raise ValueError(
            "No supported forecast KPI "
            "columns were found."
        )

    required_actual = [
        cell_col,
        time_col,
        *[
            mapping[kpi]
            for kpi in kpis
        ],
    ]

    missing = [
        column
        for column in required_actual
        if column not in actual_df.columns
    ]

    if missing:
        raise ValueError(
            "Actual dataset is missing "
            "required columns: "
            + ", ".join(missing)
        )

    forecast_df[cell_col] = (
        forecast_df[cell_col]
        .astype(str)
        .str.strip()
    )

    actual_df[cell_col] = (
        actual_df[cell_col]
        .astype(str)
        .str.strip()
    )

    forecast_df[time_col] = (
        pd.to_datetime(
            forecast_df[time_col],
            format="mixed",
            errors="coerce",
        )
    )

    actual_df[time_col] = (
        pd.to_datetime(
            actual_df[time_col],
            format="mixed",
            errors="coerce",
        )
    )

    invalid_actual = int(
        actual_df[
            time_col
        ].isna().sum()
    )

    if invalid_actual > 0:
        raise ValueError(
            "Actual dataset contains "
            f"{invalid_actual} invalid "
            "timestamp row(s)."
        )

    forecast_duplicates = int(
        forecast_df.duplicated(
            subset=[
                cell_col,
                time_col,
            ]
        ).sum()
    )

    if forecast_duplicates:
        raise ValueError(
            "Forecast output contains "
            "duplicate cell/timestamp keys."
        )

    actual_duplicates = int(
        actual_df.duplicated(
            subset=[
                cell_col,
                time_col,
            ]
        ).sum()
    )

    if actual_duplicates:
        raise ValueError(
            "Actual dataset contains "
            f"{actual_duplicates} duplicate "
            "cell/timestamp keys."
        )

    actual_selected = (
        actual_df[
            required_actual
        ].copy()
    )

    for kpi in kpis:
        raw_column = mapping[kpi]

        actual_selected[
            f"{kpi}_ACTUAL"
        ] = pd.to_numeric(
            actual_selected[
                raw_column
            ],
            errors="coerce",
        )

    actual_selected = (
        actual_selected[
            [
                cell_col,
                time_col,
                *[
                    f"{kpi}_ACTUAL"
                    for kpi in kpis
                ],
            ]
        ]
    )

    matched_df = (
        forecast_df.merge(
            actual_selected,
            on=[
                cell_col,
                time_col,
            ],
            how="inner",
            validate="one_to_one",
        )
    )

    if matched_df.empty:
        forecast_start = (
            forecast_df[
                time_col
            ].min()
        )

        forecast_end = (
            forecast_df[
                time_col
            ].max()
        )

        raise ValueError(
            "No forecast rows matched "
            "the actual dataset. "
            "Actual data must cover: "
            f"{forecast_start} to "
            f"{forecast_end}."
        )

    metrics = []

    for kpi in kpis:
        forecast_col = (
            f"{kpi}_FORECAST"
        )

        actual_col = (
            f"{kpi}_ACTUAL"
        )

        matched_df[
            forecast_col
        ] = pd.to_numeric(
            matched_df[
                forecast_col
            ],
            errors="coerce",
        )

        metric = _calculate_metrics(
            matched_df[
                actual_col
            ],
            matched_df[
                forecast_col
            ],
        )

        metrics.append(
            {
                "kpi": kpi,
                "source_column": (
                    mapping[kpi]
                ),
                "forecast_column": (
                    forecast_col
                ),
                "actual_column": (
                    actual_col
                ),
                **metric,
            }
        )

    mape_values = [
        item["mape"]
        for item in metrics
        if item["mape"] is not None
    ]

    r2_values = [
        item["r2"]
        for item in metrics
        if item["r2"] is not None
    ]

    macro_mape = (
        round(
            float(
                np.mean(
                    mape_values
                )
            ),
            6,
        )
        if mape_values
        else None
    )

    macro_r2 = (
        round(
            float(
                np.mean(
                    r2_values
                )
            ),
            6,
        )
        if r2_values
        else None
    )

    forecast_rows = int(
        len(forecast_df)
    )

    matched_rows = int(
        len(matched_df)
    )

    validation_id = (
        datetime.now(
            timezone.utc
        ).strftime(
            "VAL-%Y%m%dT%H%M%S%fZ"
        )
    )

    export_df = (
        matched_df[
            [
                cell_col,
                time_col,
                *[
                    item
                    for kpi in kpis
                    for item in (
                        f"{kpi}_ACTUAL",
                        f"{kpi}_FORECAST",
                    )
                ],
            ]
        ]
        .copy()
    )

    validation_compute_seconds = (
        time.perf_counter()
        - validation_started
    )

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="baps-validation-"
        )
    )

    try:
        validation_path = (
            work_dir
            / VALIDATION_FILENAME
        )

        summary_path = (
            work_dir
            / SUMMARY_FILENAME
        )

        export_df.to_csv(
            validation_path,
            index=False,
        )

        result = {
            "status": "completed",
            "validation_id": (
                validation_id
            ),
            "forecast_run_id": run_id,
            "generation_id": (
                generation_id
            ),
            "actual_source": (
                actual_source
            ),
            "actual_source_label": (
                actual_source_label
            ),
            "actual_filename": (
                resolved_actual_filename
            ),
            "forecast_rows": (
                forecast_rows
            ),
            "actual_rows": int(
                len(actual_df)
            ),
            "matched_rows": (
                matched_rows
            ),
            "unmatched_forecast_rows": int(
                forecast_rows
                - matched_rows
            ),
            "forecast_cells": int(
                forecast_df[
                    cell_col
                ].nunique()
            ),
            "actual_cells": int(
                actual_df[
                    cell_col
                ].nunique()
            ),
            "matched_cells": int(
                matched_df[
                    cell_col
                ].nunique()
            ),
            "match_rate_percent": round(
                (
                    matched_rows
                    / forecast_rows
                    * 100.0
                )
                if forecast_rows
                else 0.0,
                4,
            ),
            "kpis": kpis,
            "cells": sorted(
                matched_df[
                    cell_col
                ]
                .astype(str)
                .unique()
                .tolist()
            ),
            "metrics": metrics,
            "macro": {
                "mape": macro_mape,
                "r2": macro_r2,
            },
            "download_url": (
                f"/api/validation/"
                f"{validation_id}/csv"
            ),
        }

        summary_path.write_text(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        validation_prefix = (
            f"{VALIDATION_RUNS_BLOB_PREFIX}/"
            f"{validation_id}"
        )

        validation_blob_pathname = (
            f"{validation_prefix}/"
            f"{VALIDATION_FILENAME}"
        )

        summary_blob_pathname = (
            f"{validation_prefix}/"
            f"{SUMMARY_FILENAME}"
        )

        upload_started = (
            time.perf_counter()
        )

        async with AsyncBlobClient() as client:
            validation_blob = (
                await client.upload_file(
                    str(
                        validation_path
                    ),
                    validation_blob_pathname,
                    access="private",
                    add_random_suffix=False,
                    overwrite=False,
                    multipart=(
                        validation_path
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

        result[
            "artifacts"
        ] = {
            "validation": {
                "pathname": (
                    validation_blob.pathname
                ),
                "size": (
                    validation_path
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

        result[
            "runtime_seconds"
        ] = {
            "blob_download": round(
                blob_download_seconds,
                4,
            ),
            "dataset_load": round(
                dataset_load_seconds,
                4,
            ),
            "validation_compute": round(
                validation_compute_seconds,
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

        return result

    finally:
        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )

        try:
            del forecast_df
        except Exception:
            pass

        try:
            del actual_df
        except Exception:
            pass

        try:
            del matched_df
        except Exception:
            pass

        try:
            del export_df
        except Exception:
            pass

        gc.collect()