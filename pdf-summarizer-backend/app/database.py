import os

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DEFAULT_DB_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "pdf_summarizer.db"))
SQLALCHEMY_DATABASE_URL = os.getenv("DB_URL", f"sqlite:///{DEFAULT_DB_PATH}")

engine = create_engine(
    url=SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

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