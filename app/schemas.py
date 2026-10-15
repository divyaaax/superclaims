"""Pydantic Schemas for Claim Processing Pipeline.

Defines all structured data models for:
- Document segregation (9 exact categories)
- ID Agent extraction
- Discharge Summary Agent extraction
- Itemized Bill Agent extraction (with Decimal arithmetic)
- Aggregated final API responses
"""

from decimal import Decimal
from enum import Enum
from typing import Dict, List, Optional
from pydantic import BaseModel, Field, ConfigDict


class DocumentType(str, Enum):
    """The exact 9 document types required by the assignment specification."""
    CLAIM_FORMS = "claim_forms"
    CHEQUE_OR_BANK_DETAILS = "cheque_or_bank_details"
    IDENTITY_DOCUMENT = "identity_document"
    ITEMIZED_BILL = "itemized_bill"
    DISCHARGE_SUMMARY = "discharge_summary"
    PRESCRIPTION = "prescription"
    INVESTIGATION_REPORT = "investigation_report"
    CASH_RECEIPT = "cash_receipt"
    OTHER = "other"


class PageClassification(BaseModel):
    """Classification record for a single document page."""
    page_number: int = Field(..., description="1-indexed original page number")
    document_type: DocumentType = Field(..., description="Classified category from the 9 allowed types")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Confidence score 0.0-1.0")
    reasoning: Optional[str] = Field(default=None, description="Brief justification for classification")

    model_config = ConfigDict(use_enum_values=True)


class BatchClassificationResponse(BaseModel):
    """Pydantic model for LLM structured output classification."""
    classifications: List[PageClassification] = Field(
        ...,
        description="List of classifications for the supplied pages"
    )


class SegregationSummary(BaseModel):
    """Summary of PDF document segregation results."""
    total_pages: int = Field(..., ge=1, description="Total number of pages processed")
    categories: Dict[str, List[int]] = Field(
        default_factory=dict,
        description="Mapping of each DocumentType to list of 1-indexed page numbers"
    )
    page_classifications: List[PageClassification] = Field(
        default_factory=list,
        description="Ordered list of per-page classifications"
    )


class IdentityData(BaseModel):
    """Extracted data from identity_document pages (ID Agent)."""
    patient_name: Optional[str] = Field(default=None, description="Full name of the patient")
    date_of_birth: Optional[str] = Field(default=None, description="Date of birth as stated")
    id_numbers: Optional[Dict[str, Optional[str]]] = Field(
        default=None,
        description="Identification numbers, e.g. {'id_number': '...', 'id_type': '...'}"
    )
    policy_details: Optional[str] = Field(default=None, description="Insurance policy details if present on ID")
    gender: Optional[str] = Field(default=None, description="Gender if stated on ID")
    address: Optional[str] = Field(default=None, description="Residential address if stated on ID")
    source_pages: List[int] = Field(default_factory=list, description="Pages used for extraction")
    extracted: bool = Field(default=False, description="True if identity document was found and processed")


class DischargeSummaryData(BaseModel):
    """Extracted data from discharge_summary pages (Discharge Summary Agent)."""
    diagnosis: Optional[str] = Field(default=None, description="Primary/admission/discharge diagnosis")
    admission_date: Optional[str] = Field(default=None, description="Date of hospital admission")
    discharge_date: Optional[str] = Field(default=None, description="Date of hospital discharge")
    physician_details: Optional[Dict[str, Optional[str]]] = Field(
        default=None,
        description="Physician name and designation, e.g. {'name': '...', 'role': '...'}"
    )
    hospital_name: Optional[str] = Field(default=None, description="Hospital or clinic name")
    discharge_condition: Optional[str] = Field(default=None, description="Condition of patient at discharge")
    discharge_medications: Optional[List[str]] = Field(default=None, description="Prescribed discharge medications")
    source_pages: List[int] = Field(default_factory=list, description="Pages used for extraction")
    extracted: bool = Field(default=False, description="True if discharge summary was found and processed")


class BillItem(BaseModel):
    """Individual line item from an itemized hospital bill."""
    item_description: str = Field(..., description="Service or procedure description")
    quantity: Optional[Decimal] = Field(default=None, description="Quantity or units billed")
    unit_price: Optional[Decimal] = Field(default=None, description="Unit rate/price per unit")
    amount: Decimal = Field(..., description="Line-item total amount")
    service_date: Optional[str] = Field(default=None, description="Date of service if stated")


class ItemizedBillData(BaseModel):
    """Extracted data and financial validation from itemized_bill pages (Bill Agent)."""
    bill_number: Optional[str] = Field(default=None, description="Bill/Invoice number")
    bill_date: Optional[str] = Field(default=None, description="Billing date")
    bill_items: List[BillItem] = Field(default_factory=list, description="List of individual line items")
    stated_subtotal: Optional[Decimal] = Field(default=None, description="Subtotal stated on document")
    stated_tax: Optional[Decimal] = Field(default=None, description="Tax amount stated on document")
    stated_total: Optional[Decimal] = Field(default=None, description="Total amount stated on document")
    calculated_subtotal: Optional[Decimal] = Field(default=None, description="Sum of line-item amounts")
    calculated_total: Optional[Decimal] = Field(default=None, description="Calculated subtotal + tax")
    discrepancy_detected: bool = Field(default=False, description="True if calculated math differs from stated total")
    discrepancy_details: Optional[str] = Field(default=None, description="Explanation of calculation discrepancy if any")
    source_pages: List[int] = Field(default_factory=list, description="Pages used for extraction")
    extracted: bool = Field(default=False, description="True if itemized bill was found and processed")


class ExtractedData(BaseModel):
    """Container for the outputs of the three extraction agents."""
    identity_information: Optional[IdentityData] = Field(
        default=None,
        description="Extracted patient identity information"
    )
    discharge_summary: Optional[DischargeSummaryData] = Field(
        default=None,
        description="Extracted hospital discharge summary"
    )
    itemized_bill: Optional[ItemizedBillData] = Field(
        default=None,
        description="Extracted itemized bill items and financial reconciliation"
    )


class ClaimProcessingResponse(BaseModel):
    """Final JSON response for POST /api/process endpoint."""
    claim_id: str = Field(..., description="The unique claim identifier provided in the request")
    status: str = Field(..., description="Processing status: SUCCESS, PARTIAL_SUCCESS, or ERROR")
    processing_time_seconds: Optional[float] = Field(default=None, description="Total pipeline latency in seconds")
    segregation_results: SegregationSummary = Field(..., description="Page-by-page document classification")
    extracted_data: ExtractedData = Field(..., description="Structured extracted data from the 3 extraction agents")
    errors: List[str] = Field(default_factory=list, description="List of non-fatal warnings or error messages")


class HealthResponse(BaseModel):
    """Response model for GET /health endpoint."""
    status: str = "ok"
    service: str = "Claim Processing Pipeline"
    version: str = "1.0.0"
    llm_configured: bool = False
    llm_model: str = "gpt-4o-mini"
    use_mock_llm: bool = False
