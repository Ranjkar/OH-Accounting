"""AI extraction provider abstraction. Swap models/providers without touching callers."""

import logging
from typing import Protocol

from app.core.config import settings
from app.schemas.extraction import InvoiceExtraction

logger = logging.getLogger(__name__)

EXTRACTION_TOOL_NAME = "record_invoice_fields"

SYSTEM_PROMPT = (
    "You are an accounting document extraction assistant for a Dutch accounting firm. "
    "Extract structured invoice data from the provided document text. "
    "Only report values that are explicitly present in the text. "
    "If a field is not present or you are not confident, set it to null — never guess or invent a value. "
    "document_type must be one of SALES_INVOICE, PURCHASE_INVOICE, CREDIT_NOTE, RECEIPT, BANK_STATEMENT, OTHER. "
    "classification_confidence is your confidence (0.0-1.0) in the document_type classification. "
    "Support both Dutch and international invoice formats. "
    "Where feasible, record in field_sources a short location hint per extracted field "
    "(e.g. {'invoice_number': 'page 1'})."
)


class AIExtractionProvider(Protocol):
    def extract_invoice_fields(self, text: str) -> InvoiceExtraction: ...


class ClaudeExtractionProvider:
    def __init__(self) -> None:
        import anthropic

        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY not configured")
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    def extract_invoice_fields(self, text: str) -> InvoiceExtraction:
        schema = InvoiceExtraction.model_json_schema()
        response = self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=[
                {
                    "name": EXTRACTION_TOOL_NAME,
                    "description": "Record the extracted invoice fields.",
                    "input_schema": schema,
                }
            ],
            tool_choice={"type": "tool", "name": EXTRACTION_TOOL_NAME},
            messages=[{"role": "user", "content": text[:50_000]}],
        )
        for block in response.content:
            if block.type == "tool_use" and block.name == EXTRACTION_TOOL_NAME:
                return InvoiceExtraction.model_validate(block.input)
        raise RuntimeError("Claude did not return a structured extraction")


class StubExtractionProvider:
    """Used when no AI provider is configured. Never invents data — everything
    comes back null so the document is routed to manual review."""

    def extract_invoice_fields(self, text: str) -> InvoiceExtraction:
        return InvoiceExtraction(document_type="OTHER", classification_confidence=0.0)


_provider: AIExtractionProvider | None = None


def get_ai_provider() -> AIExtractionProvider:
    global _provider
    if _provider is not None:
        return _provider
    try:
        _provider = ClaudeExtractionProvider()
    except Exception:
        logger.warning("No AI extraction provider configured, falling back to StubExtractionProvider")
        _provider = StubExtractionProvider()
    return _provider


def reset_provider_cache() -> None:
    """Test hook: clear the cached provider singleton."""
    global _provider
    _provider = None
