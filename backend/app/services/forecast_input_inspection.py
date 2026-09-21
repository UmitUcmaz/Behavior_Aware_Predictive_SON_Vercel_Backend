"""Legacy raw CSV inspection, preserved without filesystem job management."""
from functools import lru_cache
from io import BytesIO
import pandas as pd
from ml_engine.forecast_engine import ForecastMetadata

@lru_cache(maxsize=1)
def get_forecast_metadata():
    return ForecastMetadata()


def inspect_forecast_bytes(
    file_bytes,
    filename,
):

    if (
        not filename
        or not filename.lower().endswith(".csv")
    ):
        raise ValueError(
            "Only CSV files are accepted."
        )

    if not file_bytes:
        raise ValueError(
            "Uploaded CSV file is empty."
        )

    df_raw = pd.read_csv(
        BytesIO(file_bytes)
    )

    if df_raw.empty:
        raise ValueError(
            "Uploaded CSV contains no data rows."
        )

    engine = get_forecast_metadata()

    time_col = engine.schema.get(
        "selected_date_column",
        "SDATE",
    )

    cell_cols = engine.schema.get(
        "cell_columns",
        [],
    )

    cell_col = (
        cell_cols[0]
        if cell_cols
        else "CELL_NAME"
    )

    kpi_cols = engine.schema.get(
        "kpi_columns",
        [],
    )

    required_columns = [
        time_col,
        cell_col,
        *kpi_cols,
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in df_raw.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(
                missing_columns
            )
        )

    parsed_times = pd.to_datetime(
        df_raw[time_col],
        format="mixed",
        errors="coerce",
    )

    invalid_timestamp_rows = int(
        parsed_times.isna().sum()
    )

    if invalid_timestamp_rows > 0:
        raise ValueError(
            (
                f"Timestamp validation failed for "
                f"{invalid_timestamp_rows} row(s) "
                f"in column '{time_col}'."
            )
        )

    valid_times = parsed_times.dropna()

    if valid_times.empty:
        raise ValueError(
            "No valid timestamps were found."
        )

    cell_values = (
        df_raw[cell_col]
        .dropna()
        .astype(str)
        .str.strip()
    )

    cell_values = cell_values[
        cell_values != ""
    ]

    total_cells = int(
        cell_values.nunique()
    )

    if total_cells <= 0:
        raise ValueError(
            "No valid cell identifiers were found."
        )

    input_start = (
        valid_times
        .min()
        .strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    )

    input_end = (
        valid_times
        .max()
        .strftime(
            "%Y-%m-%dT%H:%M:%S"
        )
    )

    return {
        "status": "validated",
        "input_filename": filename,
        "input_rows": int(
            len(df_raw)
        ),
        "total_columns": int(
            len(df_raw.columns)
        ),
        "total_cells": total_cells,
        "total_kpis": int(
            len(kpi_cols)
        ),
        "cell_column": cell_col,
        "time_column": time_col,
        "kpi_columns": list(
            kpi_cols
        ),
        "valid_timestamp_rows": int(
            len(valid_times)
        ),
        "invalid_timestamp_rows": (
            invalid_timestamp_rows
        ),
        "input_date_range": {
            "start": input_start,
            "end": input_end,
        },
    }