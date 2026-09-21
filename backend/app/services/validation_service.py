from datetime import (
    datetime,
    timezone,
)

from io import BytesIO
import json

import numpy as np
import pandas as pd

from ml_engine.forecast_engine import (
    PROJECT_ROOT,
)

from backend.app.services.forecast_service import (
    get_forecast_csv_path,
    get_forecast_metadata,
    get_forecast_ground_truth_path,
    get_forecast_run_metadata,
)


VALIDATION_RUNS_DIR = (
    PROJECT_ROOT
    / "data"
    / "outputs"
    / "validation_runs"
)


def get_validation_service_status():

    return {
        "status": "ready",
        "service": "validation",
    }


def _get_kpi_mapping():

    engine = (
        get_forecast_metadata()
    )

    mapping_df = (
        engine.mapping_df
    )

    source_col = (
        "SOURCE_COLUMN"
        if (
            "SOURCE_COLUMN"
            in mapping_df.columns
        )
        else mapping_df.columns[0]
    )

    if (
        "CONFIRMED_ROLE"
        in mapping_df.columns
    ):

        role_col = (
            "CONFIRMED_ROLE"
        )

    elif (
        "STANDARDIZED_NAME"
        in mapping_df.columns
    ):

        role_col = (
            "STANDARDIZED_NAME"
        )

    else:

        role_col = (
            "PROPOSED_KPI_ROLE"
        )

    mapping = {}

    for _, row in (
        mapping_df.iterrows()
    ):

        source = str(
            row[source_col]
        ).strip()

        role = str(
            row[role_col]
        ).strip()

        if (
            source
            and role
            and source.lower()
            != "nan"
            and role.lower()
            != "nan"
        ):

            mapping[
                role
            ] = source

    return mapping


def list_forecast_runs(
    limit=50,
):

    runs_dir = (
        PROJECT_ROOT
        / "data"
        / "outputs"
        / "runs"
    )

    if not runs_dir.exists():

        return []

    runs = []

    for run_dir in sorted(
        runs_dir.glob(
            "FR-*"
        ),
        reverse=True,
    ):

        forecast_file = (
            run_dir
            / "forecast.csv"
        )

        if not forecast_file.exists():

            continue

        try:

            metadata = (
                get_forecast_run_metadata(
                    run_dir.name
                )
            )

        except Exception:

            metadata = {
                "run_id": (
                    run_dir.name
                ),
                "source_type": (
                    "uploaded"
                ),
                "ground_truth": {
                    "available": False,
                    "filename": None,
                },
            }

        source_type = (
            metadata.get(
                "source_type",
                "uploaded",
            )
        )

        ground_truth = (
            metadata.get(
                "ground_truth",
                {},
            )
        )

        runs.append(
            {
                "run_id": (
                    run_dir.name
                ),
                "source_type": (
                    source_type
                ),
                "source_label": (
                    "Generated Demo/Test Dataset"
                    if source_type
                    == "generated"
                    else "Uploaded Dataset"
                ),
                "ground_truth_available": bool(
                    ground_truth.get(
                        "available",
                        False,
                    )
                ),
                "ground_truth_filename": (
                    ground_truth.get(
                        "filename"
                    )
                ),
                "horizon_steps": (
                    metadata.get(
                        "horizon_steps"
                    )
                ),
                "total_cells": (
                    metadata.get(
                        "total_cells"
                    )
                ),
                "forecast_rows": (
                    metadata.get(
                        "forecast_rows"
                    )
                ),
            }
        )

        if len(
            runs
        ) >= int(
            limit
        ):

            break

    return runs


def _safe_metric(
    value,
):

    if value is None:

        return None

    value = float(
        value
    )

    if not np.isfinite(
        value
    ):

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
        np.isfinite(
            actual
        )
        & np.isfinite(
            forecast
        )
    )

    actual = actual[
        mask
    ]

    forecast = forecast[
        mask
    ]

    count = int(
        len(
            actual
        )
    )

    if count == 0:

        return {
            "count": 0,
            "mae": None,
            "rmse": None,
            "mape": None,
            "r2": None,
        }

    error = (
        forecast
        - actual
    )

    mae = np.mean(
        np.abs(
            error
        )
    )

    rmse = np.sqrt(
        np.mean(
            np.square(
                error
            )
        )
    )

    non_zero = (
        np.abs(
            actual
        )
        > 1e-12
    )

    if bool(
        non_zero.any()
    ):

        mape = (
            np.mean(
                np.abs(
                    error[
                        non_zero
                    ]
                    / actual[
                        non_zero
                    ]
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
                actual
                - forecast
            )
        )

        ss_tot = np.sum(
            np.square(
                actual
                - mean_actual
            )
        )

        r2 = (
            1.0
            - ss_res
            / ss_tot
            if ss_tot > 0
            else None
        )

    else:

        r2 = None

    return {
        "count": count,
        "mae": _safe_metric(
            mae
        ),
        "rmse": _safe_metric(
            rmse
        ),
        "mape": _safe_metric(
            mape
        ),
        "r2": _safe_metric(
            r2
        ),
    }


def _resolve_actual_dataset(
    run_id,
    file_bytes=None,
    filename=None,
):

    metadata = (
        get_forecast_run_metadata(
            run_id
        )
    )

    if file_bytes:

        return {
            "bytes": file_bytes,
            "filename": (
                filename
                or "uploaded_actual.csv"
            ),
            "source": "uploaded",
            "source_label": (
                "Uploaded Actual Data"
            ),
        }

    ground_truth = (
        metadata.get(
            "ground_truth",
            {},
        )
    )

    if ground_truth.get(
        "available",
        False,
    ):

        path = (
            get_forecast_ground_truth_path(
                run_id
            )
        )

        return {
            "bytes": path.read_bytes(),
            "filename": (
                ground_truth.get(
                    "filename"
                )
                or "ground_truth.csv"
            ),
            "source": (
                "generated_ground_truth"
            ),
            "source_label": (
                "Generated Ground Truth"
            ),
        }

    raise ValueError(
        (
            "This forecast run does not "
            "contain generated ground truth. "
            "Upload an actual network CSV "
            "covering the forecast period."
        )
    )


def run_validation_bytes(
    run_id,
    file_bytes=None,
    filename=None,
):

    forecast_path = (
        get_forecast_csv_path(
            run_id
        )
    )

    actual_info = (
        _resolve_actual_dataset(
            run_id=run_id,
            file_bytes=file_bytes,
            filename=filename,
        )
    )

    forecast_df = (
        pd.read_csv(
            forecast_path
        )
    )

    actual_df = (
        pd.read_csv(
            BytesIO(
                actual_info[
                    "bytes"
                ]
            )
        )
    )

    if actual_df.empty:

        raise ValueError(
            "Actual dataset contains no data rows."
        )

    engine = (
        get_forecast_metadata()
    )

    time_col = (
        engine.schema.get(
            "selected_date_column",
            "SDATE",
        )
    )

    cell_cols = (
        engine.schema.get(
            "cell_columns",
            [],
        )
    )

    cell_col = (
        cell_cols[0]
        if cell_cols
        else "CELL_NAME"
    )

    mapping = (
        _get_kpi_mapping()
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
            (
                "No supported forecast "
                "KPI columns were found."
            )
        )

    required_actual = [
        cell_col,
        time_col,
        *[
            mapping[
                kpi
            ]
            for kpi in kpis
        ],
    ]

    missing = [
        column
        for column in required_actual
        if column
        not in actual_df.columns
    ]

    if missing:

        raise ValueError(
            (
                "Actual dataset is missing "
                "required columns: "
                + ", ".join(
                    missing
                )
            )
        )

    forecast_df[
        cell_col
    ] = (
        forecast_df[
            cell_col
        ]
        .astype(str)
        .str.strip()
    )

    actual_df[
        cell_col
    ] = (
        actual_df[
            cell_col
        ]
        .astype(str)
        .str.strip()
    )

    forecast_df[
        time_col
    ] = pd.to_datetime(
        forecast_df[
            time_col
        ],
        format="mixed",
        errors="coerce",
    )

    actual_df[
        time_col
    ] = pd.to_datetime(
        actual_df[
            time_col
        ],
        format="mixed",
        errors="coerce",
    )

    invalid_actual = int(
        actual_df[
            time_col
        ].isna().sum()
    )

    if invalid_actual > 0:

        raise ValueError(
            (
                "Actual dataset contains "
                f"{invalid_actual} invalid "
                "timestamp row(s)."
            )
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
            (
                "Forecast output contains "
                "duplicate cell/timestamp keys."
            )
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
            (
                "Actual dataset contains "
                f"{actual_duplicates} duplicate "
                "cell/timestamp keys."
            )
        )

    actual_selected = (
        actual_df[
            required_actual
        ]
        .copy()
    )

    for kpi in kpis:

        raw_column = (
            mapping[
                kpi
            ]
        )

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
            (
                "No forecast rows matched "
                "the actual dataset. "
                "Actual data must cover: "
                f"{forecast_start} to "
                f"{forecast_end}."
            )
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

        metric = (
            _calculate_metrics(
                matched_df[
                    actual_col
                ],
                matched_df[
                    forecast_col
                ],
            )
        )

        metrics.append(
            {
                "kpi": kpi,
                "source_column": (
                    mapping[
                        kpi
                    ]
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
        if item["mape"]
        is not None
    ]

    r2_values = [
        item["r2"]
        for item in metrics
        if item["r2"]
        is not None
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
        len(
            forecast_df
        )
    )

    matched_rows = int(
        len(
            matched_df
        )
    )

    validation_id = (
        datetime.now(
            timezone.utc
        ).strftime(
            "VAL-%Y%m%dT%H%M%S%fZ"
        )
    )

    validation_dir = (
        VALIDATION_RUNS_DIR
        / validation_id
    )

    validation_dir.mkdir(
        parents=True,
        exist_ok=True,
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

    export_df.to_csv(
        validation_dir
        / "validation_matched.csv",
        index=False,
    )

    result = {
        "status": "completed",
        "validation_id": (
            validation_id
        ),
        "forecast_run_id": (
            run_id
        ),
        "actual_source": (
            actual_info[
                "source"
            ]
        ),
        "actual_source_label": (
            actual_info[
                "source_label"
            ]
        ),
        "actual_filename": (
            actual_info[
                "filename"
            ]
        ),
        "forecast_rows": (
            forecast_rows
        ),
        "actual_rows": int(
            len(
                actual_df
            )
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
            "mape": (
                macro_mape
            ),
            "r2": (
                macro_r2
            ),
        },
        "download_url": (
            f"/validation/"
            f"{validation_id}"
            f"/csv"
        ),
    }

    with open(
        validation_dir
        / "summary.json",
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            result,
            file,
            indent=2,
        )

    return result


def get_validation_csv_path(
    validation_id,
):

    if not str(
        validation_id
    ).startswith(
        "VAL-"
    ):

        raise ValueError(
            "Invalid validation_id."
        )

    path = (
        VALIDATION_RUNS_DIR
        / validation_id
        / "validation_matched.csv"
    )

    if not path.exists():

        raise FileNotFoundError(
            (
                "Validation run not found: "
                f"{validation_id}"
            )
        )

    return path


def get_validation_chart_data(
    validation_id,
    cell_name,
    kpi,
):

    path = (
        get_validation_csv_path(
            validation_id
        )
    )

    engine = (
        get_forecast_metadata()
    )

    time_col = (
        engine.schema.get(
            "selected_date_column",
            "SDATE",
        )
    )

    cell_cols = (
        engine.schema.get(
            "cell_columns",
            [],
        )
    )

    cell_col = (
        cell_cols[0]
        if cell_cols
        else "CELL_NAME"
    )

    actual_col = (
        f"{kpi}_ACTUAL"
    )

    forecast_col = (
        f"{kpi}_FORECAST"
    )

    df = (
        pd.read_csv(
            path
        )
    )

    required = [
        cell_col,
        time_col,
        actual_col,
        forecast_col,
    ]

    missing = [
        column
        for column in required
        if column
        not in df.columns
    ]

    if missing:

        raise ValueError(
            (
                "Validation chart columns "
                "not found: "
                + ", ".join(
                    missing
                )
            )
        )

    df[
        cell_col
    ] = (
        df[
            cell_col
        ].astype(str)
    )

    cell_df = (
        df[
            df[
                cell_col
            ]
            == str(
                cell_name
            )
        ]
        .copy()
    )

    if cell_df.empty:

        raise ValueError(
            (
                "Cell not found in validation: "
                f"{cell_name}"
            )
        )

    cell_df[
        time_col
    ] = pd.to_datetime(
        cell_df[
            time_col
        ],
        format="mixed",
        errors="coerce",
    )

    cell_df[
        actual_col
    ] = pd.to_numeric(
        cell_df[
            actual_col
        ],
        errors="coerce",
    )

    cell_df[
        forecast_col
    ] = pd.to_numeric(
        cell_df[
            forecast_col
        ],
        errors="coerce",
    )

    cell_df = (
        cell_df
        .dropna(
            subset=[
                time_col,
                actual_col,
                forecast_col,
            ]
        )
        .sort_values(
            time_col
        )
    )

    points = [
        {
            "time": (
                row[
                    time_col
                ].strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
            ),
            "actual": float(
                row[
                    actual_col
                ]
            ),
            "forecast": float(
                row[
                    forecast_col
                ]
            ),
        }
        for _, row in (
            cell_df.iterrows()
        )
    ]

    return {
        "status": "ready",
        "validation_id": (
            validation_id
        ),
        "cell_name": str(
            cell_name
        ),
        "kpi": kpi,
        "points": points,
    }
