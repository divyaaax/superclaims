"""Itemized Bill Agent for extracting charges and validating monetary calculations."""

from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.pdf_processor import PageContent
from app.schemas import BillItem, ItemizedBillData
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a medical billing and healthcare accounting specialist.
Your task is to extract all line-item charges and stated financial totals from itemized hospital bill pages.

EXTRACT THE FOLLOWING FIELDS:
1. bill_number: The bill or invoice identifier (e.g., "BILL-2025-789456").
2. bill_date: Billing date stated on the document.
3. bill_items: A list of every single line item charge, where each item has:
   - item_description: The name or description of the charge/service.
   - quantity: The numerical quantity (e.g. 5, 1, 10).
   - unit_price: The rate per unit as a decimal (e.g. 200.00, 150.00).
   - amount: The line-item total charge as a decimal (e.g. 1000.00, 150.00).
   - service_date: Date service was rendered if provided.
4. stated_subtotal: The subtotal amount explicitly stated on the bill.
5. stated_tax: The tax amount explicitly stated on the bill.
6. stated_total: The final total amount explicitly stated on the bill.

CRITICAL RULES:
- Extract all monetary figures precisely as stated on the document.
- Do NOT alter or calculate your own total inside stated_total; write down what the document states.
- If quantity or unit_price is not provided for a specific line item, set it to null.
- Extract ONLY from itemized hospital bill pages (do not confuse with pharmacy receipts or cash receipts).
"""

TWO_PLACES = Decimal("0.01")


class ItemizedBillAgent:
    """Agent for extracting itemized charges and reconciling totals."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or get_llm_service()

    def extract(self, relevant_pages: List[PageContent]) -> ItemizedBillData:
        """Extract billing items and perform decimal arithmetic verification."""
        source_page_nums = [p.page_number for p in relevant_pages]

        if not relevant_pages:
            logger.info("Bill Agent: No itemized_bill pages provided. Returning empty result.")
            return ItemizedBillData(
                bill_number=None,
                bill_date=None,
                bill_items=[],
                stated_subtotal=None,
                stated_tax=None,
                stated_total=None,
                calculated_subtotal=None,
                calculated_total=None,
                discrepancy_detected=False,
                discrepancy_details=None,
                source_pages=[],
                extracted=False,
            )

        logger.info("Bill Agent: Processing pages %s for billing extraction.", source_page_nums)

        pages_text = "\n\n".join(
            [f"--- ITEMIZED BILL PAGE {p.page_number} ---\n{p.text}" for p in relevant_pages]
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Please extract the itemized bill charges and stated totals from the following page(s):\n\n{pages_text}"
            ),
        ]

        try:
            raw_data: ItemizedBillData = self.llm_service.invoke_structured(
                messages=messages,
                schema=ItemizedBillData,
            )

            reconciled_data = self._reconcile_finances(raw_data, source_page_nums)
            logger.info(
                "Bill Agent: Extracted %d line items. Discrepancy detected: %s",
                len(reconciled_data.bill_items),
                reconciled_data.discrepancy_detected,
            )
            return reconciled_data

        except Exception as e:
            logger.error("Bill Agent failed extraction: %s", str(e))
            return ItemizedBillData(
                bill_number=None,
                bill_date=None,
                bill_items=[],
                stated_subtotal=None,
                stated_tax=None,
                stated_total=None,
                calculated_subtotal=None,
                calculated_total=None,
                discrepancy_detected=False,
                discrepancy_details=f"Extraction failed: {str(e)}",
                source_pages=source_page_nums,
                extracted=False,
            )

    @classmethod
    def _reconcile_finances(cls, data: ItemizedBillData, source_pages: List[int]) -> ItemizedBillData:
        """Calculate line-item sums using Decimal arithmetic and check for discrepancies."""
        items = data.bill_items or []
        
        if items:
            calc_subtotal = sum(
                (Decimal(str(item.amount)) for item in items),
                Decimal("0.00"),
            ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        else:
            calc_subtotal = Decimal("0.00") if data.stated_subtotal is not None else None

        tax = Decimal(str(data.stated_tax)) if data.stated_tax is not None else Decimal("0.00")
        calc_total = (calc_subtotal + tax).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if calc_subtotal is not None else None

        discrepancy_detected = False
        discrepancy_details = None

        if data.stated_total is not None and calc_total is not None:
            stated = Decimal(str(data.stated_total)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            diff = abs(calc_total - stated)
            # Allow up to 0.02 tolerance for penny rounding across multiple line items
            if diff > Decimal("0.02"):
                discrepancy_detected = True
                discrepancy_details = (
                    f"Calculation discrepancy: Stated total is {stated}, but calculated total from line items is "
                    f"{calc_total} (calculated subtotal {calc_subtotal} + stated tax {tax}). "
                    f"Variance: {diff}."
                )
        elif data.stated_subtotal is not None and calc_subtotal is not None:
            stated_sub = Decimal(str(data.stated_subtotal)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
            diff = abs(calc_subtotal - stated_sub)
            if diff > Decimal("0.02"):
                discrepancy_detected = True
                discrepancy_details = (
                    f"Calculation discrepancy: Stated subtotal is {stated_sub}, but calculated subtotal is "
                    f"{calc_subtotal}. Variance: {diff}."
                )

        return ItemizedBillData(
            bill_number=data.bill_number,
            bill_date=data.bill_date,
            bill_items=items,
            stated_subtotal=Decimal(str(data.stated_subtotal)) if data.stated_subtotal is not None else None,
            stated_tax=Decimal(str(data.stated_tax)) if data.stated_tax is not None else None,
            stated_total=Decimal(str(data.stated_total)) if data.stated_total is not None else None,
            calculated_subtotal=calc_subtotal,
            calculated_total=calc_total,
            discrepancy_detected=discrepancy_detected,
            discrepancy_details=discrepancy_details,
            source_pages=source_pages,
            extracted=True,
        )
