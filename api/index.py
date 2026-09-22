from pathlib import Path
import gc
import os
import sys
import time

import joblib

from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
)

from fastapi.middleware.cors import (
    CORSMiddleware,
)

from pydantic import (
    BaseModel,
    Field,
)


PROJECT_ROOT = Path(
    __file__
).resolve().parents[1]

if str(
    PROJECT_ROOT
) not in sys.path:
    sys.path.insert(
        0,
        str(
            PROJECT_ROOT
        ),
    )


from ml_engine.forecast_engine import (
    ENGINE_VERSION,
    ForecastMetadata,
    CLUSTERING_MODELS_DIR,
    FORECASTING_MODELS_DIR,
)

from backend.app.services.vercel_generation_service import (
    generate_dataset_from_blob,
)

from backend.app.services.vercel_forecast_service import (
    forecast_generated_dataset,
)

from backend.app.services.vercel_validation_service import (
    validate_forecast_run,
)

from backend.app.services.vercel_son_service import (
    evaluate_son_blob_run,
)

from backend.app.services.vercel_run_catalog_service import (
    list_forecast_runs,
)

from api.production_routes import (
    router as production_router,
)


app = FastAPI(
    title=(
        "Behavior-Aware Predictive SON "
        "- Vercel Backend"
    ),
    version="0.11.0",
)


# =========================================================
# CORS
# =========================================================

DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

configured_cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "",
    ).split(",")
    if origin.strip()
]

CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys(
        DEFAULT_CORS_ORIGINS
        + configured_cors_origins
    )
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=(
        CORS_ALLOWED_ORIGINS
    ),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Disposition",
    ],
)


app.include_router(
    production_router
)


# =========================================================
# REQUEST MODELS
# =========================================================

class SonRulesRequest(
    BaseModel
):
    es_prb_threshold: float = Field(
        30.0,
        ge=10,
        le=50,
    )

    es_max_active_users: float = Field(
        10.0,
        ge=1,
        le=30,
    )

    es_min_steps: int = Field(
        3,
        ge=1,
    )

    es_max_steps: int = Field(
        6,
        ge=1,
    )

    mlb_prb_threshold: float = Field(
        80.0,
        ge=60,
        le=95,
    )

    mlb_steps: int = Field(
        2,
        ge=1,
    )

    cap_prb_threshold: float = Field(
        80.0,
        ge=60,
        le=95,
    )

    cap_steps: int = Field(
        2,
        ge=1,
    )


class SonEvaluateRequest(
    BaseModel
):
    run_id: str = Field(
        ...,
        min_length=5,
    )

    rules: SonRulesRequest


class ValidationBlobRequest(
    BaseModel
):
    run_id: str = Field(
        ...,
        min_length=5,
        max_length=64,
    )

    pathname: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )

    filename: str = Field(
        ...,
        min_length=1,
        max_length=255,
    )


# =========================================================
# BASIC STATUS
# =========================================================

@app.get("/api")
def root():
    return {
        "application": (
            "Behavior_Aware_Predictive_SON"
        ),
        "deployment": (
            "vercel-backend"
        ),
        "version": "0.11.0",
        "status": "running",
        "storage": (
            "vercel-private-blob"
        ),
    }


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "engine": ENGINE_VERSION,
        "project_root": str(
            PROJECT_ROOT
        ),
        "storage": (
            "vercel-private-blob"
        ),
    }


# =========================================================
# ARTIFACT STATUS
# =========================================================

@app.get("/api/artifacts")
def artifacts():
    metadata = (
        ForecastMetadata()
    )

    clustering_models = sorted(
        path.name
        for path
        in CLUSTERING_MODELS_DIR.glob(
            "*.joblib"
        )
    )

    forecasting_models = sorted(
        path.name
        for path
        in FORECASTING_MODELS_DIR.glob(
            "*.joblib"
        )
    )

    return {
        "status": "ready",

        "engine": (
            ENGINE_VERSION
        ),

        "schema_loaded": (
            metadata.schema
            is not None
        ),

        "mapping_rows": len(
            metadata.mapping_df
        ),

        "clustering_models": {
            "count": len(
                clustering_models
            ),
            "files": (
                clustering_models
            ),
        },

        "forecasting_models": {
            "count": len(
                forecasting_models
            ),
            "files": (
                forecasting_models
            ),
        },
    }


@app.get("/api/model-load-test")
def model_load_test():
    results = []

    for path in sorted(
        FORECASTING_MODELS_DIR.glob(
            "*.joblib"
        )
    ):
        started = (
            time.perf_counter()
        )

        artifact = joblib.load(
            path
        )

        model = (
            artifact.get(
                "model"
            )
            if isinstance(
                artifact,
                dict,
            )
            else artifact
        )

        results.append(
            {
                "file": (
                    path.name
                ),

                "file_mb": round(
                    path.stat().st_size
                    / 1024
                    / 1024,
                    2,
                ),

                "model_type": (
                    type(
                        model
                    ).__name__
                ),

                "n_estimators": getattr(
                    model,
                    "n_estimators",
                    None,
                ),

                "n_features": getattr(
                    model,
                    "n_features_in_",
                    None,
                ),

                "load_seconds": round(
                    time.perf_counter()
                    - started,
                    3,
                ),
            }
        )

        del model
        del artifact

        gc.collect()

    return {
        "status": "ready",

        "models_loaded": len(
            results
        ),

        "models": (
            results
        ),
    }


# =========================================================
# GENERATION POC
# =========================================================

@app.get("/api/generate-poc")
async def generate_poc(
    cells: int = Query(
        100,
        ge=1,
        le=2000,
    ),
    seed: int | None = Query(
        None,
        ge=0,
        le=2_147_483_647,
    ),
):
    try:
        return (
            await generate_dataset_from_blob(
                cell_count=cells,
                seed=seed,
            )
        )

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


# =========================================================
# FORECAST POC
# =========================================================

@app.get(
    "/api/forecast-generation-poc"
)
async def forecast_generation_poc(
    generation_id: str = Query(
        ...,
        min_length=5,
    ),
    horizon_steps: int = Query(
        96,
    ),
):
    try:
        return (
            await forecast_generated_dataset(
                generation_id=(
                    generation_id
                ),
                horizon_steps=(
                    horizon_steps
                ),
            )
        )

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


# =========================================================
# FORECAST RUN CATALOG
# =========================================================

async def _forecast_run_catalog():
    try:
        return (
            await list_forecast_runs()
        )

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


@app.get(
    "/api/validation/runs"
)
async def validation_runs():
    return (
        await _forecast_run_catalog()
    )


@app.get(
    "/api/son/runs"
)
async def son_runs():
    return (
        await _forecast_run_catalog()
    )


# =========================================================
# VALIDATION
# =========================================================

@app.post(
    "/api/validate"
)
async def validate_compatibility(
    run_id: str = Form(
        ...
    ),
    file: UploadFile | None = File(
        None
    ),
):
    """
    Frontend-compatible validation endpoint.

    Generated forecast runs automatically use
    the generation ground_truth.csv stored in
    Vercel Private Blob.

    Custom uploaded actual/ground-truth files
    will be migrated separately through the
    direct-to-Blob upload flow.
    """

    if file is not None:
        raise HTTPException(
            status_code=400,
            detail=(
                "Custom actual CSV upload is "
                "not enabled in the Vercel "
                "compatibility API yet. "
                "Generated forecast runs use "
                "their stored ground truth "
                "automatically."
            ),
        )

    try:
        return (
            await validate_forecast_run(
                run_id=run_id,
            )
        )

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


@app.post(
    "/api/validate-blob"
)
async def validate_blob_compatibility(
    payload: ValidationBlobRequest,
):
    """
    Reference-only validation endpoint.

    The browser uploads the actual CSV directly
    to Private Vercel Blob, then sends only the
    Blob pathname and original filename here.
    """

    try:
        return (
            await validate_forecast_run(
                run_id=payload.run_id,
                actual_pathname=(
                    payload.pathname
                ),
                actual_filename=(
                    payload.filename
                ),
            )
        )

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


# Keep the old POC endpoint until migration
# regression testing is complete.
@app.get(
    "/api/validate-generation"
)
async def validate_generation(
    run_id: str = Query(
        ...,
        min_length=5,
    ),
):
    try:
        return (
            await validate_forecast_run(
                run_id=run_id,
            )
        )

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


# =========================================================
# SON
# =========================================================

@app.post(
    "/api/son/evaluate"
)
async def son_evaluate_compatibility(
    payload: SonEvaluateRequest,
):
    try:
        rules = (
            payload.rules.model_dump()
        )

        if (
            rules[
                "es_max_steps"
            ]
            < rules[
                "es_min_steps"
            ]
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    "es_max_steps must be "
                    "greater than or equal "
                    "to es_min_steps."
                ),
            )

        return (
            await evaluate_son_blob_run(
                run_id=(
                    payload.run_id
                ),
                rules=rules,
            )
        )

    except HTTPException:
        raise

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc


# Keep the old POC endpoint until migration
# regression testing is complete.
@app.get(
    "/api/son-evaluate"
)
async def son_evaluate_poc(
    run_id: str = Query(
        ...,
        min_length=5,
    ),
    es_prb_threshold: float = Query(
        30.0,
        ge=10,
        le=50,
    ),
    es_max_active_users: float = Query(
        10.0,
        ge=1,
        le=30,
    ),
    es_min_steps: int = Query(
        3,
        ge=1,
    ),
    es_max_steps: int = Query(
        6,
        ge=1,
    ),
    mlb_prb_threshold: float = Query(
        80.0,
        ge=60,
        le=95,
    ),
    mlb_steps: int = Query(
        2,
        ge=1,
    ),
    cap_prb_threshold: float = Query(
        80.0,
        ge=60,
        le=95,
    ),
    cap_steps: int = Query(
        2,
        ge=1,
    ),
):
    try:
        rules = {
            "es_prb_threshold": (
                es_prb_threshold
            ),

            "es_max_active_users": (
                es_max_active_users
            ),

            "es_min_steps": (
                es_min_steps
            ),

            "es_max_steps": (
                es_max_steps
            ),

            "mlb_prb_threshold": (
                mlb_prb_threshold
            ),

            "mlb_steps": (
                mlb_steps
            ),

            "cap_prb_threshold": (
                cap_prb_threshold
            ),

            "cap_steps": (
                cap_steps
            ),
        }

        return (
            await evaluate_son_blob_run(
                run_id=run_id,
                rules=rules,
            )
        )

    except ValueError as exc:
        gc.collect()

        raise HTTPException(
            status_code=400,
            detail=str(
                exc
            ),
        ) from exc

    except FileNotFoundError as exc:
        gc.collect()

        raise HTTPException(
            status_code=404,
            detail=str(
                exc
            ),
        ) from exc

    except Exception as exc:
        gc.collect()

        raise HTTPException(
            status_code=500,
            detail=(
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        ) from exc

from api.upload_routes import router as upload_router
app.include_router(upload_router)
