"""Docker-free backend using canonical PDFs/SQLite and a separate Qdrant index.

Run from any directory: pdf-summarizer-backend/venv_win/Scripts/python run_local.py
The frontend still runs with Next. No Docker volumes are opened or rewritten.
"""
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent


def local_environment():
    import launcher
    environment = launcher.ENVIRONMENT.copy()
    port = environment.get('DOCUMIND_OLLAMA_PORT','21434')
    environment.update(DB_URL='sqlite:///' + (ROOT/'db_data'/'pdf_summarizer.db').as_posix(),
        DOCUMIND_UPLOAD_DIR=str(ROOT/'uploaded_pdfs'),
        DOCUMIND_QDRANT_LOCAL_PATH=str(ROOT/'db_data'/'qdrant_local'),
        OLLAMA_API_URL=f'http://127.0.0.1:{port}/api/chat',
        OLLAMA_EMBED_URL=f'http://127.0.0.1:{port}/api/embeddings',
        OLLAMA_TAGS_URL=f'http://127.0.0.1:{port}/api/tags')
    return environment


if __name__ == '__main__':
    os.environ.update(local_environment())
    sys.path.insert(0,str(ROOT/'pdf-summarizer-backend'))
    os.chdir(ROOT)
    (ROOT/'db_data').mkdir(exist_ok=True)
    import uvicorn
    uvicorn.run('app.main:app',host='127.0.0.1',port=int(os.getenv('DOCUMIND_BACKEND_PORT','8888')))
