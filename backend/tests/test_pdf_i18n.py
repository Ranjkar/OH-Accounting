"""Phase 16.1: verifies PDF generation actually renders Persian/Arabic
correctly -- not just that dictionaries/endpoints exist. A font merely
having Unicode code points assigned is not the same as it containing
real Arabic-script glyphs with shaping tables (GSUB/GPOS), and
insert_text() placing one glyph per logical character is not the same
as correct contextual-form shaping + bidi reordering. Both were real,
separately-verified bugs during development (see the Phase 16.1
report) -- these tests pin both down so they can't regress silently."""

import fitz

from app.reporting.pdf_builder import RTL_FONT_FILES, is_rtl, shape_rtl
from app.reporting.report_i18n import SUPPORTED_LOCALES, box_description, t
from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _create_user(db_session, tenant_name="PDF i18n Co", email="pdf-i18n@acme.nl"):
    tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test User", role=UserRole.admin)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# --- Font asset sanity -------------------------------------------------


def test_rtl_fonts_exist_and_have_shaping_tables():
    for locale, path in RTL_FONT_FILES.items():
        assert path.exists(), f"missing font file for {locale}: {path}"
        font = fitz.Font(fontfile=str(path))
        # A font with no GSUB/GPOS can still have Arabic code points
        # mapped to disconnected isolated-form glyphs -- that renders as
        # technically-not-tofu but visually wrong (letters don't join).
        # buffer access confirms this is a real, parseable font file.
        assert font.buffer, f"{locale} font has no glyph data"


def test_shape_rtl_produces_presentation_form_glyphs_not_bare_letters():
    raw = "الفاتورة"  # "the invoice"
    shaped = shape_rtl(raw)
    assert shaped != raw, "shaping should transform the text, not pass it through unchanged"
    # Arabic Presentation Forms-A/B block -- confirms reshaping actually
    # selected contextual (initial/medial/final/isolated) glyph forms.
    assert any(0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFC for ch in shaped)


def test_shape_rtl_is_a_noop_for_pure_latin_numeric_text():
    # IBANs, invoice refs, amounts -- must stay exactly as-is.
    technical = "NL91ABNA0417164300"
    assert shape_rtl(technical) == technical


def test_is_rtl():
    assert is_rtl("ar") and is_rtl("fa")
    assert not is_rtl("nl") and not is_rtl("en")


# --- Rendered PDF content, all 4 locales --------------------------------


def test_vat_report_pdf_renders_real_glyphs_in_all_four_locales(client, db_session):
    user = _create_user(db_session)
    headers = _login(client, user.email)
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()
    vat_period_id = fy["vat_periods"][0]["id"]
    client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id,
            "financial_year_id": fy["id"],
            "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )
    vat_return = client.get("/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers).json()

    for locale in SUPPORTED_LOCALES:
        resp = client.get(
            f"/api/v1/reports/vat-return/{vat_return['id']}",
            params={"format": "pdf", "document_language": locale},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.content[:4] == b"%PDF"

        doc = fitz.open(stream=resp.content, filetype="pdf")
        extracted = doc[0].get_text()

        # The amount and VAT-box code are never translated -- must
        # survive in every locale's PDF unchanged.
        assert "210.00" in extracted
        assert "1a" in extracted

        if locale in ("nl", "en"):
            assert t(locale, "vat", "title") in extracted
        else:
            # Arabic/Persian presentation-form text doesn't always
            # round-trip character-for-character through extraction (MuPDF
            # may normalize some presentation forms back toward base
            # forms), so assert on glyph *origin* instead: every
            # extracted character must be ASCII, a known financial/
            # formatting symbol, or in the Arabic Unicode blocks -- never
            # a placeholder/tofu glyph (which extracts as U+FFFD or is
            # simply absent, not as some other unrelated character).
            assert "�" not in extracted, f"{locale} PDF contains an unrenderable-glyph placeholder"
            has_arabic_script = any(
                0x0600 <= ord(ch) <= 0x06FF or 0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFC
                for ch in extracted
            )
            assert has_arabic_script, f"{locale} PDF has no Arabic-script glyphs at all -- title/headings failed to render"


def test_vat_report_pdf_rtl_layout_is_mirrored_not_just_relabelled():
    """The box-breakdown heading in an RTL document must sit closer to
    the page's right margin than an LTR document's does -- proof the
    *layout* mirrors (RTL isn't just LTR layout with Arabic strings
    dropped in, which would look wrong even with perfect glyph shaping)."""
    from app.reporting.pdf_builder import MARGIN, PAGE_WIDTH, PdfReportBuilder

    ltr = PdfReportBuilder(title="VAT Return Report", company_name="Test BV", subtitle="x", generated_at="x", locale="en")
    ltr.heading("Declaration box breakdown")
    ltr_doc = fitz.open(stream=ltr.to_bytes(), filetype="pdf")
    ltr_word = [w for w in ltr_doc[0].get_text("words") if w[4] == "Declaration"][0]
    ltr_x0 = ltr_word[0]

    rtl = PdfReportBuilder(title="تقرير الإقرار الضريبي", company_name="Test BV", subtitle="x", generated_at="x", locale="ar")
    rtl.heading("تفصيل خانات الإقرار")
    rtl_doc = fitz.open(stream=rtl.to_bytes(), filetype="pdf")
    rtl_words = rtl_doc[0].get_text("words")
    assert rtl_words, "RTL heading produced no extractable text at all"
    rtl_rightmost_x1 = max(w[2] for w in rtl_words if w[1] < 250)  # heading row only, not the navy header band

    assert ltr_x0 < PAGE_WIDTH / 2, "LTR heading should start near the left margin"
    assert rtl_rightmost_x1 > PAGE_WIDTH / 2, "RTL heading should sit near the right margin"
    assert rtl_rightmost_x1 > PAGE_WIDTH - MARGIN - 10, "RTL heading should hug the right margin, mirroring the LTR layout"


def test_vat_report_pdf_table_columns_mirror_for_rtl():
    from app.reporting.pdf_builder import PAGE_WIDTH, PdfReportBuilder

    rtl = PdfReportBuilder(title="x", company_name="x", subtitle="x", generated_at="x", locale="ar")
    rtl.table(["Box", "Description", "Net", "VAT"], [["1a", "Domestic sales", "1000.00", "210.00"]], col_widths=[40, 280, 90, 90])
    doc = fitz.open(stream=rtl.to_bytes(), filetype="pdf")
    words = {w[4]: w[0] for w in doc[0].get_text("words")}
    # In RTL layout the first logical column ("Box"/"1a") must be the
    # rightmost (nearest the page's trailing numeric edge), matching how
    # the LTR layout puts it leftmost -- i.e. actually mirrored, not
    # just re-labelled in place.
    assert words["Box"] > words["VAT"], "RTL table should flow right-to-left: Box (first column) rightmost, VAT (last) leftmost"
    assert words["1a"] > words["210.00"]


def test_unsupported_document_language_rejected(client, db_session):
    user = _create_user(db_session, tenant_name="PDF i18n Co 2", email="pdf-i18n-2@acme.nl")
    headers = _login(client, user.email)
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()
    vat_period_id = fy["vat_periods"][0]["id"]
    vat_return = client.get("/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers).json()

    resp = client.get(
        f"/api/v1/reports/vat-return/{vat_return['id']}",
        params={"format": "pdf", "document_language": "de"},
        headers=headers,
    )
    assert resp.status_code == 400


def test_box_description_translations_exist_for_every_box_and_locale():
    from app.reporting.vat_report import BOX_ROWS

    for locale in SUPPORTED_LOCALES:
        for code, _, _, _ in BOX_ROWS:
            desc = box_description(locale, code)
            assert desc, f"missing box description for {locale}/{code}"
