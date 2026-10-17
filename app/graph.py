"""LangGraph workflow for claim document segregation and extraction."""

import logging
import time
from typing import Any, Dict, List, Optional
from langgraph.graph import END, START, StateGraph

from app.agents.bill_agent import ItemizedBillAgent
from app.agents.discharge_agent import DischargeSummaryAgent
from app.agents.id_agent import IDAgent
from app.agents.segregator import SegregatorAgent
from app.pdf_processor import PageContent
from app.schemas import (
    ClaimProcessingResponse,
    DocumentType,
    ExtractedData,
    SegregationSummary,
)
from app.services.llm_service import get_llm_service
from app.state import ClaimState

logger = logging.getLogger(__name__)


def segregator_node(state: ClaimState) -> Dict[str, Any]:
    """Classify pages into document categories."""
    logger.info("Executing Segregator Node for claim_id=%s", state.get("claim_id"))
    llm_svc = get_llm_service()
    segregator = SegregatorAgent(llm_service=llm_svc)
    pages = state.get("pages", [])

    try:
        summary = segregator.classify_pages(pages)
        return {"segregation_summary": summary}
    except Exception as e:
        logger.error("Segregator node encountered error: %s", str(e))
        empty_summary = SegregationSummary(
            total_pages=len(pages),
            categories={doc_type.value: [] for doc_type in DocumentType},
            page_classifications=[],
        )
        return {
            "segregation_summary": empty_summary,
            "errors": [f"Segregator error: {str(e)}"],
        }


def id_agent_node(state: ClaimState) -> Dict[str, Any]:
    """Extract patient identity from ID pages."""
    logger.info("Executing ID Agent Node for claim_id=%s", state.get("claim_id"))
    llm_svc = get_llm_service()
    id_agent = IDAgent(llm_service=llm_svc)
    pages = state.get("pages", [])
    segregation = state.get("segregation_summary")

    relevant_page_nums = []
    if segregation and segregation.categories:
        relevant_page_nums = segregation.categories.get(DocumentType.IDENTITY_DOCUMENT.value, [])

    relevant_pages = [p for p in pages if p.page_number in relevant_page_nums]
    logger.info("ID Agent received %d relevant pages: %s", len(relevant_pages), relevant_page_nums)

    try:
        id_data = id_agent.extract(relevant_pages)
        return {"identity_data": id_data}
    except Exception as e:
        logger.error("ID agent node encountered error: %s", str(e))
        return {"errors": [f"ID Agent error: {str(e)}"]}


def discharge_agent_node(state: ClaimState) -> Dict[str, Any]:
    """Extract clinical details from discharge summary pages."""
    logger.info("Executing Discharge Summary Agent Node for claim_id=%s", state.get("claim_id"))
    llm_svc = get_llm_service()
    discharge_agent = DischargeSummaryAgent(llm_service=llm_svc)
    pages = state.get("pages", [])
    segregation = state.get("segregation_summary")

    relevant_page_nums = []
    if segregation and segregation.categories:
        relevant_page_nums = segregation.categories.get(DocumentType.DISCHARGE_SUMMARY.value, [])

    relevant_pages = [p for p in pages if p.page_number in relevant_page_nums]
    logger.info("Discharge Summary Agent received %d relevant pages: %s", len(relevant_pages), relevant_page_nums)

    try:
        discharge_data = discharge_agent.extract(relevant_pages)
        return {"discharge_data": discharge_data}
    except Exception as e:
        logger.error("Discharge Summary agent node encountered error: %s", str(e))
        return {"errors": [f"Discharge Agent error: {str(e)}"]}


def bill_agent_node(state: ClaimState) -> Dict[str, Any]:
    """Extract billing items and reconcile arithmetic."""
    logger.info("Executing Itemized Bill Agent Node for claim_id=%s", state.get("claim_id"))
    llm_svc = get_llm_service()
    bill_agent = ItemizedBillAgent(llm_service=llm_svc)
    pages = state.get("pages", [])
    segregation = state.get("segregation_summary")

    relevant_page_nums = []
    if segregation and segregation.categories:
        relevant_page_nums = segregation.categories.get(DocumentType.ITEMIZED_BILL.value, [])

    relevant_pages = [p for p in pages if p.page_number in relevant_page_nums]
    logger.info("Itemized Bill Agent received %d relevant pages: %s", len(relevant_pages), relevant_page_nums)

    try:
        bill_data = bill_agent.extract(relevant_pages)
        return {"bill_data": bill_data}
    except Exception as e:
        logger.error("Itemized Bill agent node encountered error: %s", str(e))
        return {"errors": [f"Bill Agent error: {str(e)}"]}


def aggregator_node(state: ClaimState) -> Dict[str, Any]:
    """Combine agent outputs into a unified response."""
    claim_id = state.get("claim_id", "UNKNOWN")
    logger.info("Executing Aggregator Node for claim_id=%s", claim_id)

    segregation = state.get("segregation_summary")
    if segregation is None:
        segregation = SegregationSummary(
            total_pages=len(state.get("pages", [])),
            categories={},
            page_classifications=[],
        )

    id_data = state.get("identity_data")
    discharge_data = state.get("discharge_data")
    bill_data = state.get("bill_data")
    errors = list(state.get("errors", []))

    extracted_data = ExtractedData(
        identity_information=id_data,
        discharge_summary=discharge_data,
        itemized_bill=bill_data,
    )

    start_time = state.get("start_time")
    latency = round(time.time() - start_time, 3) if start_time else None

    if errors:
        status = "PARTIAL_SUCCESS" if (id_data or discharge_data or bill_data) else "ERROR"
    else:
        status = "SUCCESS"

    final_response = ClaimProcessingResponse(
        claim_id=claim_id,
        status=status,
        processing_time_seconds=latency,
        segregation_results=segregation,
        extracted_data=extracted_data,
        errors=errors,
    )

    return {"final_response": final_response}


def build_claim_graph() -> StateGraph:
    """Build and compile the LangGraph workflow."""
    workflow = StateGraph(ClaimState)

    workflow.add_node("segregator", segregator_node)
    workflow.add_node("id_agent", id_agent_node)
    workflow.add_node("discharge_agent", discharge_agent_node)
    workflow.add_node("bill_agent", bill_agent_node)
    workflow.add_node("aggregator", aggregator_node)

    workflow.add_edge(START, "segregator")
    workflow.add_edge("segregator", "id_agent")
    workflow.add_edge("segregator", "discharge_agent")
    workflow.add_edge("segregator", "bill_agent")
    workflow.add_edge("id_agent", "aggregator")
    workflow.add_edge("discharge_agent", "aggregator")
    workflow.add_edge("bill_agent", "aggregator")
    workflow.add_edge("aggregator", END)

    return workflow.compile()


claim_graph = build_claim_graph()


def process_claim_pipeline(claim_id: str, pages: List[PageContent]) -> ClaimProcessingResponse:
    """Execute claim processing pipeline on extracted pages."""
    initial_state: ClaimState = {
        "claim_id": claim_id,
        "pages": pages,
        "errors": [],
        "start_time": time.time(),
    }
    result_state = claim_graph.invoke(initial_state)
    return result_state["final_response"]
