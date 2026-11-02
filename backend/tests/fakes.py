"""Fake AI/OCR providers for tests. Real Claude/Tesseract calls are never made
in the automated test suite."""

from app.schemas.extraction import InvoiceExtraction


class FakeAIProvider:
    def __init__(self, result: InvoiceExtraction | None = None, raise_exc: Exception | None = None):
        self.result = result or InvoiceExtraction(
            document_type="PURCHASE_INVOICE",
            classification_confidence=0.95,
            invoice_number="INV-001",
            invoice_date="2026-01-15",
            due_date="2026-02-14",
            supplier_name="Acme Supplies B.V.",
            supplier_vat_number="NL123456789B01",
            customer_name="Test B.V.",
            net_amount=100.0,
            vat_rate=21.0,
            vat_amount=21.0,
            gross_amount=121.0,
            currency="EUR",
        )
        self.raise_exc = raise_exc
        self.calls: list[str] = []
        self.call_contexts: list[tuple[str | None, str | None]] = []

    def extract_invoice_fields(
        self, text: str, client_company_name: str | None = None, client_vat_number: str | None = None
    ) -> InvoiceExtraction:
        self.calls.append(text)
        self.call_contexts.append((client_company_name, client_vat_number))
        if self.raise_exc:
            raise self.raise_exc
        return self.result


class FakeOCRProvider:
    def __init__(self, text: str = "invoice text"):
        self.text = text
        self.calls = 0

    def extract_text(self, image_bytes: bytes) -> str:
        self.calls += 1
        return self.text


class FakeAssistantProvider:
    def __init__(self, answer: str = "This is a fake assistant answer."):
        self.answer = answer
        self.calls: list[tuple[dict, str]] = []

    def ask(self, facts: dict, question: str) -> str:
        self.calls.append((facts, question))
        return self.answer
