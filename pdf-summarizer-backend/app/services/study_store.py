"""Local durable state. Secrets are rejected, not stored in JSON blobs."""
import json
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from sqlalchemy import update

from . import documents
from ..models import WorkspaceRecord, WorkspaceTombstone, StudyItem, ReviewCache, JobJournal, ExamRun


def encoded(value, limit=2_000_000):
    def inspect(value, depth=0):
        if depth > 35: raise HTTPException(422, 'Saved data is nested too deeply.')
        if isinstance(value, dict):
            if any(str(key).lower() in {'api_key', 'apikey', 'password', 'authorization', 'access_token', 'secret'} for key in value):
                raise HTTPException(422, 'Credentials cannot be included in saved work.')
            for item in value.values(): inspect(item, depth + 1)
        elif isinstance(value, list):
            for item in value: inspect(item, depth + 1)
    inspect(value)
    try: result = json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (ValueError,TypeError) as exc: raise HTTPException(422,'Saved data must contain finite numbers and valid JSON values.') from exc
    if len(result.encode()) > limit: raise HTTPException(413, 'Saved work exceeds the size limit. Export or split this workspace.')
    return result


def workspaces():
    with documents.SessionLocal() as db:
        return [{**json.loads(row.payload), 'revision': row.revision} for row in db.query(WorkspaceRecord).order_by(WorkspaceRecord.updated.desc()).limit(100).all()]


def deleted_workspaces():
    with documents.SessionLocal() as db:
        return [row[0] for row in db.query(WorkspaceTombstone.id).order_by(WorkspaceTombstone.created.desc()).limit(10000).all()]


def save_workspace(key, value, revision=None):
    payload = encoded(value)
    with documents.SessionLocal() as db:
        row = db.get(WorkspaceRecord, key)
        if row:
            if revision != row.revision: raise HTTPException(409, 'This workspace changed in another tab. Reload before saving; your browser copy is retained.')
            changed = db.execute(update(WorkspaceRecord).where(WorkspaceRecord.id == key, WorkspaceRecord.revision == revision).values(payload=payload, revision=revision + 1, updated=datetime.now(timezone.utc)))
            if changed.rowcount != 1: raise HTTPException(409, 'Another tab saved first. Reload before saving.')
            revision += 1
        else:
            if db.get(WorkspaceTombstone,key): raise HTTPException(409,'This workspace was removed. Import its backup as a new workspace to restore it.')
            if db.query(WorkspaceRecord).count() >= 100: raise HTTPException(409, 'The local workspace limit is 100. Export and remove an old workspace.')
            if revision not in (None, 0): raise HTTPException(409, 'The workspace was removed in another tab.')
            revision = 1
            db.add(WorkspaceRecord(id=key, payload=payload, revision=revision))
        db.commit()
    return {'id': key, 'revision': revision}


def remove_workspace(key):
    with documents.SessionLocal() as db:
        db.query(WorkspaceRecord).filter_by(id=key).delete()
        db.query(StudyItem).filter_by(workspace_id=key).delete()
        db.query(ExamRun).filter_by(workspace_id=key).delete()
        db.merge(WorkspaceTombstone(id=key))
        db.commit()
    return {'removed': key}


def items(workspace_id, kind=None):
    with documents.SessionLocal() as db:
        query = db.query(StudyItem).filter_by(workspace_id=workspace_id)
        if kind: query = query.filter_by(kind=kind)
        return [{'id': row.id, 'kind': row.kind, 'workspace_id': row.workspace_id, 'data': json.loads(row.payload)} for row in query.order_by(StudyItem.updated.desc()).limit(500).all()]


def save_item(workspace_id, kind, data, key=None):
    payload = encoded(data, 150_000)
    key = key or uuid.uuid4().hex
    with documents.SessionLocal() as db:
        row = db.get(StudyItem, key)
        if row and (row.workspace_id != workspace_id or row.kind != kind): raise HTTPException(409, 'This item belongs to another workspace or kind.')
        if not row and db.query(StudyItem).filter_by(workspace_id=workspace_id).count() >= 500: raise HTTPException(409, 'This workspace has 500 study items. Export and remove old items.')
        db.merge(StudyItem(id=key, workspace_id=workspace_id, kind=kind, payload=payload, updated=datetime.now(timezone.utc)))
        db.commit()
    return {'id': key, 'kind': kind, 'workspace_id': workspace_id, 'data': data}


def review_item(key, workspace_id, correct):
    with documents.SessionLocal() as db:
        row = db.get(StudyItem, key)
        if not row or row.workspace_id != workspace_id: raise HTTPException(404, 'Review item not found.')
        data = json.loads(row.payload)
        interval = min(90, max(1, int(data.get('interval_days', 0)) * 2)) if correct else 1
        data.update(interval_days=interval, due=(datetime.now(timezone.utc) + timedelta(days=interval)).isoformat(),
                    attempts=min(100000, int(data.get('attempts', 0)) + 1), last_correct=correct)
        row.payload = encoded(data)
        kind = row.kind
        row.updated = datetime.now(timezone.utc)
        db.commit()
    return {'id': key, 'kind': kind, 'data': data}


def storage_report():
    with documents.SessionLocal() as db:
        cache = db.query(ReviewCache).all()
        return {'workspaces': db.query(WorkspaceRecord).count(), 'study_items': db.query(StudyItem).count(),
                'review_cache_entries': len(cache), 'review_cache_bytes': sum(len(row.payload.encode()) for row in cache),
                'journal_entries': db.query(JobJournal).count(), 'cache_limit_entries': 2000}


def maintain_cache(clear=False):
    with documents.SessionLocal() as db:
        keys = db.query(ReviewCache.key).order_by(ReviewCache.key).all()
        remove = [row[0] for row in keys] if clear else [row[0] for row in keys[:-2000]]
        if remove: db.query(ReviewCache).filter(ReviewCache.key.in_(remove)).delete(synchronize_session=False)
        db.commit()
    return {'removed': len(remove), 'policy': 'Keep at most 2000 entries; deterministic eviction, not LRU.'}
