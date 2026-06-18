from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class PDFDocumentBase(BaseModel):
    """
    shared attributes across schemas. both inputs and outputs
    will at least know the filename
    """
    filename : str

class PDFDocumentCreate(PDFDocumentBase):
    """
    schema for creating a new database record.
    when a file is first uploaded, we will only specify where its saved
    """
    file_path : str

class PDFDocumentResponse(PDFDocumentBase):
    """
    schema for sending data back to the client
    this contains all the fields the client or the frontend are allowed to see
    """
    id : int
    status : str
    raw_text : Optional[str] = None
    summary : Optional[str] = None
    created_at : datetime

    class Config:
        from_attributes = True