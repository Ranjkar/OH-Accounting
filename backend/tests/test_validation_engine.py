from app.models.document import Document, ExtractedInvoiceFields
from app.models.enums import DocumentType
from app.services.validation_engine import validate_document


def _doc(**kwargs) -> Document:
    defaults = dict(
        tenant_id=1,
        company_id=1,
        uploaded_by_user_id=1,
        original_filename="f.pdf",
        secure_filename="f.pdf",
        storage_path="x",
        content_type="application/pdf",
        file_size=1,
        sha256_hash="x",
    )
    defaults.update(kwargs)
    return Document(**defaults)


def _fields(**kwargs) -> ExtractedInvoiceFields:
    return ExtractedInvoiceFields(document_id=1, **kwargs)


def test_net_plus_vat_equals_gross_passes():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(net_amount=100.0, vat_amount=21.0, gross_amount=121.0, invoice_number="X1")
    findings = validate_document(doc, fields)
    assert not any(f.rule_code == "AMOUNT_MISMATCH" for f in findings)


def test_net_plus_vat_not_equal_gross_flags_error():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(net_amount=100.0, vat_amount=21.0, gross_amount=130.0, invoice_number="X1")
    findings = validate_document(doc, fields)
    assert any(f.rule_code == "AMOUNT_MISMATCH" and f.severity.value == "error" for f in findings)


def test_small_rounding_difference_does_not_flag():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(net_amount=100.0, vat_amount=21.0, gross_amount=121.01, invoice_number="X1")
    findings = validate_document(doc, fields)
    assert not any(f.rule_code == "AMOUNT_MISMATCH" for f in findings)


def test_vat_rate_inconsistent_with_amount():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(
        net_amount=100.0, vat_amount=9.0, gross_amount=109.0, vat_rate=21.0, invoice_number="X1"
    )
    findings = validate_document(doc, fields)
    assert any(f.rule_code == "VAT_RATE_INCONSISTENT" for f in findings)


def test_missing_invoice_number_on_purchase_invoice_is_error():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(net_amount=100.0, vat_amount=21.0, gross_amount=121.0)
    findings = validate_document(doc, fields)
    assert any(f.rule_code == "MISSING_INVOICE_NUMBER" and f.severity.value == "error" for f in findings)


def test_credit_note_without_reference_warns():
    doc = _doc(document_type=DocumentType.credit_note)
    fields = _fields(net_amount=-10.0, vat_amount=-2.1, gross_amount=-12.1)
    findings = validate_document(doc, fields)
    assert any(f.rule_code == "MISSING_CREDIT_NOTE_REFERENCE" for f in findings)


def test_due_date_before_invoice_date_is_error():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(invoice_number="X1", invoice_date="2026-02-01", due_date="2026-01-01")
    findings = validate_document(doc, fields)
    assert any(f.rule_code == "DUE_DATE_BEFORE_INVOICE_DATE" for f in findings)


def test_duplicate_document_flagged():
    doc = _doc(is_duplicate=True, duplicate_of_document_id=7)
    findings = validate_document(doc, None)
    assert any(f.rule_code == "DUPLICATE_DOCUMENT" and f.severity.value == "error" for f in findings)


def test_missing_vat_breakdown_warns():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(invoice_number="X1", gross_amount=121.0)
    findings = validate_document(doc, fields)
    assert any(f.rule_code == "MISSING_VAT_BREAKDOWN" for f in findings)


def test_unrecognized_currency_is_info_only():
    doc = _doc(document_type=DocumentType.purchase_invoice)
    fields = _fields(net_amount=100.0, vat_amount=21.0, gross_amount=121.0, invoice_number="X1", currency="XYZ")
    findings = validate_document(doc, fields)
    match = [f for f in findings if f.rule_code == "UNRECOGNIZED_CURRENCY"]
    assert match and match[0].severity.value == "info"
