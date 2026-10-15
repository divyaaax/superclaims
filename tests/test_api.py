"""Tests for FastAPI HTTP Endpoints and Request Validation."""

import io
from unittest.mock import patch
from fastapi.testclient import TestClient
import pypdf


def test_api_process_success(client: TestClient, sample_pdf_bytes, mock_llm_service):
    """Test successful POST /api/process with valid claim_id and PDF file."""
    files = {"file": ("claim_docs.pdf", sample_pdf_bytes, "application/pdf")}
    data = {"claim_id": "CLM-2025-001"}

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 200

    res_json = response.json()
    assert res_json["claim_id"] == "CLM-2025-001"
    assert res_json["status"] == "SUCCESS"
    assert "segregation_results" in res_json
    assert "extracted_data" in res_json


def test_api_process_missing_claim_id(client: TestClient, sample_pdf_bytes):
    """Test rejection when claim_id is whitespace or omitted."""
    files = {"file": ("claim.pdf", sample_pdf_bytes, "application/pdf")}
    data = {"claim_id": "   "}

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 400
    assert "claim_id" in response.json()["detail"].lower()


def test_api_process_invalid_file_extension(client: TestClient):
    """Test rejection when an image or text file is uploaded instead of a PDF."""
    files = {"file": ("claim.txt", b"plain text claim details", "text/plain")}
    data = {"claim_id": "CLM-2025-002"}

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 400
    assert "only pdf documents are accepted" in response.json()["detail"].lower()


def test_api_process_corrupt_pdf(client: TestClient):
    """Test rejection when uploaded file is corrupted."""
    files = {"file": ("corrupt.pdf", b"NOT_A_VALID_PDF_STREAM", "application/pdf")}
    data = {"claim_id": "CLM-CORRUPT"}

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 400
    assert "failed to process pdf" in response.json()["detail"].lower()


def test_api_process_unconfigured_llm(client: TestClient, sample_pdf_bytes):
    """Test 503 error when LLM API key is missing and mock mode is off."""
    with patch("app.main.get_llm_service") as mock_get_svc:
        mock_svc = mock_get_svc.return_value
        mock_svc.is_configured.return_value = False

        files = {"file": ("claim.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"claim_id": "CLM-NO-KEY"}

        response = client.post("/api/process", data=data, files=files)
        assert response.status_code == 503
        assert "llm service is not configured" in response.json()["detail"].lower()


def test_api_process_file_too_large(client: TestClient, sample_pdf_bytes):
    """Test rejection with 413 when file exceeds MAX_FILE_SIZE_MB limit."""
    with patch("app.main.settings.max_file_size_mb", 0):  # Set limit to 0 MB (0 bytes)
        files = {"file": ("large_claim.pdf", sample_pdf_bytes, "application/pdf")}
        data = {"claim_id": "CLM-TOO-LARGE"}

        response = client.post("/api/process", data=data, files=files)
        assert response.status_code == 413
        assert "exceeds maximum permitted limit" in response.json()["detail"].lower()
