from sqlalchemy import Column, String, Integer, Text, DateTime
from datetime import datetime
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

    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)