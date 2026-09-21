from __future__ import annotations

from pathlib import Path
import gzip
import shutil
import tempfile
import threading
import time
from typing import Callable

from fastapi.concurrency import run_in_threadpool
from vercel.blob import AsyncBlobClient

from backend.app.services import (
    dataset_generator_service as generator_service,
)


SOURCE_BLOB_PATH = (
    "source/network_traffic.csv.gz"
)

GENERATIONS_BLOB_PREFIX = (
    "generations"
)

GENERATED_FILES = [
    "forecast_input.csv",
    "ground_truth.csv",
    "model_ready_forecast_input.csv",
    "manifest.json",
]

GENERATION_LOCK = threading.Lock()

ProgressCallback = Callable[[dict], None]


def _emit_progress(
    callback: ProgressCallback | None,
    *,
    request_started: float,
    cell_count: int,
    stage: str,
    stage_label: str,
    progress_percent: float,
    generation_id: str = "",
):
    if callback is None:
        return

    payload = {
        "status": "running",
        "generation_id": generation_id,
        "stage": stage,
        "stage_label": stage_label,
        "cell_count": int(cell_count),
        "progress_percent": round(
            max(
                0.0,
                min(
                    100.0,
                    float(progress_percent),
                ),
            ),
            2,
        ),
        "elapsed_seconds": round(
            time.perf_counter()
            - request_started,
            2,
        ),
    }

    try:
        callback(payload)
    except Exception:
        # Progress reporting must never break generation.
        pass


def _decompress_source(
    gzip_path: Path,
    csv_path: Path,
):
    csv_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with gzip.open(
        gzip_path,
        "rb",
    ) as source:
        with open(
            csv_path,
            "wb",
        ) as target:
            shutil.copyfileobj(
                source,
                target,
                length=8 * 1024 * 1024,
            )


def _run_existing_generator(
    source_csv: Path,
    output_root: Path,
    cell_count: int,
    seed: int | None,
    progress_callback,
):
    output_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    old_source_file = (
        generator_service.SOURCE_FILE
    )

    old_output_root = (
        generator_service.OUTPUT_ROOT
    )

    try:
        with GENERATION_LOCK:
            generator_service.SOURCE_FILE = (
                source_csv
            )

            generator_service.OUTPUT_ROOT = (
                output_root
            )

            return (
                generator_service.generate_dataset(
                    cell_count=int(cell_count),
                    seed=seed,
                    progress_callback=(
                        progress_callback
                    ),
                )
            )

    finally:
        generator_service.SOURCE_FILE = (
            old_source_file
        )

        generator_service.OUTPUT_ROOT = (
            old_output_root
        )


async def generate_dataset_from_blob(
    cell_count: int,
    seed: int | None = None,
    progress_callback: ProgressCallback | None = None,
):
    request_started = time.perf_counter()

    cell_count = int(cell_count)

    work_dir = Path(
        tempfile.mkdtemp(
            prefix="baps-generation-",
            dir=tempfile.gettempdir(),
        )
    )

    gzip_path = (
        work_dir
        / "network_traffic.csv.gz"
    )

    source_csv = (
        work_dir
        / "data"
        / "raw"
        / "network_traffic.csv"
    )

    output_root = (
        work_dir
        / "data"
        / "outputs"
        / "generated"
    )

    try:
        _emit_progress(
            progress_callback,
            request_started=request_started,
            cell_count=cell_count,
            stage="source_download",
            stage_label="Downloading Source Dataset",
            progress_percent=1.0,
        )

        download_started = (
            time.perf_counter()
        )

        async with AsyncBlobClient() as client:
            await client.download_file(
                SOURCE_BLOB_PATH,
                str(gzip_path),
                access="private",
                timeout=120,
            )

        source_download_seconds = (
            time.perf_counter()
            - download_started
        )

        compressed_bytes = (
            gzip_path.stat().st_size
        )

        _emit_progress(
            progress_callback,
            request_started=request_started,
            cell_count=cell_count,
            stage="source_download",
            stage_label="Source Dataset Downloaded",
            progress_percent=5.0,
        )

        _emit_progress(
            progress_callback,
            request_started=request_started,
            cell_count=cell_count,
            stage="source_decompression",
            stage_label="Decompressing Source Dataset",
            progress_percent=6.0,
        )

        decompress_started = (
            time.perf_counter()
        )

        await run_in_threadpool(
            _decompress_source,
            gzip_path,
            source_csv,
        )

        decompress_seconds = (
            time.perf_counter()
            - decompress_started
        )

        source_bytes = (
            source_csv.stat().st_size
        )

        # Compressed copy is no longer needed.
        gzip_path.unlink(
            missing_ok=True
        )

        _emit_progress(
            progress_callback,
            request_started=request_started,
            cell_count=cell_count,
            stage="source_decompression",
            stage_label="Source Dataset Ready",
            progress_percent=10.0,
        )

        generation_started = (
            time.perf_counter()
        )

        def generator_progress(
            percent: float,
            label: str,
        ):
            # The existing generator already reports a real 0-100
            # progress value. Reserve 0-10% for source preparation
            # and 90-100% for Blob artifact upload/finalization.
            mapped_percent = (
                10.0
                + (
                    max(
                        0.0,
                        min(
                            100.0,
                            float(percent),
                        ),
                    )
                    * 0.80
                )
            )

            _emit_progress(
                progress_callback,
                request_started=(
                    request_started
                ),
                cell_count=cell_count,
                stage="dataset_generation",
                stage_label=str(label),
                progress_percent=(
                    mapped_percent
                ),
            )

        result = await run_in_threadpool(
            _run_existing_generator,
            source_csv,
            output_root,
            cell_count,
            seed,
            generator_progress,
        )

        generation_seconds = (
            time.perf_counter()
            - generation_started
        )

        generation_id = str(
            result["generation_id"]
        )

        generation_dir = (
            output_root
            / generation_id
        )

        _emit_progress(
            progress_callback,
            request_started=request_started,
            cell_count=cell_count,
            stage="artifact_upload",
            stage_label="Preparing Generated Artifacts",
            progress_percent=90.0,
            generation_id=generation_id,
        )

        uploaded = {}

        local_artifacts = []
        total_upload_bytes = 0

        for filename in GENERATED_FILES:
            local_path = (
                generation_dir
                / filename
            )

            if not local_path.exists():
                raise FileNotFoundError(
                    "Generated artifact "
                    f"not found: {filename}"
                )

            file_size = (
                local_path.stat().st_size
            )

            local_artifacts.append(
                (
                    filename,
                    local_path,
                    file_size,
                )
            )

            total_upload_bytes += file_size

        total_upload_bytes = max(
            total_upload_bytes,
            1,
        )

        uploaded_bytes = 0

        upload_started = (
            time.perf_counter()
        )

        async with AsyncBlobClient() as client:
            for (
                filename,
                local_path,
                file_size,
            ) in local_artifacts:
                _emit_progress(
                    progress_callback,
                    request_started=(
                        request_started
                    ),
                    cell_count=cell_count,
                    stage="artifact_upload",
                    stage_label=(
                        "Uploading Generated Artifacts"
                    ),
                    progress_percent=(
                        90.0
                        + 9.0
                        * uploaded_bytes
                        / total_upload_bytes
                    ),
                    generation_id=(
                        generation_id
                    ),
                )

                blob_path = (
                    f"{GENERATIONS_BLOB_PREFIX}/"
                    f"{generation_id}/"
                    f"{filename}"
                )

                blob = await client.upload_file(
                    str(local_path),
                    blob_path,
                    access="private",
                    add_random_suffix=False,
                    overwrite=False,
                    multipart=(
                        file_size
                        >= 5 * 1024 * 1024
                    ),
                )

                uploaded[
                    filename
                ] = {
                    "pathname": (
                        blob.pathname
                    ),
                    "size": file_size,
                }

                uploaded_bytes += file_size

                _emit_progress(
                    progress_callback,
                    request_started=(
                        request_started
                    ),
                    cell_count=cell_count,
                    stage="artifact_upload",
                    stage_label=(
                        "Uploading Generated Artifacts"
                    ),
                    progress_percent=(
                        90.0
                        + 9.0
                        * uploaded_bytes
                        / total_upload_bytes
                    ),
                    generation_id=(
                        generation_id
                    ),
                )

        upload_seconds = (
            time.perf_counter()
            - upload_started
        )

        _emit_progress(
            progress_callback,
            request_started=request_started,
            cell_count=cell_count,
            stage="completed",
            stage_label="Dataset Generated",
            progress_percent=100.0,
            generation_id=generation_id,
        )

        return {
            "status": "completed",
            "generation_id": (
                generation_id
            ),
            "cell_count": int(
                result["cell_count"]
            ),
            "seed": int(
                result["seed"]
            ),
            "eligible_cell_count": int(
                result[
                    "eligible_cell_count"
                ]
            ),
            "forecast_input_rows": int(
                result[
                    "forecast_input_rows"
                ]
            ),
            "ground_truth_rows": int(
                result[
                    "ground_truth_rows"
                ]
            ),
            "model_ready_rows": int(
                result[
                    "model_ready_rows"
                ]
            ),
            "source": {
                "blob_pathname": (
                    SOURCE_BLOB_PATH
                ),
                "compressed_bytes": (
                    compressed_bytes
                ),
                "uncompressed_bytes": (
                    source_bytes
                ),
            },
            "artifacts": uploaded,
            "runtime_seconds": {
                "source_download": round(
                    source_download_seconds,
                    4,
                ),
                "decompress": round(
                    decompress_seconds,
                    4,
                ),
                "generation": round(
                    generation_seconds,
                    4,
                ),
                "blob_upload": round(
                    upload_seconds,
                    4,
                ),
                "total": round(
                    time.perf_counter()
                    - request_started,
                    4,
                ),
            },
        }

    finally:
        shutil.rmtree(
            work_dir,
            ignore_errors=True,
        )
