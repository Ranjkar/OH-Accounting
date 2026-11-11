"""Branded agreement PDF (Phase 26) on the shared PdfReportBuilder.

Input is the rendered `content` dict produced by contract_service
(parties, term, services, fees, clauses) -- exactly what is hashed and
stored on the ContractVersion, so the PDF and the signing page are two
views of one immutable document. When `signature` is given, an evidence
page is appended; the result is the final tamper-evident PDF whose own
SHA-256 is stored alongside the hash of the version that was signed.
"""

from datetime import datetime, timezone

from app.reporting.pdf_builder import NAVY, SLATE, PdfReportBuilder
from app.services.contract_templates import label


def render_contract_pdf(content: dict, signature: dict | None = None) -> bytes:
    lang = content["language"]
    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf = PdfReportBuilder(content["title"], content["client"]["name"], f"{label(lang, 'reference')}: {content['reference']}", generated, locale=lang)

    pdf.heading(label(lang, "parties"))
    pdf.key_value_row(label(lang, "provider"), content["provider"]["name"])
    pdf.key_value_row(label(lang, "client"), content["client"]["name"])
    pdf.key_value_row(label(lang, "kvk"), content["client"]["kvk_number"] or "-")
    pdf.key_value_row(label(lang, "vat"), content["client"]["vat_number"] or "-")
    pdf.key_value_row(label(lang, "address"), content["client"]["address"] or "-")
    pdf.key_value_row(label(lang, "representative"), content["client"]["representative"] or "-")

    pdf.heading(label(lang, "term"))
    pdf.paragraph(content["term"]["text"])
    pdf.key_value_row(label(lang, "fee"), content["fees"]["fee_text"], highlight=True)
    pdf.key_value_row(label(lang, "payment_terms"), content["fees"]["payment_terms_text"])
    pdf.key_value_row(label(lang, "notice_period"), content["fees"]["notice_period_text"])

    pdf.heading(label(lang, "services"))
    for service in content["services"]:
        pdf.paragraph(f"- {service['label']}")

    for clause in content["clauses"]:
        pdf.heading(clause["heading"])
        pdf.paragraph(clause["body"])

    pdf.heading(label(lang, "signature_block"))
    if signature is None:
        pdf.paragraph(label(lang, "unsigned_note"), color=SLATE)
    else:
        pdf.paragraph(f"{label(lang, 'signed_by')}: {signature['signer_name_typed']}")
    pdf.paragraph(label(lang, "legal_note"), size=8, color=SLATE)

    if signature is not None:
        pdf.new_page()
        pdf.heading(label(lang, "evidence_title"))
        pdf.key_value_row(label(lang, "reference"), content["reference"])
        pdf.key_value_row(label(lang, "signed_by"), signature["signer_name_typed"])
        pdf.key_value_row(label(lang, "signer_email"), signature["signer_email"])
        pdf.key_value_row(label(lang, "signed_at"), signature["signed_at"])
        if signature.get("ip_address"):
            pdf.key_value_row(label(lang, "ip"), signature["ip_address"])
        pdf.text(label(lang, "method"), size=10, color=SLATE)
        pdf.paragraph(label(lang, "method_value"))
        pdf.text(label(lang, "document_hash"), size=10, color=SLATE)
        pdf.paragraph(signature["document_sha256"], size=9)
        pdf.text(label(lang, "consent"), size=10, color=SLATE)
        pdf.paragraph(signature["consent_text"], size=9)
        pdf.paragraph(label(lang, "legal_note"), size=8, color=NAVY)
    return pdf.to_bytes()
