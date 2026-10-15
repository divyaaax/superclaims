"""Tests for Individual Agent Logic and Arithmetic Validation."""

from decimal import Decimal
from unittest.mock import MagicMock
from app.agents.bill_agent import ItemizedBillAgent
from app.agents.discharge_agent import DischargeSummaryAgent
from app.agents.id_agent import IDAgent
from app.agents.segregator import SegregatorAgent
from app.pdf_processor import PageContent
from app.schemas import BillItem, DocumentType, ItemizedBillData


def test_segregator_with_mock_llm(mock_llm_service, mock_pages):
    """Test Segregator Agent correctly maps pages to the 9 categories."""
    segregator = SegregatorAgent(llm_service=mock_llm_service)
    summary = segregator.classify_pages(mock_pages)

    assert summary.total_pages == 4
    assert len(summary.page_classifications) == 4

    # Verify category mappings
    assert 1 in summary.categories[DocumentType.CLAIM_FORMS.value]
    assert 3 in summary.categories[DocumentType.IDENTITY_DOCUMENT.value]
    assert 4 in summary.categories[DocumentType.DISCHARGE_SUMMARY.value]
    assert 9 in summary.categories[DocumentType.ITEMIZED_BILL.value]


def test_segregator_blank_page_handling(mock_llm_service):
    """Test Segregator immediately assigns 'other' to blank/low-text pages."""
    blank_page = PageContent(
        page_number=1,
        text="   ",
        char_count=0,
        has_extractable_text=False,
        is_blank=True,
    )
    segregator = SegregatorAgent(llm_service=mock_llm_service)
    summary = segregator.classify_pages([blank_page])

    assert summary.total_pages == 1
    assert summary.page_classifications[0].document_type == DocumentType.OTHER
    assert 1 in summary.categories[DocumentType.OTHER.value]


def test_id_agent_normal_extraction(mock_llm_service, mock_pages):
    """Test ID Agent extracts identity details from relevant pages."""
    id_page = [p for p in mock_pages if p.page_number == 3]
    agent = IDAgent(llm_service=mock_llm_service)
    data = agent.extract(id_page)

    assert data.extracted is True
    assert data.patient_name == "JOHN MICHAEL SMITH"
    assert data.date_of_birth == "15-MAR-1985"
    assert data.id_numbers["id_number"] == "ID-987-654-321"
    assert data.policy_details is None  # Missing field is preserved as None
    assert data.source_pages == [3]


def test_id_agent_empty_pages(mock_llm_service):
    """Test ID Agent returns clean nulls when no identity pages exist."""
    agent = IDAgent(llm_service=mock_llm_service)
    data = agent.extract([])

    assert data.extracted is False
    assert data.patient_name is None
    assert data.source_pages == []


def test_discharge_agent_normal_extraction(mock_llm_service, mock_pages):
    """Test Discharge Summary Agent extracts diagnosis and dates."""
    discharge_page = [p for p in mock_pages if p.page_number == 4]
    agent = DischargeSummaryAgent(llm_service=mock_llm_service)
    data = agent.extract(discharge_page)

    assert data.extracted is True
    assert "Pneumonia" in data.diagnosis
    assert data.admission_date == "January 20, 2025"
    assert data.discharge_date == "January 25, 2025"
    assert data.physician_details["name"] == "Dr. Sarah Johnson, MD"
    assert data.source_pages == [4]


def test_discharge_agent_empty_pages(mock_llm_service):
    """Test Discharge Summary Agent handles absence of discharge summary pages."""
    agent = DischargeSummaryAgent(llm_service=mock_llm_service)
    data = agent.extract([])

    assert data.extracted is False
    assert data.diagnosis is None
    assert data.source_pages == []


def test_itemized_bill_reconciliation_exact_match(mock_llm_service):
    """Test Itemized Bill Agent validates math when calculation matches stated total."""
    agent = ItemizedBillAgent(llm_service=mock_llm_service)
    bill_data = ItemizedBillData(
        bill_number="BILL-100",
        bill_items=[
            BillItem(item_description="Room", quantity=Decimal("5"), unit_price=Decimal("200.00"), amount=Decimal("1000.00")),
            BillItem(item_description="Lab", quantity=Decimal("1"), unit_price=Decimal("150.00"), amount=Decimal("150.00")),
        ],
        stated_subtotal=Decimal("1150.00"),
        stated_tax=Decimal("57.50"),
        stated_total=Decimal("1207.50"),
    )
    reconciled = agent._reconcile_finances(bill_data, source_pages=[9])

    assert reconciled.calculated_subtotal == Decimal("1150.00")
    assert reconciled.calculated_total == Decimal("1207.50")
    assert reconciled.stated_total == Decimal("1207.50")
    assert reconciled.discrepancy_detected is False
    assert reconciled.discrepancy_details is None


def test_itemized_bill_discrepancy_detection(mock_llm_service):
    """Test Itemized Bill Agent flags discrepancies without replacing stated total."""
    agent = ItemizedBillAgent(llm_service=mock_llm_service)
    # Stated total is $1500.00, but line items only sum to $1150 + $57.50 = $1207.50
    bill_data = ItemizedBillData(
        bill_number="BILL-DISCREPANT",
        bill_items=[
            BillItem(item_description="Room", amount=Decimal("1000.00")),
            BillItem(item_description="Lab", amount=Decimal("150.00")),
        ],
        stated_subtotal=Decimal("1150.00"),
        stated_tax=Decimal("57.50"),
        stated_total=Decimal("1500.00"),  # Deliberate disagreement
    )
    reconciled = agent._reconcile_finances(bill_data, source_pages=[9])

    assert reconciled.stated_total == Decimal("1500.00")  # Never silently replaced!
    assert reconciled.calculated_total == Decimal("1207.50")
    assert reconciled.discrepancy_detected is True
    assert "Calculation discrepancy" in reconciled.discrepancy_details
    assert "1500.00" in reconciled.discrepancy_details
    assert "1207.50" in reconciled.discrepancy_details


def test_itemized_bill_empty_pages(mock_llm_service):
    """Test Itemized Bill Agent handles absence of bill pages."""
    agent = ItemizedBillAgent(llm_service=mock_llm_service)
    data = agent.extract([])

    assert data.extracted is False
    assert data.bill_items == []
    assert data.stated_total is None
    assert data.source_pages == []
