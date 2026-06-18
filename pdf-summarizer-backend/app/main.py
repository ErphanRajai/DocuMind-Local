from fastapi import FastAPI
from .database import engine
from . import models

from .routers import summarizer


models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title= "AI PDF Summarizer Backend",
    description= "API for uploading PDFs and generating AI Summaries",
    version="1.0.0"
)

app.include_router(summarizer.router)
@app.get("/")
async def root():
    return {"status": "healthy",
            "message": "Welcome to the AI PDF summarizer API"}
