from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


SQLALCHEMY_DATABSE_URL = "sqlite:////workspace/db_data/pdf_summarizer.db"

engine = create_engine(
    url = SQLALCHEMY_DATABSE_URL, connect_args={"check_same_thread":False}
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