import os
import sqlite3
from contextlib import closing
from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pdf_summarizer.db"))
SQLALCHEMY_DATABASE_URL = os.getenv("DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine = create_engine(
    url=SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def initialize_database():
    """Add diagnostics to existing local databases without rebuilding their data."""
    inspector = inspect(engine)
    if inspector.has_table("pdf_documents"):
        existing = {column["name"] for column in inspector.get_columns("pdf_documents")}
        column_types = {"error_message": "TEXT", "warning_message": "TEXT", "page_count": "INTEGER",
                        "source_version": "INTEGER NOT NULL DEFAULT 0"}
        missing = set(column_types) - existing
        if missing and engine.dialect.name == "sqlite" and engine.url.database != ":memory:":
            source = Path(engine.url.database)
            suffix = ".before_processing_diagnostics.bak" if missing & {"error_message", "warning_message"} else ".before_page_citations.bak"
            backup = source.with_name(source.name + suffix)
            if source.is_file() and not backup.exists():
                with closing(sqlite3.connect(str(source))) as original, closing(sqlite3.connect(str(backup))) as copy:
                    original.backup(copy)
        with engine.begin() as connection:
            for column in sorted(missing):
                connection.exec_driver_sql(f"ALTER TABLE pdf_documents ADD COLUMN {column} {column_types[column]}")
            if "error_message" in missing:
                connection.exec_driver_sql(
                    "UPDATE pdf_documents SET error_message = summary, summary = NULL "
                    "WHERE status = 'failed' AND summary LIKE 'Error during %'"
                )
    Base.metadata.create_all(bind=engine)

def get_db():
    """
    Creates a new database session for a single web request,
    and ensures it closes automatically after it finishes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
