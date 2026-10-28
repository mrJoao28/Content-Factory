import tempfile
from pathlib import Path
from typing import Literal

from content_factory_render.archive import MAX_ZIP
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import Field
from starlette.concurrency import run_in_threadpool

from .config import settings
from .db import Session
from .external_render import NOTEBOOK_URL, export_project, import_result, location
from .models import ExternalRenderExport
from .security import safe_path
from .visual_schema import Data

router = APIRouter()


class ExportRequest(Data):
    expected_revision: int = Field(ge=1)


class LocationRequest(ExportRequest):
    execution_location: Literal['local', 'colab']
    hardware: Literal['GPU', 'CPU', 'OPTIX', 'CUDA'] = 'GPU'


@router.get('/external-render/info')
def info():
    return {'notebook_url': NOTEBOOK_URL, 'max_zip_bytes': MAX_ZIP}


@router.post('/projects/{project_id}/render-location')
def change_location(project_id: str, body: LocationRequest):
    return location(project_id, body.expected_revision, body.execution_location, body.hardware)


@router.post('/projects/{project_id}/external-render/export')
def export(project_id: str, body: ExportRequest):
    return export_project(project_id, body.expected_revision)


@router.get('/external-render/exports/{export_id}/download')
def download(export_id: str):
    with Session() as db:
        row = db.get(ExternalRenderExport, export_id)
        if not row or row.state != 'EXPORTED':
            raise HTTPException(404, 'Active export not found')
        return FileResponse(safe_path(settings.output_dir, row.path), media_type='application/zip', filename=f'factory-{row.id}.zip')


@router.post('/projects/{project_id}/external-render/import')
async def upload(project_id: str, request: Request):
    # Raw ZIP avoids parsing an unbounded multipart request before applying route-specific limits.
    if request.headers.get('content-type', '').split(';')[0] != 'application/zip':
        raise HTTPException(415, 'Upload the return ZIP as application/zip')
    length = request.headers.get('content-length')
    if length and (not length.isdigit() or int(length) > MAX_ZIP):
        raise HTTPException(413, 'Return ZIP exceeds 256 MiB')
    with tempfile.TemporaryDirectory(dir=settings.output_dir) as temp:
        archive = Path(temp)/'return.zip'
        size = 0
        with archive.open('wb') as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > MAX_ZIP:
                    raise HTTPException(413, 'Return ZIP exceeds 256 MiB')
                output.write(chunk)
        return await run_in_threadpool(import_result, project_id, archive)
