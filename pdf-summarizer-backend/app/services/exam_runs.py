"""Durable, idempotent exam checkpoints. Never persist provider credentials."""
import json
import uuid
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import update
from . import documents, study_store
from ..models import ExamRun

BOOT = uuid.uuid4().hex

def read(key, workspace=None):
    with documents.SessionLocal() as db:
        row=db.get(ExamRun,key)
        if not row or workspace is not None and row.workspace_id!=workspace: raise HTTPException(404,'Exam run not found.')
        return {'id':row.id,'workspace_id':row.workspace_id,'state':row.state,**json.loads(row.payload)}

def listing(workspace):
    with documents.SessionLocal() as db:
        rows=db.query(ExamRun).filter_by(workspace_id=workspace).order_by(ExamRun.updated.desc()).limit(50).all()
        return [{'id':r.id,'state':r.state,'exam_pdf_id':json.loads(r.payload)['request']['exam_pdf_id'],
                 'completed':len(json.loads(r.payload).get('answers',{})), 'updated':r.updated.isoformat()} for r in rows]

def create(workspace, payload):
    key=uuid.uuid4().hex
    with documents.SessionLocal() as db:
        db.add(ExamRun(id=key,workspace_id=workspace,payload=study_store.encoded(payload,8_000_000),state='ready'))
        db.commit()
    return key

def claim(key):
    with documents.SessionLocal() as db:
        row=db.get(ExamRun,key)
        if not row: raise HTTPException(404,'Exam run not found.')
        if row.state=='running' and row.owner==BOOT: raise HTTPException(409,'This exam is already running. Stop it before resuming.')
        changed=db.execute(update(ExamRun).where(ExamRun.id==key,ExamRun.state==row.state,ExamRun.owner==row.owner).values(state='running',owner=BOOT))
        if changed.rowcount!=1: raise HTTPException(409,'Another request resumed this exam first.')
        db.commit()

def checkpoint(key, payload, state='running'):
    with documents.SessionLocal() as db:
        row=db.get(ExamRun,key)
        if not row: raise HTTPException(404,'Exam run was removed.')
        row.payload=study_store.encoded(payload,8_000_000);row.state=state;row.updated=datetime.now(timezone.utc)
        db.commit()

def feedback(key, index, value):
    run=read(key)
    if str(index) not in run.get('answers',{}):raise HTTPException(404,'Answer not found.')
    # A separate record preserves the answer/checkpoint and supports future regression review.
    return study_store.save_item(run['workspace_id'],'answer_feedback',{'run_id':key,'question_index':index,**value})
