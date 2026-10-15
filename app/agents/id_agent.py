"""ID Agent Module

Extracts patient identity information from pages classified as identity_document.
Extracts:
- Patient name
- Date of birth
- Identification numbers (ID number, ID type)
- Policy details (if present on the ID card)
- Additional stated demographics (gender, address)
Preserves missing fields as None/null without inventing information.
"""

import logging
from typing import List, Optional
from langchain_core.messages import HumanMessage, SystemMessage

from app.pdf_processor import PageContent
from app.schemas import IdentityData
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a medical claims data extraction specialist specializing in identity documents.
Your task is to extract identity information ONLY from the provided identity document pages.

EXTRACT THE FOLLOWING FIELDS (if present):
1. patient_name: The full legal name of the person shown on the ID.
2. date_of_birth: Date of birth as written on the document.
3. id_numbers: A dictionary containing the ID number(s) and type, e.g. {"id_number": "...", "id_type": "Driver License / Government ID"}.
4. policy_details: Any insurance policy number or coverage details explicitly shown on this ID (null if not present).
5. gender: Stated gender/sex (null if not present).
6. address: Residential address as shown on the document (null if not present).

CRITICAL RULES:
- Extract ONLY what is explicitly written on the provided pages.
- NEVER fabricate or assume missing values. If a field is not present, set it to null.
- Do not pull or invent data from outside the provided text.
"""


class IDAgent:
    """Agent that processes ONLY pages classified as identity_document."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or get_llm_service()

    def extract(self, relevant_pages: List[PageContent]) -> IdentityData:
        """Extract identity details from relevant pages.

        Args:
            relevant_pages: Pages categorized strictly as identity_document.

        Returns:
            IdentityData containing extracted fields or clean null defaults if no pages.
        """
        source_page_nums = [p.page_number for p in relevant_pages]

        if not relevant_pages:
            logger.info("ID Agent: No identity_document pages provided. Returning empty result.")
            return IdentityData(
                patient_name=None,
                date_of_birth=None,
                id_numbers=None,
                policy_details=None,
                gender=None,
                address=None,
                source_pages=[],
                extracted=False,
            )

        logger.info("ID Agent: Processing pages %s for identity extraction.", source_page_nums)

        pages_text = "\n\n".join(
            [f"--- IDENTITY DOCUMENT PAGE {p.page_number} ---\n{p.text}" for p in relevant_pages]
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(
                content=f"Please extract the patient identity details from the following page(s):\n\n{pages_text}"
            ),
        ]

        try:
            data: IdentityData = self.llm_service.invoke_structured(
                messages=messages,
                schema=IdentityData,
            )
            data.source_pages = source_page_nums
            data.extracted = True
            logger.info("ID Agent: Successfully extracted identity information.")
            return data

        except Exception as e:
            logger.error("ID Agent failed extraction: %s", str(e))
            # Safe non-fabricated fallback
            return IdentityData(
                patient_name=None,
                date_of_birth=None,
                id_numbers=None,
                policy_details=None,
                gender=None,
                address=None,
                source_pages=source_page_nums,
                extracted=False,
            )
