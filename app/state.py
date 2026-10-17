"""Graph state definition for claim processing pipeline."""

import operator
from typing import Annotated, Any, Dict, List, Optional, TypedDict
from app.pdf_processor import PageContent
from app.schemas import (
    ClaimProcessingResponse,
    DischargeSummaryData,
    IdentityData,
    ItemizedBillData,
    SegregationSummary,
)


class ClaimState(TypedDict, total=False):
    """Shared state passed between LangGraph nodes during claim processing."""

    claim_id: str
    pages: List[PageContent]

    segregation_summary: Optional[SegregationSummary]
    identity_data: Optional[IdentityData]
    discharge_data: Optional[DischargeSummaryData]
    bill_data: Optional[ItemizedBillData]

    errors: Annotated[List[str], operator.add]
    start_time: float

    final_response: Optional[ClaimProcessingResponse]
