from __future__ import annotations

import json
from datetime import (
    datetime,
    timedelta,
    timezone,
)
from typing import Any

from vercel.blob import (
    AsyncBlobClient,
    list_objects_async,
)


FORECAST_RUNS_BLOB_PREFIX = (
    "forecast-runs"
)

GENERATIONS_BLOB_PREFIX = (
    "generations"
)


def _field(
    value: Any,
    name: str,
    default=None,
):
    if isinstance(
        value,
        dict,
    ):
        return value.get(
            name,
            default,
        )

    return getattr(
        value,
        name,
        default,
    )


def _parse_run_time(
    run_id: str,
):
    try:
        parsed = datetime.strptime(
            run_id,
            "FR-%Y%m%dT%H%M%S%fZ",
        )

        return parsed.replace(
            tzinfo=timezone.utc
        ).isoformat()

    except Exception:
        return None


def _parse_timestamp(
    value,
):
    if value is None:
        return None

    text = str(
        value
    ).strip()

    if not text:
        return None

    try:
        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        )

    except Exception:
        return None


def _format_timestamp(
    value,
):
    parsed = _parse_timestamp(
        value
    )

    if parsed is None:
        return (
            str(value)
            if value is not None
            else None
        )

    return parsed.isoformat(
        timespec="seconds"
    )


async def _list_forecast_metadata_paths():
    prefix = (
        f"{FORECAST_RUNS_BLOB_PREFIX}/"
    )

    cursor = None
    pathnames: list[str] = []

    while True:
        result = (
            await list_objects_async(
                prefix=prefix,
                limit=1000,
                cursor=cursor,
            )
        )

        blobs = (
            _field(
                result,
                "blobs",
            )
            or _field(
                result,
                "objects",
            )
            or _field(
                result,
                "items",
            )
            or []
        )

        for blob in blobs:
            pathname = _field(
                blob,
                "pathname",
            )

            if (
                pathname
                and pathname.endswith(
                    "/run_metadata.json"
                )
            ):
                pathnames.append(
                    str(
                        pathname
                    )
                )

        next_cursor = _field(
            result,
            "cursor",
        )

        has_more = _field(
            result,
            "has_more",
            None,
        )

        if has_more is None:
            has_more = _field(
                result,
                "hasMore",
                None,
            )

        if not next_cursor:
            break

        if has_more is False:
            break

        if next_cursor == cursor:
            break

        cursor = next_cursor

    return sorted(
        set(
            pathnames
        ),
        reverse=True,
    )


async def _read_json_blob(
    client: AsyncBlobClient,
    pathname: str,
):
    result = await client.get(
        pathname,
        access="private",
        timeout=60,
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
        text = content.decode(
            "utf-8"
        )

    else:
        text = str(
            content
        )

    return json.loads(
        text
    )


async def _load_generation_manifest(
    client: AsyncBlobClient,
    generation_id: str,
):
    pathname = (
        f"{GENERATIONS_BLOB_PREFIX}/"
        f"{generation_id}/"
        f"manifest.json"
    )

    return await _read_json_blob(
        client,
        pathname,
    )


def _metadata_date_range(
    metadata: dict,
    generation_manifest: dict | None,
):
    forecast_range = (
        metadata.get(
            "forecast_date_range"
        )
        or {}
    )

    forecast_start = (
        metadata.get(
            "forecast_start"
        )
        or forecast_range.get(
            "start"
        )
    )

    forecast_end = (
        metadata.get(
            "forecast_end"
        )
        or forecast_range.get(
            "end"
        )
    )

    if (
        generation_manifest
        and not forecast_start
    ):
        forecast_start = (
            generation_manifest.get(
                "ground_truth_start"
            )
        )

    if (
        generation_manifest
        and not forecast_end
    ):
        horizon_steps = (
            metadata.get(
                "horizon_steps"
            )
        )

        resolution_minutes = int(
            generation_manifest.get(
                "resolution_minutes",
                15,
            )
        )

        parsed_start = (
            _parse_timestamp(
                forecast_start
            )
        )

        if (
            parsed_start is not None
            and horizon_steps
        ):
            forecast_end_dt = (
                parsed_start
                + timedelta(
                    minutes=(
                        (
                            int(
                                horizon_steps
                            )
                            - 1
                        )
                        * resolution_minutes
                    )
                )
            )

            forecast_end = (
                forecast_end_dt
                .isoformat(
                    timespec="seconds"
                )
            )

        else:
            forecast_end = (
                generation_manifest.get(
                    "ground_truth_end"
                )
            )

    return (
        _format_timestamp(
            forecast_start
        ),
        _format_timestamp(
            forecast_end
        ),
    )


def _catalog_item(
    metadata: dict,
    metadata_pathname: str,
    generation_manifest: (
        dict | None
    ),
):
    parts = (
        metadata_pathname
        .split("/")
    )

    pathname_run_id = (
        parts[1]
        if len(parts) >= 3
        else None
    )

    run_id = (
        metadata.get(
            "run_id"
        )
        or pathname_run_id
    )

    if not run_id:
        raise ValueError(
            "Forecast run metadata "
            "does not contain run_id."
        )

    generation_id = (
        metadata.get(
            "generation_id"
        )
    )

    source = (
        metadata.get(
            "source"
        )
    )

    generated = bool(
        generation_id
    ) or (
        str(
            source
        ).lower()
        in {
            "generated",
            "generation",
            "vercel-generated",
        }
    )

    if generated:
        source_type = "generated"

        source_label = (
            "Generated Dataset"
        )

    else:
        source_type = (
            str(
                source
            )
            if source
            else "uploaded"
        )

        source_label = (
            "Uploaded Dataset"
        )

    total_cells = (
        metadata.get(
            "total_cells"
        )
    )

    if total_cells is None:
        total_cells = (
            metadata.get(
                "successful_cells"
            )
        )

    forecast_rows = (
        metadata.get(
            "forecast_rows"
        )
    )

    horizon_steps = (
        metadata.get(
            "horizon_steps"
        )
    )

    (
        forecast_start,
        forecast_end,
    ) = _metadata_date_range(
        metadata,
        generation_manifest,
    )

    created_at = (
        metadata.get(
            "created_at"
        )
        or _parse_run_time(
            run_id
        )
    )

    ground_truth_available = (
        bool(
            generation_id
        )
    )

    ground_truth_filename = (
        "ground_truth.csv"
        if ground_truth_available
        else None
    )

    return {
        "run_id": run_id,

        "status": metadata.get(
            "status",
            "completed",
        ),

        "engine": metadata.get(
            "engine"
        ),

        "generation_id": (
            generation_id
        ),

        "source_type": (
            source_type
        ),

        "source_label": (
            source_label
        ),

        "ground_truth_available": (
            ground_truth_available
        ),

        "ground_truth_filename": (
            ground_truth_filename
        ),

        "horizon_steps": (
            int(
                horizon_steps
            )
            if horizon_steps
            is not None
            else None
        ),

        "horizon_minutes": (
            metadata.get(
                "horizon_minutes"
            )
        ),

        "total_cells": (
            int(
                total_cells
            )
            if total_cells
            is not None
            else None
        ),

        # Compatibility alias
        # required by SON frontend.
        "cells": (
            int(
                total_cells
            )
            if total_cells
            is not None
            else None
        ),

        "forecast_rows": (
            int(
                forecast_rows
            )
            if forecast_rows
            is not None
            else None
        ),

        "forecast_start": (
            forecast_start
        ),

        "forecast_end": (
            forecast_end
        ),

        "forecast_signature": (
            metadata.get(
                "forecast_signature"
            )
        ),

        "created_at": (
            created_at
        ),

        "metadata_pathname": (
            metadata_pathname
        ),
    }


async def list_forecast_runs():
    metadata_paths = (
        await _list_forecast_metadata_paths()
    )

    runs = []

    generation_cache: dict[
        str,
        dict | None,
    ] = {}

    async with AsyncBlobClient() as client:
        for pathname in metadata_paths:
            try:
                metadata = (
                    await _read_json_blob(
                        client,
                        pathname,
                    )
                )

                generation_id = (
                    metadata.get(
                        "generation_id"
                    )
                )

                generation_manifest = (
                    None
                )

                if generation_id:
                    if (
                        generation_id
                        not in generation_cache
                    ):
                        try:
                            generation_cache[
                                generation_id
                            ] = (
                                await _load_generation_manifest(
                                    client,
                                    generation_id,
                                )
                            )

                        except Exception:
                            generation_cache[
                                generation_id
                            ] = None

                    generation_manifest = (
                        generation_cache[
                            generation_id
                        ]
                    )

                item = _catalog_item(
                    metadata,
                    pathname,
                    generation_manifest,
                )

                if (
                    item.get(
                        "status"
                    )
                    == "completed"
                ):
                    runs.append(
                        item
                    )

            except Exception:
                # A damaged historical
                # artifact must not break
                # the entire run catalog.
                continue

    runs.sort(
        key=lambda item: (
            item.get(
                "run_id"
            )
            or ""
        ),
        reverse=True,
    )

    return {
        "status": "ready",
        "count": len(
            runs
        ),
        "runs": runs,
    }