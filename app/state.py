"""Graph State Definition for Claim Processing Workflow."""

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

    # Input attributes
    claim_id: str
    pages: List[PageContent]

    # Intermediate agent outputs
    segregation_summary: Optional[SegregationSummary]
    identity_data: Optional[IdentityData]
    discharge_data: Optional[DischargeSummaryData]
    bill_data: Optional[ItemizedBillData]

    # Pipeline diagnostics and errors (uses operator.add reducer for parallel fan-out updates)
    errors: Annotated[List[str], operator.add]
    start_time: float

    # Final combined response
    final_response: Optional[ClaimProcessingResponse]
