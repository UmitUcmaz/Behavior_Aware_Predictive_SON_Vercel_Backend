import numpy as np
import pandas as pd

from ml_engine.forecast_engine import PROJECT_ROOT


RUNS_DIR = (
    PROJECT_ROOT
    / "data"
    / "outputs"
    / "runs"
)


DEFAULT_RULES = {
    "es_prb_threshold": 30.0,
    "es_max_active_users": 10.0,
    "es_min_steps": 1,
    "es_max_steps": 2,

    "mlb_prb_threshold": 80.0,
    "mlb_steps": 2,

    "cap_prb_threshold": 80.0,
    "cap_steps": 2,
}


REQUIRED_COLUMNS = [
    "CELL_NAME",
    "SDATE",
    "UL_PRB_UTILIZATION_FORECAST",
    "DL_PRB_UTILIZATION_FORECAST",
    "ACTIVE_USERS_FORECAST",
]




from datetime import timedelta


def _format_time_window_v6(
    start_dt,
    end_dt,
    resolution_minutes=15,
):
    """
    Formats SON table time window.

    If start == end, end is shifted by one resolution step so:
    23:45 -> 00:00 instead of 23:45 -> 23:45
    """

    if start_dt is None:
        return "—"

    if end_dt is None:
        end_dt = start_dt

    if start_dt == end_dt:
        end_dt = end_dt + timedelta(
            minutes=resolution_minutes
        )

    else:
        end_dt = end_dt + timedelta(
            minutes=resolution_minutes
        )

    start_txt = start_dt.strftime("%H:%M")
    end_txt = end_dt.strftime("%H:%M")

    duration_minutes = int(
        max(
            resolution_minutes,
            (end_dt - start_dt).total_seconds() // 60,
        )
    )

    return f"{start_txt} - {end_txt} ({duration_minutes} mins)"


def get_son_service_status():

    return {
        "status": "ready",
        "service": "son",
        "engine": "independent-module-rule-engine-v5",
        "default_rules": DEFAULT_RULES,
        "modules": [
            "ES",
            "MLB",
            "CAP",
        ],
    }


def list_son_forecast_runs(
    limit=50,
):

    if not RUNS_DIR.exists():
        return []

    results = []

    for run_dir in sorted(
        RUNS_DIR.glob("FR-*"),
        reverse=True,
    ):

        forecast_path = (
            run_dir
            / "forecast.csv"
        )

        if not forecast_path.exists():
            continue

        try:

            df = pd.read_csv(
                forecast_path,
                usecols=[
                    "CELL_NAME",
                    "SDATE",
                ],
            )

            per_cell_steps = (
                df.groupby(
                    "CELL_NAME"
                )
                .size()
            )

            horizon_steps = (
                int(
                    per_cell_steps.median()
                )
                if not per_cell_steps.empty
                else 0
            )

            parsed_times = pd.to_datetime(
                df[
                    "SDATE"
                ],
                format="mixed",
                errors="coerce",
            )

            valid_times = (
                parsed_times.dropna()
            )

            forecast_start = (
                valid_times.min().isoformat()
                if not valid_times.empty
                else None
            )

            forecast_end = (
                valid_times.max().isoformat()
                if not valid_times.empty
                else None
            )

            results.append(
                {
                    "run_id": run_dir.name,
                    "forecast_rows": int(
                        len(df)
                    ),
                    "cells": int(
                        df[
                            "CELL_NAME"
                        ].nunique()
                    ),
                    "horizon_steps": (
                        horizon_steps
                    ),
                    "forecast_start": (
                        forecast_start
                    ),
                    "forecast_end": (
                        forecast_end
                    ),
                }
            )

        except Exception:
            continue

        if len(results) >= int(limit):
            break

    return results


def _forecast_path(
    run_id,
):

    if (
        not run_id
        or not str(
            run_id
        ).startswith("FR-")
    ):

        raise ValueError(
            "Invalid forecast run id."
        )

    path = (
        RUNS_DIR
        / str(run_id)
        / "forecast.csv"
    )

    if not path.exists():

        raise FileNotFoundError(
            (
                "Forecast run not found: "
                f"{run_id}"
            )
        )

    return path


def _merge_rules(
    rules,
):

    merged = dict(
        DEFAULT_RULES
    )

    if rules:

        for key, value in (
            rules.items()
        ):

            if (
                key in merged
                and value is not None
            ):

                if key.endswith(
                    "_steps"
                ):

                    merged[
                        key
                    ] = int(
                        value
                    )

                else:

                    merged[
                        key
                    ] = float(
                        value
                    )

    if (
        merged[
            "es_min_steps"
        ]
        >
        merged[
            "es_max_steps"
        ]
    ):

        raise ValueError(
            (
                "ES minimum duration "
                "cannot exceed maximum duration."
            )
        )

    return merged


def _time_value(
    value,
):

    return pd.Timestamp(
        value
    ).strftime(
        "%H:%M"
    )


def _time_value_end(
    value,
    resolution_minutes=15,
):

    return (
        pd.Timestamp(
            value
        )
        + pd.Timedelta(
            minutes=resolution_minutes
        )
    ).strftime(
        "%H:%M"
    )


def evaluate_son_run(
    run_id,
    rules=None,
):

    rules = (
        _merge_rules(
            rules
        )
    )

    forecast_path = (
        _forecast_path(
            run_id
        )
    )

    df = pd.read_csv(
        forecast_path
    )

    missing = [
        column
        for column in REQUIRED_COLUMNS
        if column not in df.columns
    ]

    if missing:

        raise ValueError(
            (
                "Forecast output is missing "
                "required SON columns: "
                + ", ".join(
                    missing
                )
            )
        )

    df[
        "CELL_NAME"
    ] = (
        df[
            "CELL_NAME"
        ]
        .astype(str)
        .str.strip()
    )

    df[
        "SDATE"
    ] = pd.to_datetime(
        df[
            "SDATE"
        ],
        format="mixed",
        errors="coerce",
    )

    for column in [
        "UL_PRB_UTILIZATION_FORECAST",
        "DL_PRB_UTILIZATION_FORECAST",
        "ACTIVE_USERS_FORECAST",
    ]:

        df[
            column
        ] = pd.to_numeric(
            df[
                column
            ],
            errors="coerce",
        )

    df = (
        df.dropna(
            subset=[
                "CELL_NAME",
                "SDATE",
            ]
        )
    )

    if df.empty:

        raise ValueError(
            "Forecast dataset is empty."
        )

    recommendations = []

    for (
        cell_name,
        cell_df,
    ) in df.groupby(
        "CELL_NAME",
        sort=True,
    ):

        cell_df = (
            cell_df
            .sort_values(
                "SDATE"
            )
            .reset_index(
                drop=True
            )
        )

        n_steps = int(
            len(
                cell_df
            )
        )

        dl_vals = (
            cell_df[
                "DL_PRB_UTILIZATION_FORECAST"
            ]
            .to_numpy(
                dtype=float
            )
        )

        ul_vals = (
            cell_df[
                "UL_PRB_UTILIZATION_FORECAST"
            ]
            .to_numpy(
                dtype=float
            )
        )

        usr_vals = (
            cell_df[
                "ACTIVE_USERS_FORECAST"
            ]
            .to_numpy(
                dtype=float
            )
        )

        # ====================================================
        # 1. ENERGY SAVING
        #
        # Exact legacy behavior:
        # Find a consecutive low-load sequence whose length
        # is between ES min and max steps.
        # ====================================================

        es_mask = (
            (
                dl_vals
                <
                rules[
                    "es_prb_threshold"
                ]
            )
            &
            (
                ul_vals
                <
                rules[
                    "es_prb_threshold"
                ]
            )
            &
            (
                usr_vals
                <
                rules[
                    "es_max_active_users"
                ]
            )
        )

        consecutive_count = 0
        es_triggered = False
        start_idx = 0

        for i, value in enumerate(
            es_mask
        ):

            if bool(value):

                if consecutive_count == 0:
                    start_idx = i

                consecutive_count += 1

            else:

                if (
                    rules[
                        "es_min_steps"
                    ]
                    <= consecutive_count
                    <= rules[
                        "es_max_steps"
                    ]
                ):

                    es_triggered = True

                    end_idx = (
                        i - 1
                    )

                    t_start = (
                        _time_value(
                            cell_df[
                                "SDATE"
                            ].iloc[
                                start_idx
                            ]
                        )
                    )

                    t_end = (
                        _time_value_end(
                            cell_df[
                                "SDATE"
                            ].iloc[
                                end_idx
                            ]
                        )
                    )

                    dl_window = (
                        dl_vals[
                            start_idx:
                            end_idx + 1
                        ]
                    )

                    ul_window = (
                        ul_vals[
                            start_idx:
                            end_idx + 1
                        ]
                    )

                    usr_window = (
                        usr_vals[
                            start_idx:
                            end_idx + 1
                        ]
                    )

                    recommendations.append(
                        {
                            "cell_name": (
                                cell_name
                            ),
                            "recommendation": (
                                "ES"
                            ),
                            "module_label": (
                                "Energy Saving (ES)"
                            ),
                            "triggering_condition": (
                                f"DL/UL PRB < "
                                f"{rules['es_prb_threshold']:g}% "
                                f"& Users < "
                                f"{rules['es_max_active_users']:g} "
                                f"for {consecutive_count} steps"
                            ),
                            "time_window": (
                                f"{t_start} - {t_end} "
                                f"({consecutive_count * 15} Mins)"
                            ),
                            "recommended_action": (
                                "Enable Deep Cell Sleep Mode"
                            ),
                            "evidence": (
                                f"Max DL "
                                f"{np.nanmax(dl_window):.1f}% · "
                                f"Max UL "
                                f"{np.nanmax(ul_window):.1f}% · "
                                f"Max Users "
                                f"{np.nanmax(usr_window):.1f}"
                            ),
                        }
                    )

                    break

                consecutive_count = 0

        if (
            not es_triggered
            and rules[
                "es_min_steps"
            ]
            <= consecutive_count
            <= rules[
                "es_max_steps"
            ]
        ):

            end_idx = (
                n_steps - 1
            )

            t_start = (
                _time_value(
                    cell_df[
                        "SDATE"
                    ].iloc[
                        start_idx
                    ]
                )
            )

            t_end = (
                _time_value(
                    cell_df[
                        "SDATE"
                    ].iloc[
                        end_idx
                    ]
                )
            )

            dl_window = (
                dl_vals[
                    start_idx:
                    end_idx + 1
                ]
            )

            ul_window = (
                ul_vals[
                    start_idx:
                    end_idx + 1
                ]
            )

            usr_window = (
                usr_vals[
                    start_idx:
                    end_idx + 1
                ]
            )

            recommendations.append(
                {
                    "cell_name": (
                        cell_name
                    ),
                    "recommendation": (
                        "ES"
                    ),
                    "module_label": (
                        "Energy Saving (ES)"
                    ),
                    "triggering_condition": (
                        f"DL/UL PRB < "
                        f"{rules['es_prb_threshold']:g}% "
                        f"& Users < "
                        f"{rules['es_max_active_users']:g} "
                        f"for {consecutive_count} steps"
                    ),
                    "time_window": (
                        f"{t_start} - {t_end} "
                        f"({consecutive_count * 15} Mins)"
                    ),
                    "recommended_action": (
                        "Enable Deep Cell Sleep Mode"
                    ),
                    "evidence": (
                        f"Max DL "
                        f"{np.nanmax(dl_window):.1f}% · "
                        f"Max UL "
                        f"{np.nanmax(ul_window):.1f}% · "
                        f"Max Users "
                        f"{np.nanmax(usr_window):.1f}"
                    ),
                }
            )

        # ====================================================
        # Shared final-window high-load evaluator
        # ====================================================

        def last_window_high_load(
            threshold,
            duration_steps,
        ):

            duration_steps = int(
                duration_steps
            )

            if (
                duration_steps < 1
                or n_steps
                < duration_steps
            ):

                return (
                    False,
                    None,
                    None,
                    None,
                    None,
                )

            dl_window = (
                dl_vals[
                    -duration_steps:
                ]
            )

            ul_window = (
                ul_vals[
                    -duration_steps:
                ]
            )

            high_mask = (
                (
                    dl_window
                    >
                    threshold
                )
                |
                (
                    ul_window
                    >
                    threshold
                )
            )

            if not bool(
                np.all(
                    high_mask
                )
            ):

                return (
                    False,
                    None,
                    None,
                    dl_window,
                    ul_window,
                )

            start_time = (
                _time_value(
                    cell_df[
                        "SDATE"
                    ].iloc[
                        -duration_steps
                    ]
                )
            )

            end_time = (
                _time_value_end(
                    cell_df[
                        "SDATE"
                    ].iloc[
                        -1
                    ]
                )
            )

            return (
                True,
                start_time,
                end_time,
                dl_window,
                ul_window,
            )

        # ====================================================
        # 2. CAPACITY EXPANSION
        #
        # Legacy rule:
        # - final N steps high PRB
        # - latest user count > previous * 1.10
        # CAP and MLB are evaluated independently.
        # ====================================================

        (
            cap_triggered,
            cap_start,
            cap_end,
            cap_dl_window,
            cap_ul_window,
        ) = (
            last_window_high_load(
                rules[
                    "cap_prb_threshold"
                ],
                rules[
                    "cap_steps"
                ],
            )
        )

        if cap_triggered:

            recommendations.append(
                {
                    "cell_name": (
                        cell_name
                    ),
                    "recommendation": (
                        "CAP"
                    ),
                    "module_label": (
                        "Capacity Expansion (CAP)"
                    ),
                    "triggering_condition": (
                        f"PRB > "
                        f"{rules['cap_prb_threshold']:g}% "
                        f"in last "
                        f"{rules['cap_steps']} step(s)"
                    ),
                    "time_window": (
                        f"{cap_start} - {cap_end} "
                        f"({int(rules['cap_steps']) * 15} Mins)"
                    ),
                    "recommended_action": (
                        "Flag Node for Carrier / Capacity Expansion Review"
                    ),
                    "evidence": (
                        f"Max DL "
                        f"{np.nanmax(cap_dl_window):.1f}% · "
                        f"Max UL "
                        f"{np.nanmax(cap_ul_window):.1f}%"
                    ),
                }
            )


        # =================================================
        # 3. MOBILITY LOAD BALANCING
        #
        # Independent module. CAP does not suppress MLB.
        # =================================================

        (
            mlb_triggered,
            mlb_start,
            mlb_end,
            mlb_dl_window,
            mlb_ul_window,
        ) = (
            last_window_high_load(
                rules[
                    "mlb_prb_threshold"
                ],
                rules[
                    "mlb_steps"
                ],
            )
        )

        if mlb_triggered:

            recommendations.append(
                {
                    "cell_name": (
                        cell_name
                    ),
                    "recommendation": (
                        "MLB"
                    ),
                    "module_label": (
                        "Mobility Load Balancing (MLB)"
                    ),
                    "triggering_condition": (
                        f"PRB > "
                        f"{rules['mlb_prb_threshold']:g}% "
                        f"in last "
                        f"{rules['mlb_steps']} step(s)"
                    ),
                    "time_window": (
                        f"{mlb_start} - {mlb_end} "
                        f"({int(rules['mlb_steps']) * 15} Mins)"
                    ),
                    "recommended_action": (
                        "Trigger MLB Candidate Review / "
                        "Validate Neighbor Capacity"
                    ),
                    "evidence": (
                        f"Max DL "
                        f"{np.nanmax(mlb_dl_window):.1f}% · "
                        f"Max UL "
                        f"{np.nanmax(mlb_ul_window):.1f}%"
                    ),
                }
            )
    es_count = sum(
        item[
            "recommendation"
        ] == "ES"
        for item in recommendations
    )

    mlb_count = sum(
        item[
            "recommendation"
        ] == "MLB"
        for item in recommendations
    )

    cap_count = sum(
        item[
            "recommendation"
        ] == "CAP"
        for item in recommendations
    )

    total_cells = int(
        df[
            "CELL_NAME"
        ].nunique()
    )

    flagged_cells = {
        item[
            "cell_name"
        ]
        for item in recommendations
    }

    recommendation_counts = {}

    for item in recommendations:

        cell_name = (
            item[
                "cell_name"
            ]
        )

        recommendation_counts[
            cell_name
        ] = (
            recommendation_counts.get(
                cell_name,
                0,
            )
            + 1
        )

    overlapping_cells = sum(
        count > 1
        for count in (
            recommendation_counts.values()
        )
    )

    per_cell_steps = (
        df.groupby(
            "CELL_NAME"
        )
        .size()
    )

    horizon_steps = (
        int(
            per_cell_steps.median()
        )
        if not per_cell_steps.empty
        else 0
    )

    return {
        "status": "completed",
        "run_id": run_id,
        "engine": (
            "independent-module-rule-engine-v5"
        ),
        "total_cells": (
            total_cells
        ),
        "forecast_rows": int(
            len(df)
        ),
        "horizon_steps": (
            horizon_steps
        ),
        "forecast_start": (
            df[
                "SDATE"
            ]
            .min()
            .isoformat()
        ),
        "forecast_end": (
            df[
                "SDATE"
            ]
            .max()
            .isoformat()
        ),
        "rules": (
            rules
        ),
        "summary": {
            "es": int(
                es_count
            ),
            "mlb": int(
                mlb_count
            ),
            "cap": int(
                cap_count
            ),
            "recommendations": int(
                len(
                    recommendations
                )
            ),
            "flagged_cells": int(
                len(
                    flagged_cells
                )
            ),
            "no_action": int(
                total_cells
                - len(
                    flagged_cells
                )
            ),
            "overlapping_cells": int(
                overlapping_cells
            ),
        },
        "recommendations": (
            recommendations
        ),
    }
