import hashlib
import gc
import json
import os
import time
import threading
from pathlib import Path

import joblib
import numpy as np
import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]

DATA_DIR = PROJECT_ROOT / "data" / "processed"
CLUSTERING_MODELS_DIR = PROJECT_ROOT / "models" / "clustering"
FORECASTING_MODELS_DIR = PROJECT_ROOT / "models" / "forecasting"

SCHEMA_FILE = DATA_DIR / "t1_discover_dataset_schema.json"
MAPPING_FILE = DATA_DIR / "t3.confirmed_kpi_mapping.csv"

FORECAST_MODEL_N_JOBS = 1
ENGINE_VERSION = "BASELINE-01"
FORECAST_MODEL_LOCK = threading.Lock()


def perf_add(bucket, key, seconds):
    bucket[key] = bucket.get(key, 0.0) + float(seconds)


class ForecastMetadata:

    def __init__(self):
        missing = [
            str(path)
            for path in (SCHEMA_FILE, MAPPING_FILE)
            if not path.exists()
        ]
        if missing:
            raise FileNotFoundError(
                "Required forecasting artifacts are missing: " + ", ".join(missing)
            )
        with open(SCHEMA_FILE, "r", encoding="utf-8") as f:
            self.schema = json.load(f)
        self.mapping_df = pd.read_csv(MAPPING_FILE)


class ForecastEngine(ForecastMetadata):

    def __init__(self, *, load_clustering=True, load_forecasting=True, inspect_runtime=True):
        self.load_clustering = load_clustering
        self.load_forecasting = load_forecasting
        self.inspect_runtime = inspect_runtime
        self.schema = None
        self.mapping_df = None
        self.clustering_models = {}
        self.forecasting_models = {}
        self.runtime_config = {}

        self.load_artifacts()

    def load_artifacts(self):
        super().__init__()

        self.clustering_models = {}

        if self.load_clustering and CLUSTERING_MODELS_DIR.exists():
            for path in CLUSTERING_MODELS_DIR.glob("*.joblib"):
                self.clustering_models[path.stem] = joblib.load(path)

        self.forecasting_models = {}

        if not self.load_forecasting:
            return

        if FORECASTING_MODELS_DIR.exists():
            for path in FORECASTING_MODELS_DIR.glob("*.joblib"):
                # Keep paths, never resident RF artifacts, in the engine cache.
                self.forecasting_models[path.stem] = path

        if not self.forecasting_models:
            raise FileNotFoundError(
                f"No forecasting .joblib models found in "
                f"{FORECASTING_MODELS_DIR}"
            )

        if self.inspect_runtime:
            self.runtime_config = self.configure_forecasting_runtime()

    def _load_resident_forecasting_models(self, kpis, artifacts):
        # Run-scoped ownership: the cached engine continues to store paths only.
        required = {f"{kpi}_rf_model" for kpi in kpis}
        for key, path in self.forecasting_models.items():
            if key not in required:
                continue
            artifact = joblib.load(path)
            artifacts[key] = artifact
            model = artifact.get("model") if isinstance(artifact, dict) else artifact
            if model is not None and hasattr(model, "n_jobs"):
                if hasattr(model, "set_params"):
                    model.set_params(n_jobs=FORECAST_MODEL_N_JOBS)
                else:
                    model.n_jobs = FORECAST_MODEL_N_JOBS

    def configure_forecasting_runtime(self):
        # Status retains its existing runtime fields; inspect each artifact
        # separately so even status initialization holds at most one RF.
        with FORECAST_MODEL_LOCK:
            return self._configure_forecasting_runtime()

    def _configure_forecasting_runtime(self):

        details = []
        configured_models = 0

        for model_key, path in self.forecasting_models.items():
            artifact = joblib.load(path)

            model = (
                artifact.get("model")
                if isinstance(artifact, dict)
                else artifact
            )

            if model is None:
                del artifact
                gc.collect()
                continue

            before = (
                getattr(model, "n_jobs", None)
                if hasattr(model, "n_jobs")
                else None
            )

            supported = hasattr(model, "n_jobs")
            applied = False

            if supported:
                try:

                    if hasattr(model, "set_params"):
                        model.set_params(
                            n_jobs=FORECAST_MODEL_N_JOBS
                        )
                    else:
                        model.n_jobs = FORECAST_MODEL_N_JOBS

                    applied = True
                    configured_models += 1

                except Exception:
                    applied = False

            after = (
                getattr(model, "n_jobs", None)
                if hasattr(model, "n_jobs")
                else None
            )

            details.append(
                {
                    "model_key": model_key,
                    "model_type": type(model).__name__,
                    "supports_n_jobs": bool(supported),
                    "n_jobs_before": before,
                    "n_jobs_after": after,
                    "applied": bool(applied),
                }
            )
            del model, artifact
            gc.collect()

        return {
            "requested_n_jobs": FORECAST_MODEL_N_JOBS,
            "configured_models": configured_models,
            "total_forecasting_models": len(
                self.forecasting_models
            ),
            "runtime_visible_cpus": os.cpu_count(),
            "models": details,
        }

    @staticmethod
    def build_forecast_signature(
        df_forecast,
        cell_col,
        time_col,
        kpis,
    ):

        if df_forecast is None or df_forecast.empty:
            return "EMPTY"

        forecast_cols = [
            f"{kpi}_FORECAST"
            for kpi in kpis
            if f"{kpi}_FORECAST" in df_forecast.columns
        ]

        cols = [cell_col, time_col] + forecast_cols

        sig_df = df_forecast[cols].copy()

        sig_df[cell_col] = sig_df[cell_col].astype(str)

        sig_df[time_col] = pd.to_datetime(
            sig_df[time_col],
            format="mixed",
        )

        sig_df = (
            sig_df
            .sort_values([cell_col, time_col])
            .reset_index(drop=True)
        )

        cell_bytes = "\n".join(
            sig_df[cell_col].tolist()
        ).encode("utf-8")

        time_bytes = "\n".join(
            sig_df[time_col]
            .dt.strftime("%Y-%m-%dT%H:%M:%S.%f")
            .tolist()
        ).encode("utf-8")

        numeric = (
            sig_df[forecast_cols]
            .apply(pd.to_numeric, errors="coerce")
            .to_numpy(dtype=np.float64)
        )

        numeric = np.round(numeric, 10)

        numeric_bytes = np.ascontiguousarray(
            numeric.astype("<f8", copy=False)
        ).tobytes()

        digest = hashlib.sha256()

        digest.update(cell_bytes)
        digest.update(b"\x1e")
        digest.update(time_bytes)
        digest.update(b"\x1e")
        digest.update(numeric_bytes)

        return digest.hexdigest()[:16]

    @staticmethod
    def build_forecast_export(
        df_forecast,
        cell_col,
        time_col,
        kpis,
    ):

        forecast_cols = [
            f"{kpi}_FORECAST"
            for kpi in kpis
            if f"{kpi}_FORECAST" in df_forecast.columns
        ]

        export_cols = [
            cell_col,
            time_col,
        ] + forecast_cols

        return df_forecast.loc[
            :,
            export_cols
        ].copy()

    def preprocess_and_extract_features(
        self,
        df_raw,
        perf=None,
    ):

        if perf is None:
            perf = {}

        t0 = time.perf_counter()

        time_col = self.schema.get(
            "selected_date_column",
            "SDATE",
        )

        cell_cols = self.schema.get(
            "cell_columns",
            [],
        )

        cell_col = (
            cell_cols[0]
            if cell_cols
            else "CELL_NAME"
        )

        if time_col not in df_raw.columns:
            raise ValueError(
                f"Required timestamp column not found: {time_col}"
            )

        if cell_col not in df_raw.columns:
            raise ValueError(
                f"Required cell column not found: {cell_col}"
            )

        raw_col_name = (
            "RAW_COLUMN_NAME"
            if "RAW_COLUMN_NAME" in self.mapping_df.columns
            else self.mapping_df.columns[0]
        )

        std_col_name = (
            "STANDARDIZED_NAME"
            if "STANDARDIZED_NAME" in self.mapping_df.columns
            else self.mapping_df.columns[1]
        )

        rename_dict = {}

        for _, row in self.mapping_df.iterrows():

            raw_col = str(
                row[raw_col_name]
            ).strip()

            std_col = str(
                row[std_col_name]
            ).strip()

            if raw_col in df_raw.columns:
                rename_dict[raw_col] = std_col

        df = df_raw.rename(
            columns=rename_dict
        )
        # pandas 3 Copy-on-Write isolates subsequent assignments from df_raw.

        perf_add(
            perf,
            "KPI mapping + dataframe copy",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()

        df[time_col] = pd.to_datetime(
            df[time_col],
            format="mixed",
        )

        df = (
            df
            .sort_values([cell_col, time_col])
            .reset_index(drop=True)
        )

        perf_add(
            perf,
            "Datetime parse + sort",
            time.perf_counter() - t0,
        )

        # Choose positions before the wide feature table exists, but do not
        # discard any input until all original clustering checks have run.
        # Preserve duplicates, NaT and null cell groups exactly as before.
        history_rows = df.groupby(
            cell_col, sort=False, observed=True, dropna=False
        ).tail(96).index

        t0 = time.perf_counter()

        df["HOUR"] = df[time_col].dt.hour
        df["MINUTE"] = df[time_col].dt.minute
        df["DAY_OF_WEEK"] = df[time_col].dt.dayofweek

        df["IS_WEEKEND"] = (
            df["DAY_OF_WEEK"]
            .isin([5, 6])
            .astype(int)
        )

        df["HOUR_SIN"] = np.sin(
            2 * np.pi * df["HOUR"] / 24.0
        )

        df["HOUR_COS"] = np.cos(
            2 * np.pi * df["HOUR"] / 24.0
        )

        df["DOW_SIN"] = np.sin(
            2 * np.pi * df["DAY_OF_WEEK"] / 7.0
        )

        df["DOW_COS"] = np.cos(
            2 * np.pi * df["DAY_OF_WEEK"] / 7.0
        )

        exclude = [
            cell_col,
            time_col,
            "HOUR",
            "MINUTE",
            "DAY_OF_WEEK",
            "IS_WEEKEND",
            "HOUR_SIN",
            "HOUR_COS",
            "DOW_SIN",
            "DOW_COS",
        ]

        kpis = [
            c
            for c in df.columns
            if c not in exclude
        ]

        if not kpis:
            raise ValueError(
                "No KPI columns were discovered after KPI mapping."
            )

        perf_add(
            perf,
            "Temporal features + KPI discovery",
            time.perf_counter() - t0,
        )

        t0 = time.perf_counter()

        cluster_predict_calls = 0

        for kpi in kpis:

            behavior_key = (
                f"{kpi}_behavior_kmeans"
            )

            value_key = (
                f"{kpi}_value_kmeans"
            )

            for model_key, suffix in [
                (
                    behavior_key,
                    "BEHAVIOR_CLUSTER",
                ),
                (
                    value_key,
                    "VALUE_CLUSTER",
                ),
            ]:

                if model_key not in self.clustering_models:
                    continue

                art = self.clustering_models[
                    model_key
                ]

                model = (
                    art.get("model")
                    if isinstance(art, dict)
                    else art
                )

                feats = (
                    art.get("feature_names")
                    if isinstance(art, dict)
                    else None
                )

                if model is None:
                    continue

                n_expected = getattr(
                    model,
                    "n_features_in_",
                    None,
                )

                if feats:

                    X_in = df.reindex(
                        columns=feats,
                        fill_value=0,
                    )

                else:

                    X_in = df[[kpi]]

                if (
                    n_expected is not None
                    and X_in.shape[1] != n_expected
                ):

                    if X_in.shape[1] > n_expected:

                        X_in = X_in.iloc[
                            :,
                            :n_expected,
                        ]

                    else:

                        for i in range(
                            X_in.shape[1],
                            n_expected,
                        ):

                            X_in[f"dummy_{i}"] = 0

                preds = model.predict(X_in)

                cluster_predict_calls += 1

                df[
                    f"{kpi}_{suffix}"
                ] = [
                    f"CLUSTER_{c}"
                    for c in preds
                ]
                del X_in, preds

        perf_add(
            perf,
            "Clustering predictions",
            time.perf_counter() - t0,
        )

        perf["cluster_predict_calls"] = int(
            cluster_predict_calls
        )

        return (
            df.loc[history_rows].copy(),
            cell_col,
            time_col,
            kpis,
        )

    def run_recursive_forecasting(
        self,
        df_feat,
        cell_col,
        time_col,
        kpis,
        horizon_steps,
        perf=None,
        progress_callback=None,
        resident_models=None,
    ):

        if perf is None:
            perf = {}

        unique_cells = list(
            df_feat[cell_col].unique()
        )

        total_cells = len(unique_cells)

        all_future_rows = []
        output_columns = [cell_col, time_col] + [f"{kpi}_FORECAST" for kpi in kpis]

        failed_cell_set = set()

        model_predict_calls = 0
        history_concat_calls = 0
        state_update_calls = 0
        batch_predict_rows = 0
        rows_generated = 0

        t0 = time.perf_counter()

        cell_to_pos = {
            cell: idx
            for idx, cell in enumerate(
                unique_cells
            )
        }

        cell_values = np.asarray(
            unique_cells,
            dtype=object,
        )

        last_timestamps = np.full(
            total_cells,
            np.datetime64("NaT"),
            dtype="datetime64[ns]",
        )

        history_lengths = np.zeros(
            total_cells,
            dtype=np.int16,
        )

        write_positions = np.zeros(
            total_cells,
            dtype=np.int16,
        )

        kpi_buffers = {
            kpi: np.full(
                (total_cells, 96),
                np.nan,
                dtype=float,
            )
            for kpi in kpis
        }

        cluster_cols = [
            col
            for col in df_feat.columns
            if col.endswith("_CLUSTER")
        ]

        cluster_values = {
            col: np.full(
                total_cells,
                np.nan,
                dtype=object,
            )
            for col in cluster_cols
        }

        try:

            grouped = df_feat.groupby(
                cell_col,
                sort=False,
                observed=True,
            )

        except TypeError:

            grouped = df_feat.groupby(
                cell_col,
                sort=False,
            )

        for cell, cell_history in grouped:

            pos = cell_to_pos.get(cell)

            if pos is None:
                continue

            try:

                if cell_history.empty:
                    failed_cell_set.add(cell)
                    continue

                last_ts = pd.to_datetime(
                    cell_history[time_col].iloc[-1]
                )

                if pd.isna(last_ts):
                    raise ValueError(
                        f"Invalid timestamp for cell {cell}"
                    )

                last_timestamps[pos] = np.datetime64(
                    last_ts.to_datetime64()
                )

                n_hist = min(
                    len(cell_history),
                    96,
                )

                if n_hist < 1:
                    raise ValueError(
                        f"No history available for cell {cell}"
                    )

                history_lengths[pos] = n_hist

                write_positions[pos] = (
                    n_hist % 96
                )

                for kpi in kpis:

                    vals = pd.to_numeric(
                        cell_history[
                            kpi
                        ].iloc[-n_hist:],
                        errors="coerce",
                    ).to_numpy(
                        dtype=float
                    )

                    if len(vals) == 0:
                        raise ValueError(
                            f"No KPI history available for "
                            f"{cell} / {kpi}"
                        )

                    kpi_buffers[
                        kpi
                    ][
                        pos,
                        :n_hist,
                    ] = vals

                for col in cluster_cols:

                    cluster_values[
                        col
                    ][
                        pos
                    ] = cell_history[
                        col
                    ].iloc[-1]

            except Exception:

                failed_cell_set.add(cell)

        perf_add(
            perf,
            "Cell state initialization",
            time.perf_counter() - t0,
        )

        active_mask = np.ones(
            total_cells,
            dtype=bool,
        )

        for cell in failed_cell_set:

            pos = cell_to_pos.get(cell)

            if pos is not None:
                active_mask[pos] = False

        hour_axis = np.arange(
            24,
            dtype=float,
        )

        dow_axis = np.arange(
            7,
            dtype=float,
        )

        hour_sin_lut = np.sin(
            2 * np.pi * hour_axis / 24.0
        )

        hour_cos_lut = np.cos(
            2 * np.pi * hour_axis / 24.0
        )

        dow_sin_lut = np.sin(
            2 * np.pi * dow_axis / 7.0
        )

        dow_cos_lut = np.cos(
            2 * np.pi * dow_axis / 7.0
        )

        for step in range(
            1,
            horizon_steps + 1,
        ):

            active_idx = np.flatnonzero(
                active_mask
            )

            if active_idx.size == 0:
                break

            t0 = time.perf_counter()

            future_times_np = (
                last_timestamps[
                    active_idx
                ]
                + np.timedelta64(
                    step * 15,
                    "m",
                )
            )

            future_times = pd.DatetimeIndex(
                future_times_np
            )

            hours = future_times.hour.to_numpy(
                dtype=np.int16
            )

            minutes = future_times.minute.to_numpy(
                dtype=np.int16
            )

            dows = (
                future_times
                .dayofweek
                .to_numpy(
                    dtype=np.int16
                )
            )

            step_data = {
                cell_col: cell_values[
                    active_idx
                ],
                time_col: future_times,
                "HOUR": hours,
                "MINUTE": minutes,
                "DAY_OF_WEEK": dows,
                "IS_WEEKEND": np.isin(
                    dows,
                    [5, 6],
                ).astype(
                    np.int8
                ),
                "HOUR_SIN": hour_sin_lut[
                    hours
                ],
                "HOUR_COS": hour_cos_lut[
                    hours
                ],
                "DOW_SIN": dow_sin_lut[
                    dows
                ],
                "DOW_COS": dow_cos_lut[
                    dows
                ],
            }

            active_lengths = history_lengths[
                active_idx
            ]

            active_write_pos = write_positions[
                active_idx
            ]

            for kpi in kpis:

                buf = kpi_buffers[
                    kpi
                ]

                lag1 = buf[
                    active_idx,
                    (
                        active_write_pos - 1
                    ) % 96,
                ]

                lag2_candidate = buf[
                    active_idx,
                    (
                        active_write_pos - 2
                    ) % 96,
                ]

                lag4_candidate = buf[
                    active_idx,
                    (
                        active_write_pos - 4
                    ) % 96,
                ]

                lag96_candidate = buf[
                    active_idx,
                    active_write_pos % 96,
                ]

                step_data[
                    f"{kpi}_LAG_1"
                ] = lag1

                step_data[
                    f"{kpi}_LAG_2"
                ] = np.where(
                    active_lengths >= 2,
                    lag2_candidate,
                    lag1,
                )

                step_data[
                    f"{kpi}_LAG_4"
                ] = np.where(
                    active_lengths >= 4,
                    lag4_candidate,
                    lag1,
                )

                step_data[
                    f"{kpi}_LAG_96"
                ] = np.where(
                    active_lengths >= 96,
                    lag96_candidate,
                    lag1,
                )

            for col in cluster_cols:

                if step == 1:

                    step_data[
                        col
                    ] = cluster_values[
                        col
                    ][
                        active_idx
                    ]

                else:

                    step_data[
                        col
                    ] = np.full(
                        active_idx.size,
                        np.nan,
                        dtype=object,
                    )

            step_df = pd.DataFrame(
                step_data
            )

            perf_add(
                perf,
                "Future row + lag feature build",
                time.perf_counter() - t0,
            )

            t0 = time.perf_counter()

            valid_step_mask = np.ones(
                len(step_df),
                dtype=bool,
            )

            for kpi in kpis:

                model_key = (
                    f"{kpi}_rf_model"
                )

                with FORECAST_MODEL_LOCK:
                    art = model = None
                    try:
                        if (
                            model_key
                            in self.forecasting_models
                        ):

                            art = (
                                resident_models[model_key]
                                if resident_models is not None
                                else joblib.load(self.forecasting_models[model_key])
                            )

                            model = (
                                art.get("model")
                                if isinstance(
                                    art,
                                    dict,
                                )
                                else art
                            )

                            if model is not None and hasattr(model, "n_jobs"):
                                try:
                                    if hasattr(model, "set_params"):
                                        model.set_params(n_jobs=FORECAST_MODEL_N_JOBS)
                                    else:
                                        model.n_jobs = FORECAST_MODEL_N_JOBS
                                except Exception:
                                    pass

                            feats = (
                                art.get(
                                    "feature_names",
                                    [],
                                )
                                if isinstance(
                                    art,
                                    dict,
                                )
                                else []
                            )

                            if (
                                model is not None
                                and hasattr(
                                    model,
                                    "predict",
                                )
                            ):

                                X_input = step_df.reindex(
                                    columns=feats,
                                    fill_value=0,
                                )

                                try:

                                    pred_values = np.asarray(
                                        model.predict(
                                            X_input
                                        ),
                                        dtype=float,
                                    )

                                    model_predict_calls += 1

                                    batch_predict_rows += len(
                                        X_input
                                    )

                                except Exception:

                                    pred_values = np.full(
                                        len(step_df),
                                        np.nan,
                                        dtype=float,
                                    )

                                    for pos, (_, row) in enumerate(
                                        X_input.iterrows()
                                    ):

                                        try:

                                            pred_values[
                                                pos
                                            ] = float(
                                                model.predict(
                                                    row
                                                    .to_frame()
                                                    .T
                                                )[0]
                                            )

                                            model_predict_calls += 1

                                        except Exception:

                                            valid_step_mask[
                                                pos
                                            ] = False

                            else:

                                pred_values = pd.to_numeric(
                                    step_df[
                                        f"{kpi}_LAG_1"
                                    ],
                                    errors="coerce",
                                ).to_numpy(
                                    dtype=float
                                )

                        else:

                            pred_values = pd.to_numeric(
                                step_df[
                                    f"{kpi}_LAG_1"
                                ],
                                errors="coerce",
                            ).to_numpy(
                                dtype=float
                            )

                    finally:
                        # Raw input releases each model; prepared input keeps the
                        # run-owned dictionary alive until forecasting completes.
                        art = model = None
                        if resident_models is None:
                            gc.collect()

                step_df[
                    f"{kpi}_FORECAST"
                ] = pred_values

                step_df[
                    kpi
                ] = pred_values

                valid_step_mask &= np.isfinite(
                    pred_values
                )

            perf_add(
                perf,
                "Forecast model predict calls",
                time.perf_counter() - t0,
            )

            if not bool(
                valid_step_mask.all()
            ):

                bad_idx = active_idx[
                    ~valid_step_mask
                ]

                for pos in bad_idx:

                    failed_cell_set.add(
                        unique_cells[
                            int(pos)
                        ]
                    )

                    active_mask[
                        int(pos)
                    ] = False

                active_idx = active_idx[
                    valid_step_mask
                ]

                step_df = (
                    step_df
                    .loc[valid_step_mask]
                    .reset_index(drop=True)
                )

            if step_df.empty:
                break

            all_future_rows.append(
                step_df.loc[:, output_columns].copy()
            )

            t0 = time.perf_counter()

            current_write_pos = write_positions[
                active_idx
            ].copy()

            for kpi in kpis:

                kpi_buffers[
                    kpi
                ][
                    active_idx,
                    current_write_pos,
                ] = pd.to_numeric(
                    step_df[kpi],
                    errors="coerce",
                ).to_numpy(
                    dtype=float
                )

            write_positions[
                active_idx
            ] = (
                current_write_pos + 1
            ) % 96

            history_lengths[
                active_idx
            ] = np.minimum(
                history_lengths[
                    active_idx
                ] + 1,
                96,
            )

            state_update_calls += int(
                active_idx.size
            )

            perf_add(
                perf,
                "Recursive state update",
                time.perf_counter() - t0,
            )

            rows_generated += int(
                len(step_df)
            )

            if progress_callback is not None:

                try:

                    progress_callback(
                        {
                            "stage": "recursive_forecasting",
                            "current_step": int(step),
                            "total_steps": int(
                                horizon_steps
                            ),
                            "active_cells": int(
                                active_idx.size
                            ),
                            "total_cells": int(
                                total_cells
                            ),
                            "rows_generated": int(
                                rows_generated
                            ),
                            "expected_rows": int(
                                total_cells
                                * horizon_steps
                            ),
                            "failed_cells": int(
                                len(
                                    failed_cell_set
                                )
                            ),
                            "progress_percent": round(
                                (
                                    step
                                    / horizon_steps
                                )
                                * 100.0,
                                2,
                            ),
                        }
                    )

                except Exception:

                    pass

        t0 = time.perf_counter()

        df_future = (
            pd.concat(
                all_future_rows,
                ignore_index=True,
            )
            if all_future_rows
            else pd.DataFrame()
        )
        all_future_rows.clear()

        if not df_future.empty:

            cell_order = {
                cell: idx
                for idx, cell in enumerate(
                    unique_cells
                )
            }

            df_future[
                "__CELL_ORDER__"
            ] = df_future[
                cell_col
            ].map(
                cell_order
            )

            df_future = (
                df_future
                .sort_values(
                    [
                        "__CELL_ORDER__",
                        time_col,
                    ]
                )
                .drop(
                    columns="__CELL_ORDER__"
                )
                .reset_index(drop=True)
            )

        perf_add(
            perf,
            "Final forecast pd.concat",
            time.perf_counter() - t0,
        )

        successful_cells = (
            total_cells
            - len(failed_cell_set)
        )

        failed_cells = len(
            failed_cell_set
        )

        perf[
            "model_predict_calls"
        ] = int(
            model_predict_calls
        )

        perf[
            "history_concat_calls"
        ] = int(
            history_concat_calls
        )

        perf[
            "state_update_calls"
        ] = int(
            state_update_calls
        )

        perf[
            "batch_predict_rows"
        ] = int(
            batch_predict_rows
        )

        return (
            df_future,
            successful_cells,
            failed_cells,
            total_cells,
        )

    def forecast(
        self,
        df_raw,
        horizon_steps,
        progress_callback=None,
        *,
        prepared_columns=None,
        resident_models=False,
    ):

        allowed_horizons = {
            1,
            2,
            4,
            6,
            12,
            24,
            48,
            96,
        }

        if horizon_steps not in allowed_horizons:

            raise ValueError(
                "horizon_steps must be one of: "
                "1, 2, 4, 6, 12, 24, 48, 96"
            )

        if resident_models and prepared_columns is None:
            raise ValueError("Resident models require prepared model-ready input.")

        perf = {
            "preprocess": {},
            "forecast": {},
        }

        total_started = time.perf_counter()

        phase_started = time.perf_counter()

        if progress_callback is not None:

            try:

                progress_callback(
                    {
                        "stage": "feature_engineering",
                        "current_step": 0,
                        "rows_generated": 0,
                        "progress_percent": 0.0,
                    }
                )

            except Exception:

                pass

        if prepared_columns is None:
            (
                df_feat,
                cell_col,
                time_col,
                kpis,
            ) = self.preprocess_and_extract_features(
                df_raw,
                perf=perf["preprocess"],
            )
        else:
            # Generated artifacts already contain the exact history window.
            # Recursive features, model order and state updates remain below.
            cell_col, time_col, kpis = prepared_columns
            df_feat = df_raw

        preprocess_seconds = (
            time.perf_counter()
            - phase_started
        )

        phase_started = time.perf_counter()

        artifacts = {} if resident_models else None
        try:
            if resident_models:
                with FORECAST_MODEL_LOCK:
                    self._load_resident_forecasting_models(kpis, artifacts)
            (
                df_forecast,
                successful_cells,
                failed_cells,
                total_cells,
            ) = self.run_recursive_forecasting(
                df_feat,
                cell_col,
                time_col,
                kpis,
                horizon_steps,
                perf=perf["forecast"],
                progress_callback=progress_callback,
                resident_models=artifacts,
            )
        finally:
            if artifacts is not None:
                artifacts.clear()
                gc.collect()
        del df_feat

        forecast_seconds = (
            time.perf_counter()
            - phase_started
        )

        total_seconds = (
            time.perf_counter()
            - total_started
        )

        if progress_callback is not None:

            try:

                progress_callback(
                    {
                        "stage": "finalizing",
                        "current_step": int(
                            horizon_steps
                        ),
                        "total_steps": int(
                            horizon_steps
                        ),
                        "rows_generated": int(
                            len(df_forecast)
                        ),
                        "progress_percent": 100.0,
                    }
                )

            except Exception:

                pass

        export_df = self.build_forecast_export(
            df_forecast,
            cell_col,
            time_col,
            kpis,
        )

        signature = self.build_forecast_signature(
            df_forecast,
            cell_col,
            time_col,
            kpis,
        )

        return {
            "df_forecast": df_forecast,
            "export_df": export_df,
            "cell_col": cell_col,
            "time_col": time_col,
            "kpis": kpis,
            "successful_cells": successful_cells,
            "failed_cells": failed_cells,
            "total_cells": total_cells,
            "forecast_rows": len(export_df),
            "signature": signature,
            "preprocess_seconds": preprocess_seconds,
            "forecast_seconds": forecast_seconds,
            "total_seconds": total_seconds,
            "performance": perf,
        }
