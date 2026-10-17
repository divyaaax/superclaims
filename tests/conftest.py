"""Pytest Configuration and Fixtures.

Provides fixtures for:
- FastAPI test client
- Sample PDF bytes
- Mock LLM responses for segregation and extraction
- Mocked LLM service
"""

from decimal import Decimal
import io
import os
import pytest
from fastapi.testclient import TestClient
import pypdf

from app.config import Settings
from app.main import app
from app.pdf_processor import PageContent
from app.schemas import (
    BatchClassificationResponse,
    BillItem,
    DischargeSummaryData,
    DocumentType,
    IdentityData,
    ItemizedBillData,
    PageClassification,
)
from app.services.llm_service import LLMService


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def sample_pdf_bytes():
    """Generates a minimal valid 2-page PDF in memory."""
    writer = pypdf.PdfWriter()
    writer.add_blank_page(width=200, height=200)
    writer.add_blank_page(width=200, height=200)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


@pytest.fixture
def real_sample_pdf_path():
    """Path to the real 18-page sample medical claim PDF."""
    path = os.path.join(os.path.dirname(__file__), "..", "data", "sample_medical_claim.pdf")
    return os.path.abspath(path)


@pytest.fixture
def mock_pages():
    """Mock list of PageContent representing diverse document pages."""
    return [
        PageContent(
            page_number=1,
            text="MEDICAL CLAIM FORM HealthCare Insurance Company Claim Reference: CLM-2024-789456",
            char_count=80,
            has_extractable_text=True,
            is_blank=False,
        ),
        PageContent(
            page_number=3,
            text="GOVERNMENT ID CARD Full Name: JOHN MICHAEL SMITH ID Number: ID-987-654-321 Date of Birth: 15-MAR-1985",
            char_count=100,
            has_extractable_text=True,
            is_blank=False,
        ),
        PageContent(
            page_number=4,
            text="CITY MEDICAL CENTER DISCHARGE SUMMARY Name: John Michael Smith Admission Date: January 20, 2025 Discharge Date: January 25, 2025 Attending Physician: Dr. Sarah Johnson, MD Diagnosis: Community Acquired Pneumonia (CAP)",
            char_count=210,
            has_extractable_text=True,
            is_blank=False,
        ),
        PageContent(
            page_number=9,
            text="ITEMIZED HOSPITAL BILL Bill Number: BILL-2025-789456 Room Charges 5 $200.00 $1000.00 Subtotal: $1000.00 Tax (5%): $50.00 Total Amount: $1050.00",
            char_count=150,
            has_extractable_text=True,
            is_blank=False,
        ),
    ]


class MockLLMService(LLMService):
    """Deterministic Mock LLM Service for unit tests and local evaluation."""

    def is_configured(self) -> bool:
        return True

    def invoke_structured(self, messages, schema):
        user_content = messages[-1].content

        if schema == BatchClassificationResponse:
            classifications = []
            for line in user_content.split("--- START PAGE "):
                if not line.strip():
                    continue
                page_part = line.split(" ---")[0]
                try:
                    p_num = int(page_part)
                except ValueError:
                    continue

                lower_text = line.lower()
                if "government id card" in lower_text or "identity" in lower_text:
                    doc_type = DocumentType.IDENTITY_DOCUMENT
                elif "discharge summary" in lower_text:
                    doc_type = DocumentType.DISCHARGE_SUMMARY
                elif "itemized hospital bill" in lower_text or "itemized bill" in lower_text:
                    doc_type = DocumentType.ITEMIZED_BILL
                elif "medical claim form" in lower_text:
                    doc_type = DocumentType.CLAIM_FORMS
                elif "cheque" in lower_text or "bank account" in lower_text:
                    doc_type = DocumentType.CHEQUE_OR_BANK_DETAILS
                elif "prescription" in lower_text or "rx " in lower_text:
                    doc_type = DocumentType.PRESCRIPTION
                elif "laboratory report" in lower_text or "pathology" in lower_text or "panel" in lower_text:
                    doc_type = DocumentType.INVESTIGATION_REPORT
                elif "cash receipt" in lower_text:
                    doc_type = DocumentType.CASH_RECEIPT
                else:
                    doc_type = DocumentType.OTHER

                classifications.append(
                    PageClassification(
                        page_number=p_num,
                        document_type=doc_type,
                        confidence=0.95,
                        reasoning=f"Identified keywords matching {doc_type.value}",
                    )
                )
            return BatchClassificationResponse(classifications=classifications)

        if schema == IdentityData:
            return IdentityData(
                patient_name="JOHN MICHAEL SMITH",
                date_of_birth="15-MAR-1985",
                id_numbers={"id_number": "ID-987-654-321", "id_type": "Government ID Card"},
                policy_details=None,
                gender="Male",
                address="456 Oak Street, Apt 12B, Springfield, IL 62701",
                source_pages=[],
                extracted=True,
            )

        if schema == DischargeSummaryData:
            return DischargeSummaryData(
                diagnosis="Community Acquired Pneumonia (CAP)",
                admission_date="January 20, 2025",
                discharge_date="January 25, 2025",
                physician_details={"name": "Dr. Sarah Johnson, MD", "title": "Attending Physician"},
                hospital_name="City Medical Center",
                discharge_condition="Stable, improved",
                discharge_medications=["Amoxicillin 500mg TID x 7 days", "Acetaminophen 500mg PRN for pain"],
                source_pages=[],
                extracted=True,
            )

        if schema == ItemizedBillData:
            return ItemizedBillData(
                bill_number="BILL-2025-789456",
                bill_date="February 1, 2025",
                bill_items=[
                    BillItem(
                        item_description="Room Charges - Semi-Private (5 days)",
                        quantity=Decimal("5"),
                        unit_price=Decimal("200.00"),
                        amount=Decimal("1000.00"),
                        service_date="01/20/25",
                    ),
                    BillItem(
                        item_description="Admission Fee",
                        quantity=Decimal("1"),
                        unit_price=Decimal("150.00"),
                        amount=Decimal("150.00"),
                        service_date="01/20/25",
                    ),
                ],
                stated_subtotal=Decimal("1150.00"),
                stated_tax=Decimal("57.50"),
                stated_total=Decimal("1207.50"),
                calculated_subtotal=Decimal("1150.00"),
                calculated_total=Decimal("1207.50"),
                discrepancy_detected=False,
                discrepancy_details=None,
                source_pages=[],
                extracted=True,
            )

        raise ValueError(f"Unhandled schema in MockLLMService: {schema}")


@pytest.fixture
def mock_llm_service(monkeypatch):
    """Provides an instance of MockLLMService and patches get_llm_service globally."""
    svc = MockLLMService()
    import app.services.llm_service as llm_mod
    monkeypatch.setattr(llm_mod, "_llm_service", svc)
    monkeypatch.setattr(llm_mod, "get_llm_service", lambda: svc)
    return svc
