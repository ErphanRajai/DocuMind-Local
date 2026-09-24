import io
from unittest.mock import patch, AsyncMock
from fastapi import status


def test_root_endpoint(client):
    response = client.get("/")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["status"] == "healthy"


@patch("app.main.qdrant_client.get_collections", new_callable=AsyncMock)
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
def test_healthz_healthy(mock_ollama_get, mock_qdrant_get, client):
    mock_ollama_get.return_value.status_code = 200
    mock_qdrant_get.return_value = True

    response = client.get("/healthz")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["qdrant"] == "connected"
    assert data["ollama"] == "connected"


@patch("app.main.qdrant_client.get_collections", side_effect=Exception("Qdrant Down"))
@patch("httpx.AsyncClient.get", new_callable=AsyncMock)
def test_healthz_degraded(mock_ollama_get, mock_qdrant_get, client):
    mock_ollama_get.return_value.status_code = 200

    response = client.get("/healthz")
    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    data = response.json()
    assert data["status"] == "degraded"
    assert "unreachable" in data["qdrant"]


def test_upload_pdf_invalid_format(client):
    file_payload = {"file": ("test.txt", io.BytesIO(b"dummy text"), "text/plain")}
    response = client.post("/summarizer/upload", files=file_payload)
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "Only PDF files are allowed" in response.json()["detail"]


@patch("app.routers.summarizer.process_pdf_worker")
@patch("builtins.open", create=True)
def test_upload_pdf_success(mock_open, mock_worker, client):
    fake_pdf = io.BytesIO(b"%PDF-1.4 simulated content")
    file_payload = {"file": ("sample_document.pdf", fake_pdf, "application/pdf")}

    response = client.post("/summarizer/upload", files=file_payload)
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["filename"] == "sample_document.pdf"
    assert data["status"] == "pending"
    assert "id" in data


def test_get_pdf_status_not_found(client):
    response = client.get("/summarizer/99999")
    assert response.status_code == status.HTTP_404_NOT_FOUND