import ast
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd

from backend.app.services import vercel_chart_service as service

RUN = 'VAL-20260919T162449116079Z'
CSV = b'''CELL_NAME,SDATE,ACTIVE_USERS_ACTUAL,ACTIVE_USERS_FORECAST
A,2026-09-10 16:30:00,3,4
A,2026-09-10 16:15:00,1,2
B,2026-09-10 16:15:00,99,100
A,bad-time,5,6
A,2026-09-10 16:45:00,,7
A,2026-09-10 17:00:00,invalid,8
A,2026-09-10 16:15:00,1,2
'''


def legacy_chart():
    # Execute only the existing chart function, avoiding the legacy service's
    # unrelated filesystem-only forecast imports (absent in this deployment).
    source = Path('backend/app/services/validation_service.py').read_text(encoding='utf-8-sig')
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'get_validation_chart_data')
    scope = {'pd': pd, 'get_validation_csv_path': lambda _: BytesIO(CSV),
             'get_forecast_metadata': lambda: SimpleNamespace(schema={})}
    exec(compile(ast.Module(body=[node], type_ignores=[]), '<legacy-chart>', 'exec'), scope)
    return scope['get_validation_chart_data'](RUN, 'A', 'ACTIVE_USERS')


class ValidationBlobChartTests(unittest.IsolatedAsyncioTestCase):
    async def test_exact_legacy_equality_including_nulls_order_and_duplicates(self):
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=client)
        client.__aexit__ = AsyncMock(return_value=False)
        with patch.object(service, 'AsyncBlobClient', return_value=client), patch.object(service, '_get_blob_bytes', AsyncMock(return_value=CSV)) as read:
            result = await service.get_validation_chart_data(RUN, 'A', 'ACTIVE_USERS')
        self.assertEqual(result, legacy_chart())
        self.assertEqual(len(result['points']), 3)
        read.assert_awaited_once_with(client, f'validation-runs/{RUN}/validation_matched.csv')

    async def test_invalid_id_and_kpi_fail_before_blob_access(self):
        with patch.object(service, 'AsyncBlobClient') as client:
            for identifier, kpi in [('VAL-../../source', 'ACTIVE_USERS'), (RUN, 'UNKNOWN')]:
                with self.assertRaises(ValueError):
                    await service.get_validation_chart_data(identifier, 'A', kpi)
            client.assert_not_called()

    async def test_missing_cell_does_not_invent_points(self):
        with patch.object(service, 'AsyncBlobClient'), patch.object(service, '_get_blob_bytes', AsyncMock(return_value=CSV)):
            with self.assertRaisesRegex(ValueError, 'Cell not found'):
                await service.get_validation_chart_data(RUN, 'missing', 'ACTIVE_USERS')

    async def test_missing_artifact_is_not_a_successful_empty_chart(self):
        with patch.object(service, 'AsyncBlobClient'), patch.object(service, '_get_blob_bytes', AsyncMock(side_effect=FileNotFoundError)):
            with self.assertRaises(FileNotFoundError):
                await service.get_validation_chart_data(RUN, 'A', 'ACTIVE_USERS')


if __name__ == '__main__':
    unittest.main()
