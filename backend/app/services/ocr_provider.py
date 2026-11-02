"""OCR provider abstraction. Swap in Azure Document Intelligence later without touching callers."""

import logging
from io import BytesIO
from typing import Protocol

logger = logging.getLogger(__name__)


class OCRProvider(Protocol):
    def extract_text(self, image_bytes: bytes) -> str: ...


class TesseractOCRProvider:
    def __init__(self) -> None:
        import pytesseract

        pytesseract.get_tesseract_version()  # raises if the tesseract binary isn't installed
        self._pytesseract = pytesseract
        available = set(pytesseract.get_languages(config=""))
        self._lang = "+".join(lang for lang in ("eng", "nld") if lang in available) or "eng"

    def extract_text(self, image_bytes: bytes) -> str:
        from PIL import Image

        image = Image.open(BytesIO(image_bytes))
        return self._pytesseract.image_to_string(image, lang=self._lang)


class NullOCRProvider:
    def extract_text(self, image_bytes: bytes) -> str:
        return ""


_provider: OCRProvider | None = None


def get_ocr_provider() -> OCRProvider:
    global _provider
    if _provider is not None:
        return _provider
    try:
        _provider = TesseractOCRProvider()
    except Exception:
        logger.warning("Tesseract OCR unavailable, falling back to NullOCRProvider")
        _provider = NullOCRProvider()
    return _provider


def reset_provider_cache() -> None:
    """Test hook: clear the cached provider singleton."""
    global _provider
    _provider = None
