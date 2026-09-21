import asyncio
from io import BytesIO
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
from backend.app.services import vercel_upload_service as service
from backend.app.services.forecast_input_inspection import inspect_forecast_bytes
from api import upload_routes
from api.production_routes import WORKING_BLOB_PREFIXES, FORECAST_BLOB_FILES
from backend.app.services import vercel_chart_service as chart

PATH = 'uploads/forecast/12345678-1234-4123-8123-123456789abc/history.csv'
CSV = b'CELL_NAME,SDATE,LTE_UL_PRB_UTILIZATION_PCT,LTE_DL_PRB_UTILIZATION_PCT,LTE_TRAFFIC_ACTIVEUSER_MAX\nA,2026-09-10 16:15:00,1,2,3\n'
def client_mock():
    c = MagicMock()
    c.__aenter__ = AsyncMock(return_value=c)
    c.__aexit__ = AsyncMock(return_value=False)
    c.head = AsyncMock(return_value=SimpleNamespace(size=len(CSV), content_type='text/csv'))
    return c

class BlobUploadTests(unittest.IsolatedAsyncioTestCase):
    async def test_inspection_bytes_are_unchanged(self):
        with patch.object(service, 'AsyncBlobClient', return_value=client_mock()), patch.object(service, '_download_blob_bytes', AsyncMock(return_value=CSV)) as read:
            actual = await service.inspect_uploaded_csv(PATH, 'history.csv')
            self.assertEqual(actual, inspect_forecast_bytes(CSV, 'history.csv'))
            read.assert_awaited_once_with(PATH)

    async def test_bad_path_never_reads_blob(self):
        with patch.object(service, '_download_blob_bytes', AsyncMock()) as read:
            for path in ['source/network_traffic.csv.gz', 'https://attacker/a.csv', PATH.replace('history.csv', '../history.csv')]:
                with self.assertRaises(ValueError): await service.read_uploaded_csv(path, 'history.csv')
            read.assert_not_awaited()

    async def test_size_and_type_fail_before_download(self):
        c = client_mock()
        with patch.object(service, 'AsyncBlobClient', return_value=c), patch.object(service, '_download_blob_bytes', AsyncMock()) as read:
            for size, content_type in [(service.MAX_UPLOAD_BYTES + 1, 'text/csv'), (0, 'text/csv'), (10, 'text/html')]:
                c.head.return_value = SimpleNamespace(size=size, content_type=content_type)
                with self.assertRaises(ValueError): await service.read_uploaded_csv(PATH, 'a.csv')
            read.assert_not_awaited()

    async def test_missing_columns_and_timestamps_keep_legacy_validation(self):
        for content in [b'CELL_NAME,SDATE\nA,nope\n', CSV.replace(b'2026-09-10 16:15:00', b'invalid')]:
            with self.assertRaises(ValueError): inspect_forecast_bytes(content, 'a.csv')

    async def test_sse_streams_progress_then_result_and_sanitizes_errors(self):
        async def run(path, name, steps, progress):
            progress({'stage': 'recursive_forecasting', 'current_step': 1})
            await asyncio.sleep(0)
            return {'status': 'completed', 'forecast_rows': 9600}
        with patch.object(upload_routes, 'forecast_uploaded_csv', run):
            response = await upload_routes.uploaded_events(PATH, 'a.csv', 96)
            events = [json.loads(chunk.removeprefix('data: ').strip()) async for chunk in response.body_iterator]
        self.assertEqual([e['type'] for e in events], ['connected', 'progress', 'result'])
        with patch.object(upload_routes, 'forecast_uploaded_csv', AsyncMock(side_effect=RuntimeError('credential-bearing error'))):
            response = await upload_routes.uploaded_events(PATH, 'a.csv', 96)
            content = ''.join([chunk async for chunk in response.body_iterator])
            self.assertNotIn('credential-bearing', content)
            self.assertIn('error', content)

    async def test_chart_reads_run_owned_uploaded_history(self):
        run = 'FR-20260920T200803564014Z'
        history = CSV.replace(b'LTE_UL_PRB_UTILIZATION_PCT', b'UL_PRB_UTILIZATION')
        forecast = b'CELL_NAME,SDATE,UL_PRB_UTILIZATION_FORECAST\nA,2026-09-10 16:30:00,2\n'
        read = AsyncMock(side_effect=[history, forecast])
        with patch.object(chart, 'AsyncBlobClient', return_value=client_mock()), patch.object(chart, '_get_json_blob', AsyncMock(return_value={'source_type': 'uploaded'})), patch.object(chart, '_get_blob_bytes', read):
            result = await chart.get_forecast_chart_data(run, 'A', 'UL_PRB_UTILIZATION')
        self.assertEqual(read.await_args_list[0].args[1], f'forecast-runs/{run}/history.csv')
        self.assertIsInstance(result, dict)

    def test_upload_ttl_does_not_include_permanent_source(self):
        self.assertIn('uploads/forecast/', WORKING_BLOB_PREFIXES)
        self.assertFalse(any('source/network_traffic.csv.gz'.startswith(p) for p in WORKING_BLOB_PREFIXES))
        self.assertIn('history.csv', FORECAST_BLOB_FILES)

if __name__ == '__main__': unittest.main()
