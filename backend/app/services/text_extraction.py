"""Text extraction for PDFs and images. PDFs use their embedded text layer
when present (digital invoices); OCR is only a fallback for scanned pages."""

import fitz  # PyMuPDF

from app.services.ocr_provider import OCRProvider

MIN_CHARS_PER_PAGE_BEFORE_OCR_FALLBACK = 20


def extract_pdf_text(content: bytes, ocr_provider: OCRProvider) -> tuple[str, bool]:
    """Returns (full_text, used_ocr)."""
    doc = fitz.open(stream=content, filetype="pdf")
    pages_text: list[str] = []
    used_ocr = False
    try:
        for page in doc:
            text = page.get_text().strip()
            if len(text) < MIN_CHARS_PER_PAGE_BEFORE_OCR_FALLBACK:
                pixmap = page.get_pixmap(dpi=200)
                ocr_text = ocr_provider.extract_text(pixmap.tobytes("png")).strip()
                if ocr_text:
                    used_ocr = True
                text = ocr_text or text
            pages_text.append(f"--- page {page.number + 1} ---\n{text}")
    finally:
        doc.close()
    return "\n\n".join(pages_text), used_ocr


def extract_image_text(content: bytes, ocr_provider: OCRProvider) -> str:
    return ocr_provider.extract_text(content)
