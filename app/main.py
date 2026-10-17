"""FastAPI Claim Processing Pipeline Application.

Exposes:
- POST /api/process: Ingests claim_id and PDF file, runs LangGraph orchestration, returns structured JSON.
- GET /health: Health check and LLM configuration status.
"""

import logging
import os
import shutil
import tempfile
from typing import Annotated
from fastapi import FastAPI, File, Form, HTTPException, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.graph import process_claim_pipeline
from app.pdf_processor import PDFProcessingError, PDFProcessor
from app.schemas import ClaimProcessingResponse, HealthResponse
from app.services.llm_service import LLMConfigurationError, get_llm_service

# Configure root logger
settings = get_settings()
logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("claim_processing_pipeline")

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=settings.app_description,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for frontend integrations or testing tools
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Static Files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get(
    "/",
    response_class=FileResponse,
    summary="Interactive Claim Processing Web Dashboard",
    tags=["Frontend"],
)
async def serve_dashboard():
    """Serves the interactive frontend web dashboard."""
    index_file = os.path.join(static_dir, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file, media_type="text/html")
    return HTMLResponse("<h1>SuperClaims AI Dashboard</h1><p>Visit <a href='/docs'>/docs</a> for API.</p>")


@app.get(
    "/api/sample-pdf",
    summary="Download sample medical claim PDF for one-click testing",
    tags=["Claim Processing"],
)
async def get_sample_medical_pdf():
    """Provide the sample medical claim PDF for one-click evaluation in the frontend."""
    sample_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data", "sample_medical_claim.pdf"))
    if os.path.exists(sample_path):
        return FileResponse(
            sample_path,
            media_type="application/pdf",
            filename="sample_medical_claim.pdf",
        )
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample medical PDF not found.")


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check and status",
    tags=["System"],
)
async def health_check():
    """Verify application health and LLM integration readiness."""
    llm_svc = get_llm_service()
    return HealthResponse(
        status="ok",
        service=settings.app_name,
        version=settings.app_version,
        llm_configured=llm_svc.is_configured(),
        llm_model=settings.llm_model,
        use_mock_llm=settings.use_mock_llm,
    )


@app.post(
    "/api/process",
    response_model=ClaimProcessingResponse,
    status_code=status.HTTP_200_OK,
    summary="Process PDF claim and extract segregated data",
    tags=["Claim Processing"],
)
async def process_claim(
    claim_id: Annotated[str, Form(description="Unique claim identifier")],
    file: Annotated[UploadFile, File(description="Uploaded medical claim PDF file")],
):
    """Process an uploaded medical claim PDF and return extracted structured data."""
    cleaned_claim_id = (claim_id or "").strip()
    if not cleaned_claim_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The 'claim_id' field is required and cannot be empty.",
        )

    filename = file.filename or ""
    is_pdf_content_type = file.content_type in ["application/pdf", "application/x-pdf", "application/octet-stream"]
    is_pdf_extension = filename.lower().endswith(".pdf")

    if not (is_pdf_content_type or is_pdf_extension):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid file format: '{filename}'. Only PDF documents are accepted.",
        )

    max_bytes = settings.max_file_size_bytes
    temp_file_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            temp_file_path = tmp.name
            size_read = 0
            chunk_size = 1024 * 64

            while chunk := await file.read(chunk_size):
                size_read += len(chunk)
                if size_read > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=(
                            f"File size exceeds maximum permitted limit of {settings.max_file_size_mb} MB "
                            f"({size_read} bytes read so far)."
                        ),
                    )
                tmp.write(chunk)

        if size_read == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes).",
            )

        try:
            pages = PDFProcessor.extract_pages_from_file(temp_file_path)
        except PDFProcessingError as pe:
            logger.warning("PDF processing rejected file: %s", str(pe))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to process PDF: {str(pe)}",
            )

        llm_svc = get_llm_service()
        if not llm_svc.is_configured():
            logger.error("Attempted processing without configured LLM credentials.")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "LLM service is not configured. Please configure OPENAI_API_KEY in your "
                    "environment/.env file or enable USE_MOCK_LLM=true for offline demonstration."
                ),
            )

        logger.info("Starting claim pipeline for claim_id=%s with %d pages", cleaned_claim_id, len(pages))
        response = process_claim_pipeline(claim_id=cleaned_claim_id, pages=pages)

        if response.status == "ERROR" and not (
            response.extracted_data.identity_information
            or response.extracted_data.discharge_summary
            or response.extracted_data.itemized_bill
        ):
            logger.error("Claim processing failed: %s", response.errors)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Pipeline processing failed: {'; '.join(response.errors)}",
            )

        return response

    except HTTPException:
        raise
    except LLMConfigurationError as le:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(le),
        )
    except Exception as e:
        logger.exception("Unexpected error during claim processing: %s", str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal processing error: {str(e)}",
        )
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
            except OSError as ex:
                logger.warning("Could not remove temporary file %s: %s", temp_file_path, str(ex))
        await file.close()
