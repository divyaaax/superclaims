"""LLM Service Module

Provides an interface for invoking LLM models using LangChain ChatOpenAI
with structured Pydantic outputs, configuration validation, and error handling.
"""

import logging
from typing import Any, List, Optional, Type, TypeVar
from pydantic import BaseModel
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class LLMConfigurationError(Exception):
    """Raised when LLM invocation is attempted without valid credentials or configuration."""
    pass


class LLMService:
    """Service wrapper around LangChain ChatOpenAI for structured generation."""

    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self._llm: Optional[ChatOpenAI] = None

    def is_configured(self) -> bool:
        """Check if LLM credentials are configured or mock mode is enabled."""
        if self.settings.use_mock_llm:
            return True
        return bool(self.settings.openai_api_key and self.settings.openai_api_key.strip())

    def get_llm(self) -> ChatOpenAI:
        """Get or initialize the ChatOpenAI client.

        Raises:
            LLMConfigurationError: If no API key is configured and mock mode is off.
        """
        if not self.is_configured():
            raise LLMConfigurationError(
                "OpenAI API Key is not configured. Please set the OPENAI_API_KEY environment variable "
                "or specify it in a .env file."
            )

        if self._llm is None:
            kwargs = {
                "model": self.settings.llm_model,
                "temperature": self.settings.llm_temperature,
                "api_key": self.settings.openai_api_key or "mock-key",
            }
            if self.settings.openai_base_url:
                kwargs["base_url"] = self.settings.openai_base_url

            self._llm = ChatOpenAI(**kwargs)

        return self._llm

    def invoke_structured(
        self,
        messages: List[BaseMessage],
        schema: Type[T],
    ) -> T:
        """Invoke LLM with a list of messages and enforce structured Pydantic output.

        Args:
            messages: List of SystemMessage, HumanMessage, etc.
            schema: Pydantic model class defining the expected output.

        Returns:
            An instance of schema (Type[T]) populated with validated LLM outputs.

        Raises:
            LLMConfigurationError: If the API key is missing.
            Exception: If invocation or schema validation fails.
        """
        if self.settings.use_mock_llm:
            return self._mock_resolve(messages, schema)

        llm = self.get_llm()
        structured_llm = llm.with_structured_output(schema)

        try:
            logger.debug("Invoking LLM structured output for schema %s", schema.__name__)
            result = structured_llm.invoke(messages)
            if not isinstance(result, schema):
                result = schema.model_validate(result)
            return result
        except LLMConfigurationError:
            raise
        except Exception as e:
            logger.error("LLM structured output invocation failed: %s", str(e))
            raise

    def _mock_resolve(self, messages: List[BaseMessage], schema: Type[T]) -> T:
        """Deterministic fallback resolver used only when USE_MOCK_LLM=true."""
        from decimal import Decimal
        from app.schemas import (
            BatchClassificationResponse,
            BillItem,
            DischargeSummaryData,
            DocumentType,
            IdentityData,
            ItemizedBillData,
            PageClassification,
        )

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
                        reasoning=f"Identified document type '{doc_type.value}' based on header and keywords.",
                    )
                )
            return BatchClassificationResponse(classifications=classifications)  # type: ignore

        if schema == IdentityData:
            return IdentityData(  # type: ignore
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
            return DischargeSummaryData(  # type: ignore
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
            return ItemizedBillData(  # type: ignore
                bill_number="BILL-2025-789456",
                bill_date="February 1, 2025",
                bill_items=[
                    BillItem(item_description="Room Charges - Semi-Private (5 days)", quantity=Decimal("5"), unit_price=Decimal("200.00"), amount=Decimal("1000.00"), service_date="01/20/25"),
                    BillItem(item_description="Admission Fee", quantity=Decimal("1"), unit_price=Decimal("150.00"), amount=Decimal("150.00"), service_date="01/20/25"),
                    BillItem(item_description="Emergency Room Services", quantity=Decimal("1"), unit_price=Decimal("500.00"), amount=Decimal("500.00"), service_date="01/20/25"),
                    BillItem(item_description="Physician Consultation - Dr. Sarah Johnson", quantity=Decimal("5"), unit_price=Decimal("150.00"), amount=Decimal("750.00"), service_date="01/20/25"),
                    BillItem(item_description="Chest X-Ray", quantity=Decimal("2"), unit_price=Decimal("120.00"), amount=Decimal("240.00"), service_date="01/20/25"),
                    BillItem(item_description="CT Scan - Chest", quantity=Decimal("1"), unit_price=Decimal("800.00"), amount=Decimal("800.00"), service_date="01/21/25"),
                    BillItem(item_description="Complete Blood Count (CBC)", quantity=Decimal("3"), unit_price=Decimal("45.00"), amount=Decimal("135.00"), service_date="01/20/25"),
                    BillItem(item_description="Blood Culture Test", quantity=Decimal("2"), unit_price=Decimal("80.00"), amount=Decimal("160.00"), service_date="01/21/25"),
                    BillItem(item_description="Arterial Blood Gas Analysis", quantity=Decimal("1"), unit_price=Decimal("95.00"), amount=Decimal("95.00"), service_date="01/22/25"),
                    BillItem(item_description="IV Fluids - Normal Saline", quantity=Decimal("10"), unit_price=Decimal("25.00"), amount=Decimal("250.00"), service_date="01/20/25"),
                    BillItem(item_description="Injection - Ceftriaxone 1g", quantity=Decimal("5"), unit_price=Decimal("30.00"), amount=Decimal("150.00"), service_date="01/20/25"),
                    BillItem(item_description="Injection - Paracetamol", quantity=Decimal("6"), unit_price=Decimal("8.00"), amount=Decimal("48.00"), service_date="01/21/25"),
                    BillItem(item_description="Nebulization Treatment", quantity=Decimal("4"), unit_price=Decimal("35.00"), amount=Decimal("140.00"), service_date="01/22/25"),
                    BillItem(item_description="Oxygen Therapy (per hour)", quantity=Decimal("48"), unit_price=Decimal("5.00"), amount=Decimal("240.00"), service_date="01/20/25"),
                    BillItem(item_description="Nursing Care (per day)", quantity=Decimal("5"), unit_price=Decimal("100.00"), amount=Decimal("500.00"), service_date="01/20/25"),
                    BillItem(item_description="ICU Monitoring Equipment", quantity=Decimal("2"), unit_price=Decimal("200.00"), amount=Decimal("400.00"), service_date="01/20/25"),
                    BillItem(item_description="Physiotherapy Session", quantity=Decimal("3"), unit_price=Decimal("60.00"), amount=Decimal("180.00"), service_date="01/23/25"),
                    BillItem(item_description="Medical Supplies & Consumables", quantity=Decimal("1"), unit_price=Decimal("250.00"), amount=Decimal("250.00"), service_date="01/20/25"),
                    BillItem(item_description="Laboratory Processing Fee", quantity=Decimal("1"), unit_price=Decimal("75.00"), amount=Decimal("75.00"), service_date="01/20/25"),
                    BillItem(item_description="Pharmacy Dispensing Fee", quantity=Decimal("1"), unit_price=Decimal("50.00"), amount=Decimal("50.00"), service_date="01/20/25"),
                ],
                stated_subtotal=Decimal("6113.00"),
                stated_tax=Decimal("305.65"),
                stated_total=Decimal("6418.65"),
                calculated_subtotal=Decimal("6113.00"),
                calculated_total=Decimal("6418.65"),
                discrepancy_detected=False,
                discrepancy_details=None,
                source_pages=[],
                extracted=True,
            )

        raise ValueError(f"Unsupported schema in mock resolver: {schema}")


# Singleton instance
_llm_service: Optional[LLMService] = None


def get_llm_service() -> LLMService:
    """Return singleton LLMService instance."""
    global _llm_service
    if _llm_service is None:
        _llm_service = LLMService()
    return _llm_service
