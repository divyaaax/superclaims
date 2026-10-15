"""End-to-End Integration Test on the Sample 18-Page Medical Claim PDF."""

from fastapi.testclient import TestClient


def test_sample_medical_pdf_full_pipeline(client: TestClient, real_sample_pdf_path, mock_llm_service):
    """End-to-end pipeline test processing all 18 pages of the actual sample medical claim."""
    with open(real_sample_pdf_path, "rb") as f:
        pdf_bytes = f.read()

    files = {"file": ("sample_medical_claim.pdf", pdf_bytes, "application/pdf")}
    data = {"claim_id": "CLM-2024-789456"}

    response = client.post("/api/process", data=data, files=files)
    assert response.status_code == 200

    result = response.json()
    assert result["claim_id"] == "CLM-2024-789456"
    assert result["status"] == "SUCCESS"

    # Check Segregation
    segregation = result["segregation_results"]
    assert segregation["total_pages"] == 18
    assert len(segregation["page_classifications"]) == 18

    # Check extracted ID details
    identity = result["extracted_data"]["identity_information"]
    assert identity["extracted"] is True
    assert identity["patient_name"] == "JOHN MICHAEL SMITH"
    assert identity["date_of_birth"] == "15-MAR-1985"

    # Check extracted Discharge details
    discharge = result["extracted_data"]["discharge_summary"]
    assert discharge["extracted"] is True
    assert "Pneumonia" in discharge["diagnosis"]
    assert discharge["admission_date"] == "January 20, 2025"
    assert discharge["discharge_date"] == "January 25, 2025"

    # Check extracted Bill details
    bill = result["extracted_data"]["itemized_bill"]
    assert bill["extracted"] is True
    assert len(bill["bill_items"]) > 0
    assert bill["discrepancy_detected"] is False
