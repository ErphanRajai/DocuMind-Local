"""Durable event snapshots contain outputs only, never request credentials."""
import json
from datetime import datetime, timezone, timedelta
from . import documents
from ..models import JobJournal


def save(job):
    with documents.SessionLocal() as db:
        payload = json.dumps(job.events, ensure_ascii=False)
        if len(payload.encode()) > 8_000_000: return
        db.merge(JobJournal(id=job.id, kind=job.kind, state=job.state, payload=payload, updated=datetime.now(timezone.utc)))
        db.flush()
        old=[row[0] for row in db.query(JobJournal.id).filter(JobJournal.state.in_(['completed','failed','cancelled'])).order_by(JobJournal.updated.desc()).offset(100).limit(500).all()]
        if old: db.query(JobJournal).filter(JobJournal.id.in_(old)).delete(synchronize_session=False)
        db.commit()


def recover():
    with documents.SessionLocal() as db:
        db.query(JobJournal).filter(JobJournal.updated < datetime.now(timezone.utc) - timedelta(days=7)).delete()
        records = db.query(JobJournal).order_by(JobJournal.updated.desc()).limit(32).all()
        result = []
        for row in records:
            events = json.loads(row.payload)
            if row.state not in {'completed', 'failed', 'cancelled'}:
                row.state = 'failed'
                events.append({'type': 'error', 'message': 'The backend restarted. This saved draft is incomplete; retry to reuse cached review segments.'})
                row.payload = json.dumps(events)
            result.append({'id': row.id, 'kind': row.kind, 'state': row.state, 'events': events})
        db.commit()
        return result
