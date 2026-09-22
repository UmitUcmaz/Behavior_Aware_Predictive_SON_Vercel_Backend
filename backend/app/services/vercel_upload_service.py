"""Private Blob transport adapter for the unchanged raw-input engine."""
from datetime import datetime, timezone
from io import BytesIO
import json
from pathlib import Path
import re
import tempfile
import time

import pandas as pd
from fastapi.concurrency import run_in_threadpool
from vercel.blob import AsyncBlobClient
from ml_engine.forecast_engine import ENGINE_VERSION, ForecastEngine
from backend.app.services.forecast_input_inspection import inspect_forecast_bytes
from backend.app.services.vercel_forecast_service import _download_blob_bytes

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
UPLOAD_PATTERN = re.compile(r'uploads/forecast/[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}/history\.csv')

def validate_upload_reference(pathname, filename):
    if not UPLOAD_PATTERN.fullmatch(pathname):
        raise ValueError('Invalid uploaded CSV reference.')
    if not filename.lower().endswith('.csv') or len(filename) > 255 or re.search(r'[\\/\x00-\x1f]', filename):
        raise ValueError('Invalid CSV filename.')
    return pathname

async def read_uploaded_csv(pathname, filename):
    validate_upload_reference(pathname, filename)
    async with AsyncBlobClient() as client:
        info = await client.head(pathname)
    if info.size <= 0 or info.size > MAX_UPLOAD_BYTES:
        raise ValueError('CSV must be non-empty and no larger than 50 MiB.')
    if info.content_type.split(';', 1)[0].lower() != 'text/csv':
        raise ValueError('Uploaded object must have CSV content type.')
    content = await _download_blob_bytes(pathname)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError('CSV exceeds the 50 MiB upload limit.')
    return content

async def inspect_uploaded_csv(pathname, filename):
    content = await read_uploaded_csv(pathname, filename)
    return await run_in_threadpool(inspect_forecast_bytes, content, filename)

async def forecast_uploaded_csv(pathname, filename, horizon_steps, progress_callback=None):
    started = time.perf_counter()
    content = await read_uploaded_csv(pathname, filename)
    inspection = await run_in_threadpool(inspect_forecast_bytes, content, filename)
    frame = await run_in_threadpool(pd.read_csv, BytesIO(content))
    del content
    engine = await run_in_threadpool(ForecastEngine, inspect_runtime=False)
    run_id = datetime.now(timezone.utc).strftime('FR-%Y%m%dT%H%M%S%fZ')
    def progress(event):
        if progress_callback:
            progress_callback({
                **event, 'status': 'running', 'run_id': run_id,
                'stage_label': {'feature_engineering': 'Preparing Uploaded CSV',
                    'recursive_forecasting': 'Recursive Forecasting', 'finalizing': 'Finalizing Output'}.get(event.get('stage'), 'Running Forecast'),
                'total_steps': horizon_steps, 'total_cells': inspection['total_cells'],
                'expected_rows': inspection['total_cells'] * horizon_steps,
                'failed_cells': event.get('failed_cells', 0),
                'elapsed_seconds': round(time.perf_counter() - started, 2),
                'progress_percent': min(event.get('progress_percent', 0), 99),
            })
    # Keep the exact full-input preprocessing, then reuse the engine's
    # prepared-input API so all three RF models stay resident for this run.
    preprocessing_started = time.perf_counter()
    try:
        progress({'stage': 'feature_engineering', 'current_step': 0,
                  'rows_generated': 0, 'progress_percent': 0.0})
    except Exception:
        pass  # Match the engine: progress observers must not stop inference.
    preprocessing_perf = {}
    prepared, cell_col, time_col, kpis = await run_in_threadpool(
        engine.preprocess_and_extract_features, frame, perf=preprocessing_perf)
    preprocessing_seconds = time.perf_counter() - preprocessing_started

    def prepared_progress(event):
        # The initial feature-engineering event was emitted before preprocessing.
        if event.get('stage') != 'feature_engineering':
            progress(event)

    result = await run_in_threadpool(
        engine.forecast, prepared, horizon_steps,
        progress_callback=prepared_progress,
        prepared_columns=(cell_col, time_col, kpis), resident_models=True)
    del prepared
    result['preprocess_seconds'] = preprocessing_seconds
    result['performance']['preprocess'] = preprocessing_perf
    forecast = result['export_df']
    cell_col, time_col = result['cell_col'], result['time_col']
    # Chart-only history mapping; inference above already used the untouched raw frame.
    mapping = engine.mapping_df
    raw_key = 'RAW_COLUMN_NAME' if 'RAW_COLUMN_NAME' in mapping else mapping.columns[0]
    std_key = 'STANDARDIZED_NAME' if 'STANDARDIZED_NAME' in mapping else mapping.columns[1]
    chart_history = frame.rename(columns={str(row[raw_key]).strip(): str(row[std_key]).strip() for _, row in mapping.iterrows()})
    prefix = f'forecast-runs/{run_id}'
    response = {
        'status': 'completed', 'run_id': run_id, 'engine': ENGINE_VERSION,
        'source_type': 'uploaded', 'generation_id': None, 'input_filename': filename,
        'input_rows': inspection['input_rows'], 'input_date_range': inspection['input_date_range'],
        'horizon_steps': horizon_steps, 'horizon_minutes': horizon_steps * 15,
        **{key: int(result[key]) for key in ('total_cells', 'successful_cells', 'failed_cells', 'forecast_rows')},
        'forecast_signature': result['signature'], 'kpis': list(result['kpis']),
        'cells': sorted(forecast[cell_col].astype(str).unique().tolist()),
        'output_columns': list(forecast.columns), 'preview': [],
        'forecast_start': str(forecast[time_col].min()), 'forecast_end': str(forecast[time_col].max()),
        'upload_history': f'{prefix}/history.csv',
        'download_url': f'/forecast/{run_id}/csv',
        'runtime_seconds': {'preprocessing': result['preprocess_seconds'],
            'forecast_engine': result['forecast_seconds'], 'total': time.perf_counter() - started},
        'calls': {'forecast_model_predict': int(result['performance']['forecast'].get('model_predict_calls', 0)),
            'recursive_state_update': int(result['performance']['forecast'].get('state_update_calls', 0)), 'clustering_predict': 0},
    }
    with tempfile.TemporaryDirectory(prefix='baps-upload-') as directory:
        directory = Path(directory)
        forecast.to_csv(directory / 'forecast.csv', index=False)
        chart_history[[cell_col, time_col, *result['kpis']]].to_csv(directory / 'history.csv', index=False)
        (directory / 'run_metadata.json').write_text(json.dumps(response), encoding='utf8')
        async with AsyncBlobClient() as client:
            # Publish metadata last: a completed run always has its chart and export artifacts.
            for name in ('forecast.csv', 'history.csv', 'run_metadata.json'):
                await client.upload_file(str(directory / name), f'{prefix}/{name}', access='private',
                    add_random_suffix=False, overwrite=False, multipart=(directory / name).stat().st_size >= 5 * 1024 * 1024)
    response['runtime_seconds']['total'] = time.perf_counter() - started
    return response
