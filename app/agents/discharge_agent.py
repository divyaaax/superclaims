"""Discharge Summary Agent Module

Extracts clinical discharge details from pages classified as discharge_summary.
Extracts:
- Diagnosis (primary, admission, or discharge diagnosis)
- Admission date
- Discharge date
- Physician details (attending physician name, designation, department)
- Hospital name and discharge condition when available.
Preserves original information and handles missing values cleanly.
"""

import logging
from typing import List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.pdf_processor import PageContent
from app.schemas import DischargeSummaryData
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a clinical documentation specialist.
Your task is to extract medical discharge summary details ONLY from the provided hospital discharge summary pages.

EXTRACT THE FOLLOWING FIELDS (if present):
1. diagnosis: Admission or primary clinical diagnosis (e.g. "Community Acquired Pneumonia (CAP)").
2. admission_date: Stated hospital admission date.
3. discharge_date: Stated hospital discharge date.
4. physician_details: Dictionary containing attending/primary physician information, e.g. {"name": "Dr. Sarah Johnson, MD", "title": "Attending Physician"}.
5. hospital_name: Name of the medical institution or hospital.
6. discharge_condition: Clinical condition of patient at discharge (e.g., "Stable, improved").
7. discharge_medications: List of medications prescribed upon discharge.

CRITICAL RULES:
- Extract ONLY what is explicitly stated in the provided text.
- Do NOT guess or invent missing values. If a field is not present, return null.
- Handle missing values gracefully.
"""


class DischargeSummaryAgent:
    """Agent that processes ONLY pages classified as discharge_summary."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or get_llm_service()

    def extract(self, relevant_pages: List[PageContent]) -> DischargeSummaryData:
        """Extract discharge summary details from relevant pages.

        Args:
            relevant_pages: Pages categorized strictly as discharge_summary.

        Returns:
            DischargeSummaryData containing extracted fields or clean null defaults if no pages.
        """
        source_page_nums = [p.page_number for p in relevant_pages]

        if not relevant_pages:
            logger.info("Discharge Summary Agent: No discharge_summary pages provided. Returning empty result.")
            return DischargeSummaryData(
                diagnosis=None,
                admission_date=None,
                discharge_date=None,
                physician_details=None,
                hospital_name=None,
                discharge_condition=None,
                discharge_medications=None,
                source_pages=[],
                extracted=False,
            )

        logger.info("Discharge Summary Agent: Processing pages %s for clinical extraction.", source_page_nums)

        pages_text = "\n\n".join(
            [f"--- DISCHARGE SUMMARY PAGE {p.page_number} ---\n{p.text}" for p in relevant_pages]
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Please extract the discharge summary details from the following page(s):\n\n{pages_text}"
            ),
        ]

        try:
            data: DischargeSummaryData = self.llm_service.invoke_structured(
                messages=messages,
                schema=DischargeSummaryData,
            )
            data.source_pages = source_page_nums
            data.extracted = True
            logger.info("Discharge Summary Agent: Successfully extracted clinical summary.")
            return data

        except Exception as e:
            logger.error("Discharge Summary Agent failed extraction: %s", str(e))
            return DischargeSummaryData(
                diagnosis=None,
                admission_date=None,
                discharge_date=None,
                physician_details=None,
                hospital_name=None,
                discharge_condition=None,
                discharge_medications=None,
                source_pages=source_page_nums,
                extracted=False,
            )
