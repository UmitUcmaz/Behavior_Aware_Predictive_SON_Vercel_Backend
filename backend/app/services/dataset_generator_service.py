from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import math
import secrets
from typing import Callable

import numpy as np


# DATASET-GENERATOR-PROGRESS-V1
ProgressCallback = Callable[
    [float, str],
    None,
]
import pandas as pd

from backend.app.services.model_ready_service import (
    assert_history_before_ground_truth,
    build_model_ready_history,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[3]

SOURCE_FILE = (
    PROJECT_ROOT
    / "data"
    / "raw"
    / "network_traffic.csv"
)

OUTPUT_ROOT = (
    PROJECT_ROOT
    / "data"
    / "outputs"
    / "generated"
)


CELL_COLUMN = "CELL_NAME"
DATE_COLUMN = "SDATE"

RESOLUTION_MINUTES = 15
HISTORY_DAYS = 8
GROUND_TRUTH_DAYS = 1
COVERAGE_THRESHOLD = 0.98

CHUNK_SIZE = 150_000
MAX_GENERATED_CELLS = 2000


class DatasetGeneratorError(
    RuntimeError
):
    pass


def _report_progress(
    callback: ProgressCallback | None,
    percent: float,
    label: str,
):

    if callback is None:
        return

    callback(
        max(
            0.0,
            min(
                100.0,
                float(percent),
            ),
        ),
        label,
    )


def _count_source_rows(
    callback: ProgressCallback | None,
) -> int:

    file_size = max(
        SOURCE_FILE.stat().st_size,
        1,
    )

    bytes_read = 0
    line_count = 0

    with SOURCE_FILE.open(
        "rb"
    ) as handle:

        while True:

            block = handle.read(
                8 * 1024 * 1024
            )

            if not block:
                break

            bytes_read += len(block)

            line_count += block.count(
                b"\n"
            )

            _report_progress(
                callback,
                1.0
                + (
                    4.0
                    * bytes_read
                    / file_size
                ),
                "Preparing Source",
            )

    return max(
        line_count - 1,
        1,
    )


def _parse_dates(
    series: pd.Series,
) -> pd.Series:

    return pd.to_datetime(
        series,
        errors="coerce",
        format="mixed",
    )


def _timestamp_ns(
    series: pd.Series,
) -> np.ndarray:

    return (
        series
        .astype(
            "datetime64[ns]"
        )
        .astype(
            "int64"
        )
        .to_numpy()
    )


def _read_source_structure():

    if not SOURCE_FILE.exists():
        raise DatasetGeneratorError(
            f"Raw source file not found: "
            f"{SOURCE_FILE}"
        )

    header = pd.read_csv(
        SOURCE_FILE,
        nrows=0,
    )

    columns = list(
        header.columns
    )

    required = [
        CELL_COLUMN,
        DATE_COLUMN,
    ]

    missing = [
        column
        for column in required
        if column not in columns
    ]

    if missing:
        raise DatasetGeneratorError(
            "Required columns missing: "
            + ", ".join(
                missing
            )
        )

    return columns


def _discover_grid(
    total_rows: int,
    progress_callback: ProgressCallback | None,
):

    cells = set()
    timestamp_ns_set = set()

    processed_rows = 0

    for chunk in pd.read_csv(
        SOURCE_FILE,
        usecols=[
            CELL_COLUMN,
            DATE_COLUMN,
        ],
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):

        raw_cells = (
            chunk[
                CELL_COLUMN
            ]
        )

        timestamps = _parse_dates(
            chunk[
                DATE_COLUMN
            ]
        )

        valid = (
            raw_cells.notna()
            & timestamps.notna()
        )

        if not valid.any():
            continue

        cell_values = (
            raw_cells[
                valid
            ]
            .astype(
                str
            )
            .str.strip()
        )

        cells.update(
            cell_values.unique()
        )

        values = _timestamp_ns(
            timestamps[
                valid
            ]
        )

        timestamp_ns_set.update(
            np.unique(
                values
            ).tolist()
        )

        processed_rows += len(
            chunk
        )

        _report_progress(
            progress_callback,
            5.0
            + (
                25.0
                * processed_rows
                / total_rows
            ),
            "Scanning Network Data",
        )


    if not cells:
        raise DatasetGeneratorError(
            "No valid cells found."
        )

    if not timestamp_ns_set:
        raise DatasetGeneratorError(
            "No valid timestamps found."
        )


    observed_ns = np.array(
        sorted(
            timestamp_ns_set
        ),
        dtype=np.int64,
    )


    global_start = pd.Timestamp(
        int(
            observed_ns.min()
        )
    )

    global_end = pd.Timestamp(
        int(
            observed_ns.max()
        )
    )


    timeline = pd.date_range(
        start=global_start,
        end=global_end,
        freq=(
            f"{RESOLUTION_MINUTES}min"
        ),
    )


    return (
        sorted(
            cells
        ),
        timeline,
        len(
            observed_ns
        ),
    )


def _build_presence_matrix(
    cells,
    timeline,
    total_rows: int,
    progress_callback: ProgressCallback | None,
):

    cell_to_index = {
        cell: index
        for index, cell
        in enumerate(
            cells
        )
    }

    timeline_ns = (
        timeline
        .to_numpy(
            dtype="datetime64[ns]"
        )
        .astype(
            "int64"
        )
    )

    timestamp_to_index = {
        int(value): index
        for index, value
        in enumerate(
            timeline_ns
        )
    }


    presence = np.zeros(
        (
            len(
                cells
            ),
            len(
                timeline
            ),
        ),
        dtype=np.bool_,
    )

    processed_rows = 0


    for chunk in pd.read_csv(
        SOURCE_FILE,
        usecols=[
            CELL_COLUMN,
            DATE_COLUMN,
        ],
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):

        timestamps = _parse_dates(
            chunk[
                DATE_COLUMN
            ]
        )

        raw_cells = (
            chunk[
                CELL_COLUMN
            ]
        )

        valid = (
            timestamps.notna()
            & raw_cells.notna()
        )

        if not valid.any():
            continue


        valid_cells = (
            raw_cells[
                valid
            ]
            .astype(
                str
            )
            .str.strip()
        )

        valid_timestamps = (
            timestamps[
                valid
            ]
        )


        row_indices = (
            valid_cells
            .map(
                cell_to_index
            )
        )

        ts_values = pd.Series(
            _timestamp_ns(
                valid_timestamps
            ),
            index=valid_timestamps.index,
        )

        column_indices = (
            ts_values
            .map(
                timestamp_to_index
            )
        )


        valid_grid = (
            row_indices.notna()
            & column_indices.notna()
        )

        if not valid_grid.any():
            continue


        rows = (
            row_indices[
                valid_grid
            ]
            .astype(
                int
            )
            .to_numpy()
        )

        cols = (
            column_indices[
                valid_grid
            ]
            .astype(
                int
            )
            .to_numpy()
        )


        presence[
            rows,
            cols
        ] = True

        processed_rows += len(
            chunk
        )

        _report_progress(
            progress_callback,
            30.0
            + (
                25.0
                * processed_rows
                / total_rows
            ),
            "Checking Cell Coverage",
        )


    return presence


def _find_best_window(
    presence,
    timeline,
):

    steps_per_day = int(
        (24 * 60)
        / RESOLUTION_MINUTES
    )

    history_steps = (
        HISTORY_DAYS
        * steps_per_day
    )

    ground_truth_steps = (
        GROUND_TRUTH_DAYS
        * steps_per_day
    )

    total_steps = (
        history_steps
        + ground_truth_steps
    )


    if len(
        timeline
    ) < total_steps:

        raise DatasetGeneratorError(
            "Raw dataset is too short "
            "for requested history + "
            "ground-truth window."
        )


    history_required = math.ceil(
        history_steps
        * COVERAGE_THRESHOLD
    )

    ground_truth_required = math.ceil(
        ground_truth_steps
        * COVERAGE_THRESHOLD
    )


    prefix = np.concatenate(
        [
            np.zeros(
                (
                    presence.shape[0],
                    1,
                ),
                dtype=np.int16,
            ),
            np.cumsum(
                presence,
                axis=1,
                dtype=np.int16,
            ),
        ],
        axis=1,
    )


    best = None

    max_start = (
        len(
            timeline
        )
        - total_steps
    )


    for start_idx in range(
        max_start + 1
    ):

        history_end_exclusive = (
            start_idx
            + history_steps
        )

        future_end_exclusive = (
            history_end_exclusive
            + ground_truth_steps
        )


        history_counts = (
            prefix[
                :,
                history_end_exclusive,
            ]
            - prefix[
                :,
                start_idx,
            ]
        )

        future_counts = (
            prefix[
                :,
                future_end_exclusive,
            ]
            - prefix[
                :,
                history_end_exclusive,
            ]
        )


        eligible_mask = (
            (
                history_counts
                >= history_required
            )
            & (
                future_counts
                >= ground_truth_required
            )
        )


        eligible_count = int(
            eligible_mask.sum()
        )


        if (
            best is None
            or eligible_count
            > best[
                "eligible_count"
            ]
        ):

            best = {
                "eligible_count": (
                    eligible_count
                ),
                "eligible_mask": (
                    eligible_mask.copy()
                ),
                "history_counts": (
                    history_counts.copy()
                ),
                "future_counts": (
                    future_counts.copy()
                ),
                "start_idx": (
                    start_idx
                ),
                "history_end_exclusive": (
                    history_end_exclusive
                ),
                "future_end_exclusive": (
                    future_end_exclusive
                ),
            }


    if best is None:
        raise DatasetGeneratorError(
            "Could not determine "
            "a valid generation window."
        )


    start_idx = best[
        "start_idx"
    ]

    history_end_exclusive = best[
        "history_end_exclusive"
    ]

    future_end_exclusive = best[
        "future_end_exclusive"
    ]


    best[
        "history_start"
    ] = timeline[
        start_idx
    ]

    best[
        "history_end"
    ] = timeline[
        history_end_exclusive
        - 1
    ]

    best[
        "ground_truth_start"
    ] = timeline[
        history_end_exclusive
    ]

    best[
        "ground_truth_end"
    ] = timeline[
        future_end_exclusive
        - 1
    ]

    best[
        "history_steps"
    ] = history_steps

    best[
        "ground_truth_steps"
    ] = ground_truth_steps


    return best


def _extract_generated_data(
    selected_cells,
    window,
    total_rows: int,
    progress_callback: ProgressCallback | None,
):

    selected_set = set(
        selected_cells
    )

    history_parts = []
    ground_truth_parts = []

    processed_rows = 0


    history_start = window[
        "history_start"
    ]

    history_end = window[
        "history_end"
    ]

    ground_truth_start = window[
        "ground_truth_start"
    ]

    ground_truth_end = window[
        "ground_truth_end"
    ]


    for chunk in pd.read_csv(
        SOURCE_FILE,
        chunksize=CHUNK_SIZE,
        low_memory=False,
    ):

        timestamps = _parse_dates(
            chunk[
                DATE_COLUMN
            ]
        )

        cells = (
            chunk[
                CELL_COLUMN
            ]
            .astype(
                str
            )
            .str.strip()
        )


        cell_mask = cells.isin(
            selected_set
        )


        history_mask = (
            cell_mask
            & timestamps.ge(
                history_start
            )
            & timestamps.le(
                history_end
            )
        )


        if history_mask.any():

            history = chunk.loc[
                history_mask
            ].copy()

            history[
                "__TIMESTAMP__"
            ] = timestamps[
                history_mask
            ].to_numpy()

            history_parts.append(
                history
            )


        future_mask = (
            cell_mask
            & timestamps.ge(
                ground_truth_start
            )
            & timestamps.le(
                ground_truth_end
            )
        )


        if future_mask.any():

            future = chunk.loc[
                future_mask
            ].copy()

            future[
                "__TIMESTAMP__"
            ] = timestamps[
                future_mask
            ].to_numpy()

            ground_truth_parts.append(
                future
            )


        processed_rows += len(
            chunk
        )

        _report_progress(
            progress_callback,
            60.0
            + (
                35.0
                * processed_rows
                / total_rows
            ),
            "Extracting Dataset",
        )


    if not history_parts:
        raise DatasetGeneratorError(
            "No forecast-input rows "
            "were extracted."
        )

    if not ground_truth_parts:
        raise DatasetGeneratorError(
            "No ground-truth rows "
            "were extracted."
        )


    history_df = pd.concat(
        history_parts,
        ignore_index=True,
    )

    ground_truth_df = pd.concat(
        ground_truth_parts,
        ignore_index=True,
    )


    history_df = (
        history_df
        .sort_values(
            [
                "__TIMESTAMP__",
                CELL_COLUMN,
            ]
        )
        .drop(
            columns=[
                "__TIMESTAMP__"
            ]
        )
        .reset_index(
            drop=True
        )
    )


    ground_truth_df = (
        ground_truth_df
        .sort_values(
            [
                "__TIMESTAMP__",
                CELL_COLUMN,
            ]
        )
        .drop(
            columns=[
                "__TIMESTAMP__"
            ]
        )
        .reset_index(
            drop=True
        )
    )


    return (
        history_df,
        ground_truth_df,
    )


def generate_dataset(
    cell_count: int,
    seed: int | None = None,
    progress_callback: ProgressCallback | None = None,
):

    if cell_count < 1:
        raise DatasetGeneratorError(
            "cell_count must be >= 1."
        )

    if (
        cell_count
        > MAX_GENERATED_CELLS
    ):
        raise DatasetGeneratorError(
            f"Maximum supported "
            f"cell_count is "
            f"{MAX_GENERATED_CELLS}."
        )


    _report_progress(
        progress_callback,
        0.0,
        "Starting Dataset Generation",
    )

    columns = _read_source_structure()

    total_source_rows = (
        _count_source_rows(
            progress_callback
        )
    )


    cells, timeline, observed_count = (
        _discover_grid(
            total_source_rows,
            progress_callback,
        )
    )


    presence = _build_presence_matrix(
        cells,
        timeline,
        total_source_rows,
        progress_callback,
    )


    _report_progress(
        progress_callback,
        56.0,
        "Selecting Leak-Safe Window",
    )

    window = _find_best_window(
        presence,
        timeline,
    )

    _report_progress(
        progress_callback,
        60.0,
        "Selecting Leak-Safe Window",
    )


    eligible_indices = np.flatnonzero(
        window[
            "eligible_mask"
        ]
    )


    eligible_count = len(
        eligible_indices
    )


    if cell_count > eligible_count:
        raise DatasetGeneratorError(
            f"Requested {cell_count} cells "
            f"but only {eligible_count} "
            f"cells meet the "
            f"{COVERAGE_THRESHOLD:.0%} "
            f"coverage rule."
        )


    if seed is None:
        seed = secrets.randbelow(
            2_147_483_647
        )


    rng = np.random.default_rng(
        seed
    )


    selected_indices = (
        rng.choice(
            eligible_indices,
            size=cell_count,
            replace=False,
        )
    )


    selected_cells = sorted(
        [
            cells[
                int(index)
            ]
            for index
            in selected_indices
        ]
    )


    (
        history_df,
        ground_truth_df,
    ) = _extract_generated_data(
        selected_cells,
        window,
        total_source_rows,
        progress_callback,
    )

    history_max, ground_truth_min = assert_history_before_ground_truth(
        history_df[DATE_COLUMN], ground_truth_df[DATE_COLUMN],
    )
    history_row_count = len(history_df)
    ground_truth_row_count = len(ground_truth_df)

    generation_id = (
        "GEN-"
        + datetime.now(
            timezone.utc
        ).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
    )


    generation_dir = (
        OUTPUT_ROOT
        / generation_id
    )

    generation_dir.mkdir(
        parents=True,
        exist_ok=False,
    )


    forecast_input_file = (
        generation_dir
        / "forecast_input.csv"
    )

    ground_truth_file = (
        generation_dir
        / "ground_truth.csv"
    )

    manifest_file = (
        generation_dir
        / "manifest.json"
    )


    _report_progress(
        progress_callback,
        96.0,
        "Writing Generated Files",
    )

    history_df.to_csv(
        forecast_input_file,
        index=False,
    )

    _report_progress(
        progress_callback,
        98.0,
        "Writing Generated Files",
    )

    ground_truth_df.to_csv(
        ground_truth_file,
        index=False,
    )

    # Release split frames before preparing features. Never reload the raw source.
    del history_df, ground_truth_df, presence
    model_ready = build_model_ready_history(
        forecast_input_file,
        chunksize=CHUNK_SIZE,
        progress_callback=lambda rows: _report_progress(
            progress_callback, 98.0 + 1.5 * rows / history_row_count,
            "Preparing Model-Ready History",
        ),
    )

    selected_history_counts = (
        window[
            "history_counts"
        ][
            selected_indices
        ]
    )

    selected_future_counts = (
        window[
            "future_counts"
        ][
            selected_indices
        ]
    )


    history_steps = int(
        window[
            "history_steps"
        ]
    )

    future_steps = int(
        window[
            "ground_truth_steps"
        ]
    )


    min_history_coverage = float(
        selected_history_counts.min()
        / history_steps
    )

    min_ground_truth_coverage = float(
        selected_future_counts.min()
        / future_steps
    )


    manifest = {
        "generation_id": (
            generation_id
        ),
        "source_file": str(
            SOURCE_FILE
        ),
        "source_columns": (
            columns
        ),
        "cell_count": int(
            cell_count
        ),
        "seed": int(
            seed
        ),
        "coverage_threshold": float(
            COVERAGE_THRESHOLD
        ),
        "eligible_cell_count": int(
            eligible_count
        ),
        "resolution_minutes": int(
            RESOLUTION_MINUTES
        ),
        "history_days": int(
            HISTORY_DAYS
        ),
        "history_steps": (
            history_steps
        ),
        "ground_truth_days": int(
            GROUND_TRUTH_DAYS
        ),
        "ground_truth_steps": (
            future_steps
        ),
        "history_start": str(
            window[
                "history_start"
            ]
        ),
        "history_end": str(
            window[
                "history_end"
            ]
        ),
        "cutoff": str(
            window[
                "history_end"
            ]
        ),
        "ground_truth_start": str(
            window[
                "ground_truth_start"
            ]
        ),
        "ground_truth_end": str(
            window[
                "ground_truth_end"
            ]
        ),
        "forecast_input_rows": history_row_count,
        "ground_truth_rows": ground_truth_row_count,
        "model_ready": model_ready,
        "history_max_timestamp": history_max,
        "ground_truth_min_timestamp": ground_truth_min,
        "minimum_selected_history_coverage": (
            round(
                min_history_coverage,
                6,
            )
        ),
        "minimum_selected_ground_truth_coverage": (
            round(
                min_ground_truth_coverage,
                6,
            )
        ),
        "observed_global_timestamps": int(
            observed_count
        ),
        "expected_global_grid_slots": int(
            len(
                timeline
            )
        ),
        "selected_cells": (
            selected_cells
        ),
        "leakage_control": {
            "split_before_forecast_preprocessing": True,
            "forecast_input_contains_future_rows": False,
            "ground_truth_is_separate_file": True,
            "future_kpi_values_used_for_cell_selection": False,
            "future_timestamp_presence_used_for_validation_quality_gate": True,
        },
    }


    manifest_file.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


    _report_progress(
        progress_callback,
        100.0,
        "Dataset Generated",
    )

    return {
        "generation_id": (
            generation_id
        ),
        "cell_count": int(
            cell_count
        ),
        "seed": int(
            seed
        ),
        "eligible_cell_count": int(
            eligible_count
        ),
        "coverage_threshold": float(
            COVERAGE_THRESHOLD
        ),
        "resolution_minutes": int(
            RESOLUTION_MINUTES
        ),
        "history_start": str(
            window[
                "history_start"
            ]
        ),
        "history_end": str(
            window[
                "history_end"
            ]
        ),
        "cutoff": str(
            window[
                "history_end"
            ]
        ),
        "ground_truth_start": str(
            window[
                "ground_truth_start"
            ]
        ),
        "ground_truth_end": str(
            window[
                "ground_truth_end"
            ]
        ),
        "forecast_input_rows": history_row_count,
        "ground_truth_rows": ground_truth_row_count,
        "model_ready_rows": model_ready["rows"],
        "model_ready_download": f"/dataset-generator/{generation_id}/model-ready-input",
        "minimum_history_coverage": (
            round(
                min_history_coverage,
                6,
            )
        ),
        "minimum_ground_truth_coverage": (
            round(
                min_ground_truth_coverage,
                6,
            )
        ),
        "forecast_input_download": (
            f"/dataset-generator/"
            f"{generation_id}/"
            f"forecast-input"
        ),
        "ground_truth_download": (
            f"/dataset-generator/"
            f"{generation_id}/"
            f"ground-truth"
        ),
        "manifest_download": (
            f"/dataset-generator/"
            f"{generation_id}/"
            f"manifest"
        ),
    }


def get_generation_file(
    generation_id: str,
    filename: str,
) -> Path:

    if (
        not generation_id.startswith(
            "GEN-"
        )
        or "/" in generation_id
        or "\\" in generation_id
        or ".." in generation_id
    ):
        raise DatasetGeneratorError(
            "Invalid generation_id."
        )


    generation_dir = (
        OUTPUT_ROOT
        / generation_id
    )


    file_path = (
        generation_dir
        / filename
    )


    if not file_path.exists():
        raise DatasetGeneratorError(
            f"Generated file not found: "
            f"{filename}"
        )


    return file_path


def get_status():

    return {
        "status": "ready"
        if SOURCE_FILE.exists()
        else "source_missing",
        "source_file": str(
            SOURCE_FILE
        ),
        "source_exists": (
            SOURCE_FILE.exists()
        ),
        "resolution_minutes": (
            RESOLUTION_MINUTES
        ),
        "history_days": (
            HISTORY_DAYS
        ),
        "ground_truth_days": (
            GROUND_TRUTH_DAYS
        ),
        "coverage_threshold": (
            COVERAGE_THRESHOLD
        ),
        "max_generated_cells": (
            MAX_GENERATED_CELLS
        ),
    }
