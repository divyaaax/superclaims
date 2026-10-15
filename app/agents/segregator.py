"""Segregator Agent Module

Analyzes PDF page contents and classifies each page into exactly one of
the 9 required document categories:
- claim_forms
- cheque_or_bank_details
- identity_document
- itemized_bill
- discharge_summary
- prescription
- investigation_report
- cash_receipt
- other
"""

import logging
from typing import Dict, List, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import HumanMessage, SystemMessage

from app.config import get_settings
from app.pdf_processor import PageContent
from app.schemas import BatchClassificationResponse, DocumentType, PageClassification, SegregationSummary
from app.services.llm_service import LLMService, get_llm_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert medical insurance document segregation specialist.
Your task is to classify document pages from a medical claim package into EXACTLY ONE of the following 9 categories:

1. claim_forms: Insurance claim application, claim reimbursement forms, or formal claim submission forms.
2. cheque_or_bank_details: Bank cheques, cancelled cheques, bank statements, IFSC/routing details, or direct deposit forms.
3. identity_document: Government-issued IDs, driver's licenses, passports, national ID cards, DMV identity cards.
4. itemized_bill: Itemized hospital/clinical bills detailing item-by-item medical charges, room charges, procedures, tests, and costs. (Note: Do not confuse with pharmacy receipts or cash receipts).
5. discharge_summary: Hospital discharge summaries, clinical summaries, admission/discharge clinical reports with diagnosis and hospital course.
6. prescription: Doctor's medication orders/prescriptions detailing drugs, dosages, frequencies, and directions.
7. investigation_report: Diagnostic laboratory reports, pathology reports, complete blood count, metabolic panels, radiology/imaging results.
8. cash_receipt: Payment receipts, cash memos, cashier transaction slips showing payment received.
9. other: Administrative documents, consent forms, appointment letters, blank questionnaires, referrals, or documents that do not belong to the other 8 categories.

RULES:
- You must ONLY use the exact 9 category identifiers listed above. Do not invent any new categories.
- Assign each page number exactly one classification with a confidence score (0.0 to 1.0) and a brief reasoning.
- If a page has multiple sections or is ambiguous, choose the predominant category or 'other' if uncertain.
- Do NOT guess missing content; classify based strictly on the text provided for each page.
"""


class SegregatorAgent:
    """Agent responsible for classifying pages of a claim PDF into 9 distinct categories."""

    def __init__(self, llm_service: Optional[LLMService] = None):
        self.llm_service = llm_service or get_llm_service()
        self.settings = get_settings()

    def classify_pages(self, pages: List[PageContent]) -> SegregationSummary:
        """Classify all pages in the PDF document.

        Args:
            pages: List of PageContent extracted from PDF.

        Returns:
            SegregationSummary containing page-by-page classification and category mapping.
        """
        if not pages:
            logger.warning("No pages provided for segregation.")
            return SegregationSummary(total_pages=0, categories={}, page_classifications=[])

        all_classifications: List[PageClassification] = []
        batch_size = max(1, self.settings.batch_size)

        # Separate pages into empty/low-text vs text-containing pages
        pages_to_classify: List[PageContent] = []
        for page in pages:
            if not page.has_extractable_text or page.is_blank:
                logger.info("Page %d has little or no text. Classifying as 'other'.", page.page_number)
                all_classifications.append(
                    PageClassification(
                        page_number=page.page_number,
                        document_type=DocumentType.OTHER,
                        confidence=1.0,
                        reasoning="Page contains little or no extractable text.",
                    )
                )
            else:
                pages_to_classify.append(page)

        # Process text-containing pages in batches to support large PDFs reliably
        for i in range(0, len(pages_to_classify), batch_size):
            batch = pages_to_classify[i : i + batch_size]
            batch_classifications = self._classify_batch(batch)
            all_classifications.extend(batch_classifications)

        # Sort classifications by page number to preserve original page order
        all_classifications.sort(key=lambda c: c.page_number)

        # Build category -> page numbers mapping
        categories_map: Dict[str, List[int]] = {doc_type.value: [] for doc_type in DocumentType}
        for item in all_classifications:
            doc_type_val = (
                item.document_type.value
                if isinstance(item.document_type, DocumentType)
                else str(item.document_type)
            )
            if doc_type_val in categories_map:
                categories_map[doc_type_val].append(item.page_number)
            else:
                categories_map[DocumentType.OTHER.value].append(item.page_number)

        summary = SegregationSummary(
            total_pages=len(pages),
            categories=categories_map,
            page_classifications=all_classifications,
        )

        logger.info(
            "Segregation complete for %d pages. Categorized: %s",
            len(pages),
            {k: v for k, v in categories_map.items() if v},
        )
        return summary

    def _classify_batch(self, batch: List[PageContent]) -> List[PageClassification]:
        """Classify a batch of pages using the LLM with structured output."""
        pages_text_blocks = []
        for p in batch:
            # Truncate exceedingly long text if needed to prevent token limits
            sample_text = p.text[:3000]
            pages_text_blocks.append(
                f"--- START PAGE {p.page_number} ---\n{sample_text}\n--- END PAGE {p.page_number} ---"
            )

        content_prompt = (
            f"Please classify the following {len(batch)} pages into the 9 allowed document types.\n\n"
            + "\n\n".join(pages_text_blocks)
        )

        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=content_prompt),
        ]

        try:
            response: BatchClassificationResponse = self.llm_service.invoke_structured(
                messages=messages,
                schema=BatchClassificationResponse,
            )

            # Ensure every page in this batch has a corresponding classification
            classified_map = {c.page_number: c for c in response.classifications}
            results: List[PageClassification] = []

            for p in batch:
                if p.page_number in classified_map:
                    results.append(classified_map[p.page_number])
                else:
                    logger.warning("Page %d missing from LLM response. Defaulting to 'other'.", p.page_number)
                    results.append(
                        PageClassification(
                            page_number=p.page_number,
                            document_type=DocumentType.OTHER,
                            confidence=0.5,
                            reasoning="Page omitted by classifier, defaulted to other.",
                        )
                    )
            return results

        except Exception as e:
            logger.error("Error classifying batch of pages %s: %s", [p.page_number for p in batch], str(e))
            # Safe fallback for the batch without crashing the entire pipeline
            return [
                PageClassification(
                    page_number=p.page_number,
                    document_type=DocumentType.OTHER,
                    confidence=0.0,
                    reasoning=f"Classification failed due to error: {str(e)}",
                )
                for p in batch
            ]
