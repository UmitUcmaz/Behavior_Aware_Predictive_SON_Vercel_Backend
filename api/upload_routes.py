"""Reference-only upload endpoints. CSV bytes never enter the Function request."""
import asyncio
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from backend.app.services.vercel_upload_service import (
    inspect_uploaded_csv, forecast_uploaded_csv, validate_upload_reference,
)
from api.production_routes import _cleanup_expired_working_blobs, _sse_event

router = APIRouter()
class UploadedCsvRequest(BaseModel):
    pathname: str = Field(max_length=150)
    filename: str = Field(max_length=255)

@router.post('/api/forecast/inspect-blob')
async def inspect_blob(payload: UploadedCsvRequest):
    try:
        result = await inspect_uploaded_csv(payload.pathname, payload.filename)
        await _cleanup_expired_working_blobs()
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(404, 'Uploaded CSV is unavailable or expired. Please upload it again.') from exc
    except Exception as exc:
        raise HTTPException(502, 'Could not read the private CSV. Please retry the upload.') from exc

@router.get('/api/forecast/uploaded/events')
async def uploaded_events(pathname: str, filename: str, horizon_steps: int = 96):
    try:
        validate_upload_reference(pathname, filename)
        if horizon_steps not in {12, 24, 48, 96}:
            raise ValueError('horizon_steps must be one of: 12, 24, 48, 96')
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    async def events():
        queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        def progress(data):
            loop.call_soon_threadsafe(queue.put_nowait, ('progress', data))
        async def worker():
            try:
                result = await forecast_uploaded_csv(pathname, filename, horizon_steps, progress)
                await queue.put(('result', result))
            except ValueError as exc:
                await queue.put(('error', {'message': str(exc)}))
            except FileNotFoundError:
                await queue.put(('error', {'message': 'Uploaded CSV is unavailable or expired. Please upload it again.'}))
            except Exception:
                await queue.put(('error', {'message': 'Uploaded-data forecast failed. Please retry or check the input dataset.'}))
            finally:
                await queue.put(('done', None))
        task = asyncio.create_task(worker())
        yield _sse_event('connected', {'status': 'running'})
        try:
            while True:
                kind, data = await queue.get()
                if kind == 'done': break
                yield _sse_event(kind, data)
        finally:
            if not task.done(): task.cancel()
            try: await task
            except asyncio.CancelledError: pass
    return StreamingResponse(events(), media_type='text/event-stream', headers={
        'Cache-Control': 'no-cache, no-store, no-transform', 'X-Accel-Buffering': 'no',
        'X-Content-Type-Options': 'nosniff',
    })
