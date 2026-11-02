import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import Response, FileResponse
from pydantic import BaseModel, Field
from typing import Literal

from ..services import study_store as store, documents
from ..models import PDFDocument
router = APIRouter(prefix='/summarizer', tags=['Saved study work'])


@router.get('/library')
async def document_library():
    def read():
        with documents.SessionLocal() as db:
            return [{'id':row.id,'filename':row.filename,'status':row.status,'page_count':row.page_count} for row in db.query(PDFDocument).order_by(PDFDocument.created_at.desc()).limit(500).all()]
    return await asyncio.to_thread(read)


@router.post('/study/backup')
async def backup_database():
    def create():
        import sqlite3
        from pathlib import Path
        from contextlib import closing
        from .. import database
        if database.engine.dialect.name!='sqlite' or database.engine.url.database in {None,':memory:'}: raise HTTPException(409,'Database backups require a file-based SQLite database.')
        source=Path(database.engine.url.database).resolve()
        root=source.parent/'backups';root.mkdir(exist_ok=True)
        name='study-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.sqlite'
        with closing(sqlite3.connect(str(source))) as original, closing(sqlite3.connect(str(root/name))) as copy: original.backup(copy)
        return {'filename':name,'download':'/summarizer/study/backups/'+name,'notice':'Includes the document database and study work. Keep original PDFs separately; this database backup does not embed their files.'}
    return await asyncio.to_thread(create)


@router.get('/study/backups/{name}')
async def download_backup(name:str):
    import re
    from pathlib import Path
    from .. import database
    if not re.fullmatch(r'study-\d{8}T\d{12}\.sqlite',name): raise HTTPException(404,'Backup not found.')
    root=(Path(database.engine.url.database).resolve().parent/'backups').resolve()
    path=(root/name).resolve()
    if not path.is_relative_to(root) or not path.is_file(): raise HTTPException(404,'Backup not found.')
    return FileResponse(path,filename=name,media_type='application/octet-stream',headers={'Cache-Control':'no-store'})

class SavedMessage(BaseModel):
    id: str = Field(min_length=1,max_length=100)
    role: Literal['user','assistant']
    content: str = Field(max_length=1_500_000)
    state: Literal['complete','failed','cancelled','generating'] | None = None
    metrics: dict | None = None


class SavedWorkspace(BaseModel):
    id: str = Field(min_length=1,max_length=100)
    title: str = Field(min_length=1,max_length=255)
    documents: list[dict] = Field(max_length=3)
    messages: list[SavedMessage] = Field(max_length=1000)
    updated: int = Field(ge=0)


class WorkspaceSave(BaseModel):
    workspace: SavedWorkspace
    revision: int | None = Field(None, ge=0)


class ItemSave(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=100)
    kind: str = Field(pattern=r'^(attempt|mistake|formula|bookmark|annotation|practice|active_problem|question_status|rubric|topic)$')
    data: dict
    id: str | None = Field(None, max_length=100)


class ReviewSave(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=100)
    correct: bool


class Rename(BaseModel):
    filename: str = Field(min_length=1, max_length=255, pattern=r'^[^/\\\x00]+\.pdf$')


@router.get('/workspaces')
async def list_workspaces():
    return await asyncio.to_thread(store.workspaces)


@router.get('/workspaces/deleted')
async def deleted_workspaces():
    return await asyncio.to_thread(store.deleted_workspaces)


@router.put('/workspaces/{key}')
async def save_workspace(key: str, payload: WorkspaceSave):
    value=payload.workspace.model_dump(exclude_none=True)
    if len(key) > 100 or value['id'] != key: raise HTTPException(422, 'Workspace ID does not match.')
    for document in value['documents']:
        if type(document.get('id')) is not int or document['id']<1 or not isinstance(document.get('filename'),str): raise HTTPException(422,'Each document needs a positive ID and a filename.')
    return await asyncio.to_thread(store.save_workspace, key, value, payload.revision)


@router.delete('/workspaces/{key}')
async def remove_workspace(key: str):
    return await asyncio.to_thread(store.remove_workspace, key)


@router.get('/workspaces/{key}/export')
async def export_workspace(key: str):
    values = await asyncio.to_thread(store.workspaces)
    workspace = next((w for w in values if w['id'] == key), None)
    if not workspace: raise HTTPException(404, 'Workspace not found.')
    data = {'format': 'documind-study-1', 'workspace': workspace, 'items': await asyncio.to_thread(store.items, key)}
    return Response(json.dumps(data), media_type='application/json', headers={'Content-Disposition': 'attachment; filename="documind-study-backup.json"', 'Cache-Control': 'no-store'})


@router.get('/study/items/{workspace_id}')
async def list_items(workspace_id: str, kind: str | None = None):
    return await asyncio.to_thread(store.items, workspace_id, kind)


@router.post('/study/items', status_code=201)
async def save_item(payload: ItemSave):
    return await asyncio.to_thread(store.save_item, payload.workspace_id, payload.kind, payload.data, payload.id)


@router.post('/study/items/{key}/review')
async def review_item(key: str, payload: ReviewSave):
    return await asyncio.to_thread(store.review_item, key, payload.workspace_id, payload.correct)


@router.delete('/study/items/{key}')
async def remove_item(key: str, workspace_id: str):
    from ..models import StudyItem
    def remove():
        with documents.SessionLocal() as db:
            db.query(StudyItem).filter_by(id=key, workspace_id=workspace_id).delete()
            db.commit()
        return {'removed': key}
    return await asyncio.to_thread(remove)


@router.get('/study/storage')
async def storage():
    return await asyncio.to_thread(store.storage_report)


@router.post('/study/cache/trim')
async def trim_cache():
    return await asyncio.to_thread(store.maintain_cache)


@router.delete('/study/cache')
async def clear_cache():
    return await asyncio.to_thread(store.maintain_cache, True)


@router.patch('/documents/{pdf_id}')
async def rename_document(pdf_id: int, payload: Rename):
    if not await asyncio.to_thread(documents.update_document, pdf_id, filename=payload.filename): raise HTTPException(404, 'Document not found.')
    return (await asyncio.to_thread(documents.read_documents, [pdf_id]))[0]


@router.post('/documents/{pdf_id}/reindex', status_code=202)
async def reindex_document(pdf_id: int, background_tasks: BackgroundTasks, engine: Literal['standard','docling']='standard'):
    from .summarizer import process_pdf_worker
    records = await asyncio.to_thread(documents.read_documents, [pdf_id])
    if not records: raise HTTPException(404, 'Document not found.')
    if records[0]['status'] in {'pending', 'processing', 'indexing'}: raise HTTPException(409, 'This document is already processing.')
    path, filename = await asyncio.to_thread(documents.document_file, pdf_id)
    if engine == 'docling':
        import importlib.util
        if importlib.util.find_spec('docling') is None: raise HTTPException(503, 'Install the optional requirements-docling.txt before selecting layout extraction. Standard extraction remains available.')
    await asyncio.to_thread(documents.update_document, pdf_id, status='pending')
    background_tasks.add_task(process_pdf_worker, pdf_id, path, filename, engine)
    return {'id': pdf_id, 'status': 'pending'}
