"""Tests for PDF Processor Module."""

import pytest
from app.pdf_processor import PDFProcessingError, PDFProcessor, PageContent


def test_pdf_extraction_real_sample(real_sample_pdf_path):
    """Test extracting pages from the actual 18-page sample medical claim."""
    pages = PDFProcessor.extract_pages_from_file(real_sample_pdf_path)
    assert len(pages) == 18

    # Verify 1-indexed page numbers
    for i, p in enumerate(pages, start=1):
        assert p.page_number == i
        assert p.char_count > 0
        assert p.has_extractable_text is True

    # Check key text markers on specific pages
    assert "MEDICAL CLAIM FORM" in pages[0].text
    assert "GOVERNMENT ID CARD" in pages[2].text
    assert "DISCHARGE SUMMARY" in pages[3].text
    assert "ITEMIZED HOSPITAL BILL" in pages[8].text


def test_pdf_extraction_empty_bytes():
    """Test that zero-byte PDF raises PDFProcessingError."""
    with pytest.raises(PDFProcessingError, match="empty"):
        PDFProcessor.extract_pages_from_bytes(b"")


def test_pdf_extraction_corrupted_bytes():
    """Test that random garbage bytes raise PDFProcessingError."""
    with pytest.raises(PDFProcessingError, match="Malformed"):
        PDFProcessor.extract_pages_from_bytes(b"NOT_A_PDF_HEADER_DATA_12345")


def test_pdf_extraction_blank_page(sample_pdf_bytes):
    """Test that a generated blank PDF is handled with has_extractable_text=False."""
    pages = PDFProcessor.extract_pages_from_bytes(sample_pdf_bytes)
    assert len(pages) == 2
    for p in pages:
        assert p.has_extractable_text is False
        assert p.is_blank is True
