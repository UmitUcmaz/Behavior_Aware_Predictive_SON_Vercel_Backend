"""History-only artifact preparation using the existing forecast preprocessing."""
import hashlib
from pathlib import Path

import pandas as pd

from ml_engine.forecast_engine import ForecastEngine


MODEL_READY_FILENAME = "model_ready_forecast_input.csv"


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def assert_history_before_ground_truth(history_times, ground_truth_times):
    history_times = pd.to_datetime(history_times, format="mixed")
    ground_truth_times = pd.to_datetime(ground_truth_times, format="mixed")
    if (history_times.empty or ground_truth_times.empty
            or history_times.isna().any() or ground_truth_times.isna().any()
            or not history_times.max() < ground_truth_times.min()):
        raise ValueError("DATA LEAKAGE: history must end strictly before ground truth starts.")
    return str(history_times.max()), str(ground_truth_times.min())


def build_model_ready_history(history_path, *, chunksize, progress_callback=None):
    """Read only the split history. Keep validation on every row before tail(96).

    Current engine temporal features and fitted clustering predictions are row-local.
    No model is fitted here. Reading the serialized history uses the same default
    pandas numeric parser as the raw forecast service, preserving its exact values.
    The generator has already ordered history by timestamp and cell, including ties.
    """
    history_path = Path(history_path)
    engine = ForecastEngine(load_forecasting=False)
    retained = None
    rows = 0
    perf = {}
    history_start = None
    with pd.read_csv(history_path, chunksize=chunksize) as chunks:
        for chunk in chunks:
            required = [engine.schema.get("selected_date_column", "SDATE"),
                        *(engine.schema.get("cell_columns") or ["CELL_NAME"])[:1],
                        *engine.schema.get("kpi_columns", [])]
            missing = [column for column in required if column not in chunk]
            if missing:
                raise ValueError("Missing required columns: " + ", ".join(missing))
            # Full-history clustering validation runs inside this call, before trimming.
            features, cell, date, kpis = engine.preprocess_and_extract_features(chunk, perf)
            timestamps = pd.to_datetime(chunk[date], format="mixed")
            if timestamps.isna().any():
                raise ValueError("Timestamp validation failed in generated history.")
            history_start = timestamps.min() if history_start is None else min(history_start, timestamps.min())
            rows += len(chunk)
            retained = features if retained is None else pd.concat([retained, features], ignore_index=True)
            retained = (retained.sort_values([cell, date])
                        .groupby(cell, sort=False, observed=True, dropna=False).tail(96)
                        .reset_index(drop=True))
            if progress_callback:
                progress_callback(rows)
    if retained is None or retained.empty:
        raise ValueError("No generated history rows found.")
    output = history_path.with_name(MODEL_READY_FILENAME)
    temporary = output.with_suffix(".csv.tmp")
    try:
        retained.to_csv(temporary, index=False)
        temporary.replace(output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "filename": MODEL_READY_FILENAME, "version": 1,
        "rows": len(retained), "history_rows": rows,
        "cell_count": int(retained[cell].nunique(dropna=False)),
        "cell_column": cell, "time_column": date, "kpis": kpis,
        "columns": list(retained.columns),
        "history_start": str(history_start),
        "history_sha256": file_sha256(history_path),
        "sha256": file_sha256(output),
    }
