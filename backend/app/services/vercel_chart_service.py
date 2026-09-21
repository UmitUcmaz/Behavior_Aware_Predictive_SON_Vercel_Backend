from __future__ import annotations

import json
from io import BytesIO

import pandas as pd

from vercel.blob import AsyncBlobClient


FORECAST_RUNS_PREFIX = "forecast-runs"
GENERATIONS_PREFIX = "generations"

CELL_COLUMN = "CELL_NAME"
TIME_COLUMN = "SDATE"

SUPPORTED_KPIS = {
    "UL_PRB_UTILIZATION",
    "DL_PRB_UTILIZATION",
    "ACTIVE_USERS",
}


def _validate_run_id(
    run_id: str,
) -> str:
    value = str(
        run_id
    ).strip()

    if (
        not value.startswith(
            "FR-"
        )
        or "/"
        in value
        or "\\"
        in value
        or ".."
        in value
    ):
        raise ValueError(
            "Invalid run_id."
        )

    return value


def _validate_kpi(
    kpi: str,
) -> str:
    value = str(
        kpi
    ).strip()

    if value not in SUPPORTED_KPIS:
        raise ValueError(
            f"Unsupported KPI: {value}"
        )

    return value


def _validate_history_points(
    history_points: int,
) -> int:
    value = int(
        history_points
    )

    if (
        value < 1
        or value > 500
    ):
        raise ValueError(
            "history_points must be "
            "between 1 and 500."
        )

    return value


async def _get_blob_bytes(
    client: AsyncBlobClient,
    pathname: str,
) -> bytes:
    result = await client.get(
        pathname,
        access="private",
        timeout=120,
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
        return content

    if isinstance(
        content,
        bytearray,
    ):
        return bytes(
            content
        )

    if isinstance(
        content,
        memoryview,
    ):
        return content.tobytes()

    if isinstance(
        content,
        str,
    ):
        return content.encode(
            "utf-8"
        )

    raise TypeError(
        "Unsupported Blob content type: "
        f"{type(content).__name__}"
    )


async def _get_json_blob(
    client: AsyncBlobClient,
    pathname: str,
) -> dict:
    content = (
        await _get_blob_bytes(
            client,
            pathname,
        )
    )

    return json.loads(
        content.decode(
            "utf-8"
        )
    )


def _resolve_generation_id(
    metadata: dict,
) -> str:
    generation_id = (
        metadata.get(
            "generation_id"
        )
    )

    if not generation_id:
        raise ValueError(
            "Forecast run is not linked "
            "to a generated dataset."
        )

    generation_id = str(
        generation_id
    ).strip()

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
        raise ValueError(
            "Invalid generation_id in "
            "forecast metadata."
        )

    return generation_id


def _resolve_history_path(
    metadata: dict,
    generation_id: str,
) -> str:
    pathname = (
        metadata.get(
            "generation_model_ready"
        )
    )

    if pathname:
        return str(
            pathname
        )

    return (
        f"{GENERATIONS_PREFIX}/"
        f"{generation_id}/"
        "model_ready_forecast_input.csv"
    )


def _resolve_forecast_path(
    run_id: str,
) -> str:
    return (
        f"{FORECAST_RUNS_PREFIX}/"
        f"{run_id}/"
        "forecast.csv"
    )


def _load_history_frame(
    csv_bytes: bytes,
    kpi: str,
) -> pd.DataFrame:
    required = [
        CELL_COLUMN,
        TIME_COLUMN,
        kpi,
    ]

    try:
        df = pd.read_csv(
            BytesIO(
                csv_bytes
            ),
            usecols=required,
        )

    except ValueError as exc:
        raise ValueError(
            "Required historical chart "
            "columns were not found: "
            + ", ".join(
                required
            )
        ) from exc

    return df


def _load_forecast_frame(
    csv_bytes: bytes,
    kpi: str,
) -> pd.DataFrame:
    forecast_column = (
        f"{kpi}_FORECAST"
    )

    required = [
        CELL_COLUMN,
        TIME_COLUMN,
        forecast_column,
    ]

    try:
        df = pd.read_csv(
            BytesIO(
                csv_bytes
            ),
            usecols=required,
        )

    except ValueError as exc:
        raise ValueError(
            "Required forecast chart "
            "columns were not found: "
            + ", ".join(
                required
            )
        ) from exc

    return df


def _prepare_history(
    df: pd.DataFrame,
    cell_name: str,
    kpi: str,
    history_points: int,
) -> pd.DataFrame:
    df[
        CELL_COLUMN
    ] = (
        df[
            CELL_COLUMN
        ]
        .astype(
            str
        )
    )

    selected = (
        df[
            df[
                CELL_COLUMN
            ]
            == str(
                cell_name
            )
        ]
        .copy()
    )

    if selected.empty:
        raise ValueError(
            "Cell was not found in "
            f"historical data: {cell_name}"
        )

    selected[
        TIME_COLUMN
    ] = pd.to_datetime(
        selected[
            TIME_COLUMN
        ],
        format="mixed",
        errors="coerce",
    )

    selected[
        kpi
    ] = pd.to_numeric(
        selected[
            kpi
        ],
        errors="coerce",
    )

    selected = (
        selected
        .dropna(
            subset=[
                TIME_COLUMN,
                kpi,
            ]
        )
        .sort_values(
            TIME_COLUMN
        )
        .tail(
            history_points
        )
    )

    return selected


def _prepare_forecast(
    df: pd.DataFrame,
    cell_name: str,
    forecast_column: str,
) -> pd.DataFrame:
    df[
        CELL_COLUMN
    ] = (
        df[
            CELL_COLUMN
        ]
        .astype(
            str
        )
    )

    selected = (
        df[
            df[
                CELL_COLUMN
            ]
            == str(
                cell_name
            )
        ]
        .copy()
    )

    if selected.empty:
        raise ValueError(
            "Cell was not found in "
            f"forecast output: {cell_name}"
        )

    selected[
        TIME_COLUMN
    ] = pd.to_datetime(
        selected[
            TIME_COLUMN
        ],
        format="mixed",
        errors="coerce",
    )

    selected[
        forecast_column
    ] = pd.to_numeric(
        selected[
            forecast_column
        ],
        errors="coerce",
    )

    selected = (
        selected
        .dropna(
            subset=[
                TIME_COLUMN,
                forecast_column,
            ]
        )
        .sort_values(
            TIME_COLUMN
        )
    )

    return selected


def _chart_points(
    df: pd.DataFrame,
    value_column: str,
) -> list[dict]:
    return [
        {
            "time": (
                row[
                    TIME_COLUMN
                ]
                .strftime(
                    "%Y-%m-%dT%H:%M:%S"
                )
            ),
            "value": float(
                row[
                    value_column
                ]
            ),
        }
        for _, row
        in df.iterrows()
    ]


async def get_forecast_chart_data(
    run_id: str,
    cell_name: str,
    kpi: str,
    history_points: int = 96,
):
    run_id = (
        _validate_run_id(
            run_id
        )
    )

    kpi = (
        _validate_kpi(
            kpi
        )
    )

    history_points = (
        _validate_history_points(
            history_points
        )
    )

    selected_cell = str(
        cell_name
    ).strip()

    if not selected_cell:
        raise ValueError(
            "cell_name is required."
        )

    metadata_path = (
        f"{FORECAST_RUNS_PREFIX}/"
        f"{run_id}/"
        "run_metadata.json"
    )

    async with AsyncBlobClient() as client:
        metadata = (
            await _get_json_blob(
                client,
                metadata_path,
            )
        )

        if metadata.get("source_type") == "uploaded":
            # Fixed run-owned history path; never accept arbitrary metadata URLs.
            history_path = f"{FORECAST_RUNS_PREFIX}/{run_id}/history.csv"
        else:
            generation_id = _resolve_generation_id(metadata)
            history_path = _resolve_history_path(metadata, generation_id)

        forecast_path = (
            _resolve_forecast_path(
                run_id
            )
        )

        history_bytes = (
            await _get_blob_bytes(
                client,
                history_path,
            )
        )

        forecast_bytes = (
            await _get_blob_bytes(
                client,
                forecast_path,
            )
        )

    history_df = (
        _load_history_frame(
            history_bytes,
            kpi,
        )
    )

    forecast_df = (
        _load_forecast_frame(
            forecast_bytes,
            kpi,
        )
    )

    forecast_column = (
        f"{kpi}_FORECAST"
    )

    history_cell = (
        _prepare_history(
            history_df,
            selected_cell,
            kpi,
            history_points,
        )
    )

    forecast_cell = (
        _prepare_forecast(
            forecast_df,
            selected_cell,
            forecast_column,
        )
    )

    historical = (
        _chart_points(
            history_cell,
            kpi,
        )
    )

    forecast = (
        _chart_points(
            forecast_cell,
            forecast_column,
        )
    )

    return {
        "status": "ready",

        "run_id": (
            run_id
        ),

        "cell_name": (
            selected_cell
        ),

        "kpi": (
            kpi
        ),

        "source_column": (
            kpi
        ),

        "forecast_column": (
            forecast_column
        ),

        "history_points": len(
            historical
        ),

        "forecast_points": len(
            forecast
        ),

        "historical": (
            historical
        ),

        "forecast": (
            forecast
        ),
    }
async def get_validation_chart_data(
    validation_id: str,
    cell_name: str,
    kpi: str,
) -> dict:
    """Read the existing matched validation artifact; never recompute metrics."""
    import re

    if not re.fullmatch(r"VAL-\d{8}T\d{12}Z", validation_id):
        raise ValueError("Invalid validation_id.")
    kpi = _validate_kpi(kpi)
    pathname = f"validation-runs/{validation_id}/validation_matched.csv"
    async with AsyncBlobClient() as client:
        content = await _get_blob_bytes(client, pathname)

    actual_col = f"{kpi}_ACTUAL"
    forecast_col = f"{kpi}_FORECAST"
    df = pd.read_csv(BytesIO(content))
    required = [CELL_COLUMN, TIME_COLUMN, actual_col, forecast_col]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError("Validation chart columns not found: " + ", ".join(missing))

    # Preserve validation_service.get_validation_chart_data's filtering,
    # conversions, null handling and time ordering for the Blob-backed result.
    df[CELL_COLUMN] = df[CELL_COLUMN].astype(str)
    cell_df = df[df[CELL_COLUMN] == str(cell_name)].copy()
    if cell_df.empty:
        raise ValueError(f"Cell not found in validation: {cell_name}")
    cell_df[TIME_COLUMN] = pd.to_datetime(cell_df[TIME_COLUMN], format="mixed", errors="coerce")
    cell_df[actual_col] = pd.to_numeric(cell_df[actual_col], errors="coerce")
    cell_df[forecast_col] = pd.to_numeric(cell_df[forecast_col], errors="coerce")
    cell_df = cell_df.dropna(subset=[TIME_COLUMN, actual_col, forecast_col]).sort_values(TIME_COLUMN)
    return {
        "status": "ready",
        "validation_id": validation_id,
        "cell_name": str(cell_name),
        "kpi": kpi,
        "points": [
            {"time": row[TIME_COLUMN].strftime("%Y-%m-%dT%H:%M:%S"),
             "actual": float(row[actual_col]), "forecast": float(row[forecast_col])}
            for _, row in cell_df.iterrows()
        ],
    }
