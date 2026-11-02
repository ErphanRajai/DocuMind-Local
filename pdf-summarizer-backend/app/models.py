from sqlalchemy import Column, String, Integer, Text, DateTime, ForeignKey
from datetime import datetime, timezone
from .database import Base

class PDFDocument(Base):
    """
    this class repressents the 'pdf_documents' table in our dataset
    each instance of this class will be a single row in the table
    """
    __tablename__ = "pdf_documents"
    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String, index=True)
    file_path = Column(String)
    raw_text = Column(Text, nullable=True)
    summary = Column(Text, nullable=True)
    error_message = Column(Text, nullable=True)
    warning_message = Column(Text, nullable=True)
    page_count = Column(Integer, nullable=True)
    source_version = Column(Integer, default=0, nullable=False)

    status = Column(String, default="pending")
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class PDFPage(Base):
    __tablename__ = "pdf_pages"
    pdf_id = Column(Integer, ForeignKey("pdf_documents.id", ondelete="CASCADE"), primary_key=True)
    number = Column(Integer, primary_key=True)
    label = Column(String, nullable=True)
    text = Column(Text, nullable=False)


class ReviewCache(Base):
    __tablename__ = "review_cache"
    key = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)


class WorkspaceRecord(Base):
    __tablename__ = 'workspaces'
    id = Column(String, primary_key=True)
    payload = Column(Text, nullable=False)
    revision = Column(Integer, nullable=False, default=1)
    updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class WorkspaceTombstone(Base):
    __tablename__ = 'deleted_workspaces'
    id = Column(String, primary_key=True)
    created = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class StudyItem(Base):
    __tablename__ = 'study_items'
    id = Column(String, primary_key=True)
    workspace_id = Column(String, index=True, nullable=False)
    kind = Column(String, index=True, nullable=False)
    payload = Column(Text, nullable=False)
    updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))


class JobJournal(Base):
    __tablename__ = 'job_journal'
    id = Column(String, primary_key=True)
    kind = Column(String, nullable=False)
    state = Column(String, nullable=False)
    payload = Column(Text, nullable=False)
    updated = Column(DateTime, default=lambda: datetime.now(timezone.utc))
