from datetime import date
from decimal import Decimal

from app.core.security import hash_password
from app.models.enums import LedgerSide, TransactionType, UserRole
from app.models.tenant import Tenant
from app.models.user import User

CAMT053_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Acct><Id><IBAN>NL91ABNA0417164300</IBAN></Id></Acct>
      <Ntry>
        <Amt Ccy="EUR">121.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-02-10</Dt></BookgDt>
        <ValDt><Dt>2026-02-10</Dt></ValDt>
        <AcctSvcrRef>REF-0001</AcctSvcrRef>
        <NtryDtls>
          <TxDtls>
            <RmtInf><Ustrd>Invoice INV-1</Ustrd></RmtInf>
            <RltdPties><Dbtr><Nm>Klant Retail B.V.</Nm></Dbtr></RltdPties>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def _create_user(db_session, tenant_name="Acme Accounting", email="admin@acme.nl", role=UserRole.admin):
    tenant = db_session.query(Tenant).filter(Tenant.name == tenant_name).first()
    if tenant is None:
        tenant = Tenant(name=tenant_name)
        db_session.add(tenant)
        db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123") -> dict:
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _setup_company_with_fy(client, headers, year=2026):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": year}, headers=headers).json()
    return company_id, fy


def _create_bank_account(client, headers, company_id):
    return client.post(
        "/api/v1/bank-accounts",
        json={"company_id": company_id, "iban": "NL91ABNA0417164300", "account_name": "Main"},
        headers=headers,
    ).json()


def _create_invoice(db_session, company_id, fy_id, user_id, tenant_id, invoice_number="INV-1", gross=Decimal("121.00")):
    from app.models.accounting import AccountingTransaction

    tx = AccountingTransaction(
        tenant_id=tenant_id, company_id=company_id, financial_year_id=fy_id,
        transaction_type=TransactionType.sales_invoice, ledger_side=LedgerSide.sales,
        invoice_number=invoice_number, counterparty_name="Klant Retail B.V.",
        invoice_date=date(2026, 2, 1), due_date=date(2027, 6, 1),
        net_amount=Decimal("100.00"), vat_amount=Decimal("21.00"), gross_amount=gross,
        created_by_user_id=user_id,
    )
    db_session.add(tx)
    db_session.commit()
    return tx


def test_create_bank_account_and_import_camt053(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account = _create_bank_account(client, headers, company_id)

    response = client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    batch = response.json()
    assert batch["transaction_count"] == 1
    assert batch["duplicate_count"] == 0

    transactions = client.get("/api/v1/bank-transactions", params={"company_id": company_id}, headers=headers).json()
    assert len(transactions) == 1
    assert transactions[0]["amount"] == "121.00"


def test_reimporting_the_same_file_prevents_duplicates(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account = _create_bank_account(client, headers, company_id)

    for _ in range(2):
        response = client.post(
            f"/api/v1/bank-accounts/{account['id']}/import",
            params={"source_format": "CAMT053"},
            files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
            headers=headers,
        )

    assert response.json()["duplicate_count"] == 1
    assert response.json()["transaction_count"] == 0
    transactions = client.get("/api/v1/bank-transactions", params={"company_id": company_id}, headers=headers).json()
    assert len(transactions) == 1  # never posted/imported twice


def test_import_generates_suggestions_automatically(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account = _create_bank_account(client, headers, company_id)
    _create_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)

    client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )
    transactions = client.get("/api/v1/bank-transactions", params={"company_id": company_id}, headers=headers).json()
    detail = client.get(f"/api/v1/bank-transactions/{transactions[0]['id']}", headers=headers).json()
    assert detail["reconciliation_status"] == "SUGGESTED_MATCH"
    assert len(detail["matches"]) == 1
    assert detail["matches"][0]["confidence_level"] == "HIGH"


def test_approve_match_via_api_creates_payment(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account = _create_bank_account(client, headers, company_id)
    _create_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)

    client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )
    tx_id = client.get("/api/v1/bank-transactions", params={"company_id": company_id}, headers=headers).json()[0]["id"]
    detail = client.get(f"/api/v1/bank-transactions/{tx_id}", headers=headers).json()
    match_id = detail["matches"][0]["id"]

    approve = client.post(f"/api/v1/payment-matches/{match_id}/approve", headers=headers)
    assert approve.status_code == 200
    assert approve.json()["status"] == "APPROVED"

    detail = client.get(f"/api/v1/bank-transactions/{tx_id}", headers=headers).json()
    assert detail["reconciliation_status"] == "MATCHED"

    # Reversible: reverse the match and confirm the bank tx goes back to unmatched.
    reverse = client.post(
        f"/api/v1/payment-matches/{match_id}/reverse", json={"reason": "test reversal"}, headers=headers
    )
    assert reverse.status_code == 200
    detail = client.get(f"/api/v1/bank-transactions/{tx_id}", headers=headers).json()
    assert detail["reconciliation_status"] == "UNMATCHED"


def test_bulk_approve_high_confidence(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account = _create_bank_account(client, headers, company_id)
    _create_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)

    client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )
    response = client.post("/api/v1/payment-matches/bulk-approve-high-confidence", params={"company_id": company_id}, headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["status"] == "APPROVED"


def test_exclude_transaction(client, db_session):
    _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account = _create_bank_account(client, headers, company_id)
    client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )
    tx_id = client.get("/api/v1/bank-transactions", params={"company_id": company_id}, headers=headers).json()[0]["id"]
    response = client.post(f"/api/v1/bank-transactions/{tx_id}/exclude", headers=headers)
    assert response.status_code == 200
    assert response.json()["reconciliation_status"] == "EXCLUDED"


def test_viewer_cannot_import_or_approve(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)
    account = _create_bank_account(client, headers_admin, company_id)

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_cross_tenant_access_to_bank_account_blocked(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, fy_a = _setup_company_with_fy(client, headers_a)
    account = _create_bank_account(client, headers_a, company_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get(f"/api/v1/bank-accounts/{account['id']}/import-batches", headers=headers_b)
    assert response.status_code == 404
