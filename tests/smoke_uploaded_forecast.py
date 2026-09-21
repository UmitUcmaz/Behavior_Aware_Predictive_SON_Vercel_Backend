"""Explicit local 100x96 adapter equality check; no external writes."""
import asyncio
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
import warnings
import pandas as pd
from sklearn.exceptions import InconsistentVersionWarning
from backend.app.services import vercel_upload_service as service
from ml_engine.forecast_engine import ForecastEngine

async def main():
    warnings.filterwarnings('ignore', category=InconsistentVersionWarning)
    warnings.filterwarnings('ignore', message='X does not have valid feature names')
    source = Path(sys.argv[1])
    raw = pd.read_csv(source)
    cells = raw['CELL_NAME'].drop_duplicates().iloc[:100]
    raw = raw[raw['CELL_NAME'].isin(cells)]
    content = raw.to_csv(index=False).encode()
    outputs = {}
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c); c.__aexit__ = AsyncMock(return_value=False)
    c.head = AsyncMock(return_value=SimpleNamespace(size=len(content), content_type='text/csv'))
    async def store(local, pathname, **kwargs):
        outputs[pathname] = Path(local).read_bytes()
    c.upload_file = store
    seen = set()
    def progress(event):
        step = event.get('current_step')
        if step in {1,24,48,72,96} and step not in seen:
            seen.add(step); print('ADAPTER_STEP',step,flush=True)
    start=time.perf_counter()
    with patch.object(service,'AsyncBlobClient',return_value=c), patch.object(service,'_download_blob_bytes',AsyncMock(return_value=content)):
        result=await service.forecast_uploaded_csv('uploads/forecast/12345678-1234-4123-8123-123456789abc/history.csv','input_history.csv',96,progress)
    export=outputs[f"forecast-runs/{result['run_id']}/forecast.csv"]
    assert result['successful_cells']==100 and result['failed_cells']==0 and result['forecast_rows']==9600
    print('ADAPTER_RESULT',json.dumps({k:result[k] for k in ['successful_cells','failed_cells','forecast_rows','forecast_signature','runtime_seconds']}),flush=True)
    baseline=ForecastEngine(inspect_runtime=False).forecast(pd.read_csv(BytesIO(content)),96)
    assert baseline['signature']==result['forecast_signature']
    assert baseline['export_df'].to_csv(index=False).encode()==export
    print('DIRECT_ENGINE_CSV_AND_SIGNATURE_EQUALITY_PASS',hashlib.sha256(export).hexdigest(),'total_seconds',round(time.perf_counter()-start,2),flush=True)

if __name__=='__main__':asyncio.run(main())
