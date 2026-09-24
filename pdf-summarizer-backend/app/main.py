import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .database import Base, engine
from .routers import summarizer
from .services.llm_service import LLMService
from .services.vector_db import (
    client as qdrant_client,
    init_vector_db,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQL tables
    Base.metadata.create_all(bind=engine)
    # Initialize Qdrant collection
    init_vector_db()
    yield


app = FastAPI(
    title="DocuMind Backend",
    version="1.1.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(summarizer.router)


@app.get("/healthz")
async def healthz():
    status = {"status": "healthy", "qdrant": "connected", "ollama": "connected"}

    # 1. Check Qdrant (Synchronous Client - DO NOT AWAIT)
    try:
        collections = qdrant_client.get_collections()
        if not collections:
            status["qdrant"] = "degraded: no response"
            status["status"] = "degraded"
    except Exception as e:
        status["qdrant"] = f"unreachable: {str(e)}"
        status["status"] = "degraded"

    # 2. Check Ollama
    try:
        async with httpx.AsyncClient(timeout=3.0) as http_client:
            res = await http_client.get("http://host.docker.internal:11434/")
            if res.status_code != 200:
                # Fallback check standard localhost if not in docker bridge
                res = await http_client.get("http://localhost:11434/")
    except Exception:
        # Check basic Ollama reachability via LLMService endpoint
        try:
            async with httpx.AsyncClient(timeout=3.0) as http_client:
                res = await http_client.get(LLMService.API_URL.replace("/api/chat", "/"))
        except Exception as e:
            status["ollama"] = f"unreachable: {str(e)}"
            status["status"] = "degraded"

    return status