"""Tests for LangGraph Workflow Execution."""

from unittest.mock import patch
from app.graph import build_claim_graph, process_claim_pipeline
from app.pdf_processor import PageContent
from app.schemas import ClaimProcessingResponse, DocumentType


def test_full_graph_execution(mock_llm_service, mock_pages):
    """Test end-to-end execution of the LangGraph workflow."""
    response: ClaimProcessingResponse = process_claim_pipeline(
        claim_id="CLM-TEST-001",
        pages=mock_pages,
    )

    assert response.claim_id == "CLM-TEST-001"
    assert response.status == "SUCCESS"
    assert response.segregation_results.total_pages == 4

    assert response.extracted_data.identity_information is not None
    assert response.extracted_data.identity_information.patient_name == "JOHN MICHAEL SMITH"
    assert response.extracted_data.identity_information.source_pages == [3]

    assert response.extracted_data.discharge_summary is not None
    assert "Pneumonia" in response.extracted_data.discharge_summary.diagnosis
    assert response.extracted_data.discharge_summary.source_pages == [4]

    assert response.extracted_data.itemized_bill is not None
    assert len(response.extracted_data.itemized_bill.bill_items) > 0
    assert response.extracted_data.itemized_bill.source_pages == [9]


def test_graph_with_missing_document_categories(mock_llm_service):
    """Test LangGraph when some categories (e.g. itemized bill, discharge summary) are missing."""
    id_only_pages = [
        PageContent(
            page_number=1,
            text="GOVERNMENT ID CARD Full Name: JANE DOE ID Number: ID-111-222-333 Date of Birth: 01-JAN-1990",
            char_count=98,
            has_extractable_text=True,
            is_blank=False,
        )
    ]

    response: ClaimProcessingResponse = process_claim_pipeline(
        claim_id="CLM-ONLY-ID",
        pages=id_only_pages,
    )

    assert response.claim_id == "CLM-ONLY-ID"
    assert response.status == "SUCCESS"
    assert response.extracted_data.identity_information.patient_name == "JOHN MICHAEL SMITH"
    assert response.extracted_data.discharge_summary.extracted is False
    assert response.extracted_data.itemized_bill.extracted is False
