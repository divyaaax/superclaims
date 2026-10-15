"""PDF Processing Module

Handles reading uploaded PDF files, extracting text on a per-page basis,
preserving 1-indexed page numbers, identifying low-text or empty pages,
and handling malformed or corrupted documents safely.
"""

import io
import logging
from typing import List, Union
from pydantic import BaseModel, Field
import pypdf

logger = logging.getLogger(__name__)


class PageContent(BaseModel):
    """Structured representation of a single page extracted from a PDF."""
    page_number: int = Field(..., description="1-indexed physical page number")
    text: str = Field(..., description="Extracted textual content from the page")
    char_count: int = Field(..., description="Length of extracted text in characters")
    has_extractable_text: bool = Field(..., description="False if text is empty or negligible")
    is_blank: bool = Field(default=False, description="True if no text or minimal whitespace was found")


class PDFProcessingError(Exception):
    """Custom exception raised when PDF parsing fails due to corruption or format errors."""
    pass


class PDFProcessor:
    """Service to safely read and extract text from PDF documents page-by-page."""

    # Threshold for considering a page as containing meaningful text
    MIN_TEXT_THRESHOLD: int = 15

    @classmethod
    def extract_pages_from_bytes(cls, pdf_bytes: bytes) -> List[PageContent]:
        """Extract text from each page of a PDF supplied as raw bytes.

        Args:
            pdf_bytes: Raw bytes of the uploaded PDF file.

        Returns:
            List[PageContent] containing page-by-page text with 1-indexed page numbers.

        Raises:
            PDFProcessingError: If the PDF is malformed, encrypted, or cannot be read.
        """
        if not pdf_bytes:
            raise PDFProcessingError("Uploaded file is empty (0 bytes).")

        try:
            stream = io.BytesIO(pdf_bytes)
            reader = pypdf.PdfReader(stream)
        except Exception as e:
            logger.error("Failed to parse PDF stream: %s", str(e))
            raise PDFProcessingError(f"Malformed or unreadable PDF: {str(e)}") from e

        if reader.is_encrypted:
            try:
                # Attempt empty password decryption if applicable
                decrypted = reader.decrypt("")
                if decrypted == 0:
                    raise PDFProcessingError("PDF is password-protected and cannot be decrypted.")
            except Exception as e:
                raise PDFProcessingError("PDF is encrypted and password protected.") from e

        total_pages = len(reader.pages)
        if total_pages == 0:
            raise PDFProcessingError("PDF contains no readable pages.")

        pages_content: List[PageContent] = []

        for index, page in enumerate(reader.pages):
            page_num = index + 1
            try:
                raw_text = page.extract_text() or ""
            except Exception as e:
                logger.warning("Error extracting text on page %d: %s", page_num, str(e))
                raw_text = ""

            cleaned_text = raw_text.strip()
            char_count = len(cleaned_text)
            has_text = char_count >= cls.MIN_TEXT_THRESHOLD
            is_blank = char_count == 0

            pages_content.append(
                PageContent(
                    page_number=page_num,
                    text=cleaned_text,
                    char_count=char_count,
                    has_extractable_text=has_text,
                    is_blank=is_blank,
                )
            )

        logger.info("Successfully extracted %d pages from PDF.", len(pages_content))
        return pages_content

    @classmethod
    def extract_pages_from_file(cls, file_path: Union[str, io.BytesIO]) -> List[PageContent]:
        """Extract text from each page of a PDF from a file path."""
        try:
            if isinstance(file_path, str):
                with open(file_path, "rb") as f:
                    return cls.extract_pages_from_bytes(f.read())
            return cls.extract_pages_from_bytes(file_path.read())
        except PDFProcessingError:
            raise
        except Exception as e:
            raise PDFProcessingError(f"Error reading PDF file from {file_path}: {str(e)}") from e
