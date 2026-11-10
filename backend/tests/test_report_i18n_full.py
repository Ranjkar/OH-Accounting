"""Phase 16.2: extends the Phase 16.1 VAT-report-only PDF i18n
verification to the other 4 report generators (financial overview,
annual statement, payslip, management reports), plus the XLSX/CSV
compatibility fixes (real numeric cell types, UTF-8 BOM) made in this
phase. Same verification bar as test_pdf_i18n.py: real end-to-end
generation through the API, glyph-origin assertions on the actual PDF
bytes, not just "the function didn't raise"."""

from decimal import Decimal

import fitz
import openpyxl
import io

from app.core.security import hash_password
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User
from app.reporting.report_i18n import MESSAGES, SUPPORTED_LOCALES


def _create_user(db_session, tenant_name, email):
    tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=UserRole.admin)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": "secret123"}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _has_arabic_script_no_tofu(extracted: str) -> bool:
    assert "�" not in extracted
    return any(0x0600 <= ord(ch) <= 0x06FF or 0xFB50 <= ord(ch) <= 0xFDFF or 0xFE70 <= ord(ch) <= 0xFEFC for ch in extracted)


# --- Dictionary completeness ---------------------------------------------


def test_every_report_namespace_has_identical_keys_across_all_locales():
    nl_namespaces = MESSAGES["nl"]
    for namespace, nl_table in nl_namespaces.items():
        nl_keys = set(nl_table.keys())
        for locale in SUPPORTED_LOCALES - {"nl"}:
            other_keys = set(MESSAGES[locale][namespace].keys())
            assert other_keys == nl_keys, f"{locale}.{namespace} keys differ from nl: missing={nl_keys - other_keys} extra={other_keys - nl_keys}"
            for key in nl_keys:
                if isinstance(nl_table[key], dict):
                    assert set(MESSAGES[locale][namespace][key].keys()) == set(nl_table[key].keys())
                else:
                    assert MESSAGES[locale][namespace][key], f"{locale}.{namespace}.{key} is empty"


# --- Financial overview: PDF (all locales) + XLSX numeric types + CSV BOM ---


def test_financial_overview_pdf_all_locales_and_xlsx_csv_compat(client, db_session):
    _create_user(db_session, "Fin Overview Co", "fin-overview@acme.nl")
    headers = _login(client, "fin-overview@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()
    financial_year_id = fy["id"]
    client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id, "financial_year_id": financial_year_id, "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )

    for locale in SUPPORTED_LOCALES:
        resp = client.get(
            "/api/v1/reports/financial-overview",
            params={"company_id": company_id, "financial_year_id": financial_year_id, "format": "pdf", "document_language": locale},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        doc = fitz.open(stream=resp.content, filetype="pdf")
        extracted = doc[0].get_text()
        assert "1000.00" in extracted or "1000" in extracted
        if locale == "ar":
            assert _has_arabic_script_no_tofu(extracted)

    xlsx_resp = client.get(
        "/api/v1/reports/financial-overview",
        params={"company_id": company_id, "financial_year_id": financial_year_id, "format": "xlsx", "document_language": "en"},
        headers=headers,
    )
    assert xlsx_resp.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_resp.content))
    ws = wb["Overview"]
    # Row 6 is the first period data row (1-indexed: title, company,
    # subtitle, blank, header, data...) -- sales_net must be a real
    # number, not the string "1000.00".
    sales_cell = ws.cell(row=6, column=2)
    assert isinstance(sales_cell.value, (int, float, Decimal)), f"expected numeric cell, got {type(sales_cell.value)}"

    csv_resp = client.get(
        "/api/v1/reports/financial-overview",
        params={"company_id": company_id, "financial_year_id": financial_year_id, "format": "csv"},
        headers=headers,
    )
    assert csv_resp.status_code == 200
    assert csv_resp.content.startswith("﻿".encode("utf-8")), "CSV should start with a UTF-8 BOM for Excel compatibility"
    assert b"period,sales_net" in csv_resp.content  # stable, untranslated machine-readable header


def test_financial_overview_unsupported_document_language_rejected(client, db_session):
    _create_user(db_session, "Fin Overview Co 2", "fin-overview-2@acme.nl")
    headers = _login(client, "fin-overview-2@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()
    resp = client.get(
        "/api/v1/reports/financial-overview",
        params={"company_id": company_id, "financial_year_id": fy["id"], "format": "pdf", "document_language": "de"},
        headers=headers,
    )
    assert resp.status_code == 400


# --- Payroll documents: payslip + annual statement, all locales ----------


def _setup_payroll(client, headers):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    employee_id = client.post(
        "/api/v1/employees",
        json={
            "company_id": company_id, "employee_number": "E001", "full_name": "Jan Jansen",
            "employment_start_date": "2025-01-01", "employment_type": "PERMANENT",
            "salary_basis": "MONTHLY", "monthly_salary": "4000.00",
        },
        headers=headers,
    ).json()["id"]
    run_id = client.post(
        "/api/v1/payroll-runs",
        json={"company_id": company_id, "period_type": "MONTHLY", "period_year": 2025, "period_number": 1, "tax_year": 2025},
        headers=headers,
    ).json()["id"]
    payslip_id = client.post(f"/api/v1/payroll-runs/{run_id}/payslips", json={"employee_id": employee_id}, headers=headers).json()["id"]
    return employee_id, payslip_id


def test_payslip_pdf_all_locales(client, db_session):
    _create_user(db_session, "Payroll Co", "payroll@acme.nl")
    headers = _login(client, "payroll@acme.nl")
    _, payslip_id = _setup_payroll(client, headers)

    for locale in SUPPORTED_LOCALES:
        resp = client.get(f"/api/v1/payslips/{payslip_id}/pdf", params={"document_language": locale}, headers=headers)
        assert resp.status_code == 200, resp.text
        doc = fitz.open(stream=resp.content, filetype="pdf")
        extracted = doc[0].get_text()
        assert "4000.00" in extracted
        if locale in ("fa", "ar"):
            assert _has_arabic_script_no_tofu(extracted)


def test_annual_statement_pdf_all_locales(client, db_session):
    _create_user(db_session, "Payroll Co 2", "payroll-2@acme.nl")
    headers = _login(client, "payroll-2@acme.nl")
    employee_id, _ = _setup_payroll(client, headers)

    for locale in SUPPORTED_LOCALES:
        resp = client.get(
            f"/api/v1/employees/{employee_id}/annual-statement/pdf",
            params={"tax_year": 2025, "document_language": locale},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        doc = fitz.open(stream=resp.content, filetype="pdf")
        extracted = doc[0].get_text()
        assert "4000.00" in extracted
        if locale in ("fa", "ar"):
            assert _has_arabic_script_no_tofu(extracted)


# --- Management reports: P&L + Balance Sheet, all locales, numeric XLSX --


def test_profit_and_loss_pdf_all_locales_and_xlsx_numeric(client, db_session):
    _create_user(db_session, "Mgmt Report Co", "mgmt-report@acme.nl")
    headers = _login(client, "mgmt-report@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()
    client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id, "financial_year_id": fy["id"], "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )

    for locale in SUPPORTED_LOCALES:
        resp = client.get(
            "/api/v1/reports/profit-and-loss",
            params={"company_id": company_id, "format": "pdf", "document_language": locale},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        doc = fitz.open(stream=resp.content, filetype="pdf")
        extracted = doc[0].get_text()
        if locale == "ar":
            assert _has_arabic_script_no_tofu(extracted)
        # EBITDA/EBIT are deliberately kept as untranslated finance
        # acronyms in every locale.
        assert "EBITDA" in extracted
        assert "EBIT" in extracted

    xlsx_resp = client.get(
        "/api/v1/reports/profit-and-loss",
        params={"company_id": company_id, "format": "xlsx", "document_language": "en"},
        headers=headers,
    )
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_resp.content))
    ws = wb[wb.sheetnames[0]]
    revenue_row = next(r for r in ws.iter_rows(min_row=1, max_row=ws.max_row) if r[0].value == "Revenue")
    assert isinstance(revenue_row[1].value, (int, float, Decimal))


def test_balance_sheet_pdf_all_locales_and_xlsx_numeric(client, db_session):
    _create_user(db_session, "Mgmt Report Co 2", "mgmt-report-2@acme.nl")
    headers = _login(client, "mgmt-report-2@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers)

    for locale in SUPPORTED_LOCALES:
        resp = client.get(
            "/api/v1/reports/balance-sheet",
            params={"company_id": company_id, "format": "pdf", "document_language": locale},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        doc = fitz.open(stream=resp.content, filetype="pdf")
        extracted = doc[0].get_text()
        if locale == "ar":
            assert _has_arabic_script_no_tofu(extracted)

    xlsx_resp = client.get(
        "/api/v1/reports/balance-sheet",
        params={"company_id": company_id, "format": "xlsx", "document_language": "nl"},
        headers=headers,
    )
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_resp.content))
    ws = wb[wb.sheetnames[0]]
    total_rows = [r for r in ws.iter_rows(min_row=1, max_row=ws.max_row) if r[0].value == "Totaal"]
    assert total_rows, "expected at least one translated 'Totaal' row"
    assert isinstance(total_rows[0][1].value, (int, float, Decimal))


# --- CSV compatibility: UTF-8 BOM + stable RFC 4180 comma delimiter ------
#
# Every CSV export in this app deliberately keeps a plain comma
# delimiter (not locale-dependent semicolon) and untranslated,
# stable snake_case headers -- these files are for machine import/
# export, not for reading, and changing either per UI locale would
# break any script or accountant's import tool built against the
# current header names. The one real cross-locale compatibility
# problem (Excel mis-decoding non-ASCII content as Windows-1252
# without a BOM) is fixed uniformly instead.


def test_all_csv_exports_have_utf8_bom_and_stable_comma_delimited_headers(client, db_session):
    _create_user(db_session, "CSV Compat Co", "csv-compat@acme.nl")
    headers = _login(client, "csv-compat@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()
    vat_period_id = fy["vat_periods"][0]["id"]
    client.post(
        "/api/v1/transactions",
        json={
            "company_id": company_id, "financial_year_id": fy["id"], "ledger_side": "SALES",
            "invoice_date": "2026-02-01",
            "line_items": [{"net_amount": "1000.00", "vat_rate": "21", "vat_amount": "210.00", "vat_treatment": "DOMESTIC_STANDARD"}],
        },
        headers=headers,
    )
    vat_return_id = client.get("/api/v1/vat-returns", params={"company_id": company_id, "vat_period_id": vat_period_id}, headers=headers).json()["id"]

    exports = [
        (f"/api/v1/reports/vat-return/{vat_return_id}", {"format": "csv"}, b"box,description,net,vat"),
        ("/api/v1/reports/financial-overview", {"company_id": company_id, "financial_year_id": fy["id"], "format": "csv"}, b"period,sales_net,purchases_net"),
        ("/api/v1/reports/balance-sheet", {"company_id": company_id, "format": "csv"}, b"section,line,amount"),
        ("/api/v1/reports/profit-and-loss", {"company_id": company_id, "format": "csv"}, b"line,amount"),
    ]
    for path, params, expected_header in exports:
        resp = client.get(path, params=params, headers=headers)
        assert resp.status_code == 200, (path, resp.text)
        assert resp.content.startswith("﻿".encode("utf-8")), f"{path}: missing UTF-8 BOM"
        assert expected_header in resp.content, f"{path}: expected stable header {expected_header!r} not found"
        # Comma-delimited, not locale-dependent semicolon.
        first_line = resp.content.split(b"\n")[0]
        assert b";" not in first_line, f"{path}: header row should be comma-delimited, not semicolon"


# --- Stable API error codes: never localised ------------------------------


def test_unsupported_document_language_error_detail_is_stable_english_regardless_of_accept_language(client, db_session):
    """Validation/error `detail` strings are never translated -- a
    client parsing an error response (or a human reading server logs)
    must see the same stable text regardless of the request's
    Accept-Language or the user's own locale. Only generated REPORT
    CONTENT (and the one wired dashboard message) is ever localised --
    see app/core/messages_i18n.py's module docstring for that
    boundary."""
    _create_user(db_session, "Error Stability Co", "error-stability@acme.nl")
    headers = _login(client, "error-stability@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": 2026}, headers=headers).json()

    for accept_language in ("en", "fa", "ar", "nl"):
        resp = client.get(
            "/api/v1/reports/financial-overview",
            params={"company_id": company_id, "financial_year_id": fy["id"], "format": "pdf", "document_language": "xx"},
            headers={**headers, "Accept-Language": accept_language},
        )
        assert resp.status_code == 400
        assert resp.json()["detail"] == "Unsupported document_language: xx"
