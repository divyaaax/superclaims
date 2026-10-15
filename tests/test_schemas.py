"""Tests for Pydantic Data Models and Schemas."""

from decimal import Decimal
import pytest
from pydantic import ValidationError
from app.schemas import (
    BillItem,
    ClaimProcessingResponse,
    DischargeSummaryData,
    DocumentType,
    ExtractedData,
    IdentityData,
    ItemizedBillData,
    PageClassification,
    SegregationSummary,
)


def test_document_type_exact_nine_categories():
    """Verify that DocumentType contains strictly the 9 required categories."""
    expected_categories = {
        "claim_forms",
        "cheque_or_bank_details",
        "identity_document",
        "itemized_bill",
        "discharge_summary",
        "prescription",
        "investigation_report",
        "cash_receipt",
        "other",
    }
    actual_categories = {dt.value for dt in DocumentType}
    assert actual_categories == expected_categories
    assert len(DocumentType) == 9


def test_page_classification_invalid_category():
    """Verify PageClassification rejects an invented document category."""
    with pytest.raises(ValidationError):
        PageClassification(
            page_number=1,
            document_type="invalid_custom_category",  # type: ignore
        )


def test_bill_item_decimal_validation():
    """Verify BillItem supports Decimal arithmetic without precision loss."""
    item = BillItem(
        item_description="CT Scan",
        quantity=Decimal("1"),
        unit_price=Decimal("800.00"),
        amount=Decimal("800.00"),
    )
    assert item.amount == Decimal("800.00")
    json_data = item.model_dump_json()
    assert "800" in json_data


def test_claim_processing_response_structure():
    """Verify structure and serialization of ClaimProcessingResponse."""
    segregation = SegregationSummary(
        total_pages=1,
        categories={"identity_document": [1]},
        page_classifications=[
            PageClassification(
                page_number=1,
                document_type=DocumentType.IDENTITY_DOCUMENT,
                confidence=1.0,
            )
        ],
    )
    extracted = ExtractedData(
        identity_information=IdentityData(
            patient_name="John Doe",
            date_of_birth="1980-01-01",
            source_pages=[1],
            extracted=True,
        )
    )
    response = ClaimProcessingResponse(
        claim_id="CLM-1001",
        status="SUCCESS",
        processing_time_seconds=0.45,
        segregation_results=segregation,
        extracted_data=extracted,
        errors=[],
    )
    assert response.claim_id == "CLM-1001"
    assert response.extracted_data.identity_information.patient_name == "John Doe"
