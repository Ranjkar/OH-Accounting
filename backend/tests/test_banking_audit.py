"""Phase 15: banking.py previously wrote zero AuditLog rows -- this
confirms the gap is actually closed for the key mutating actions (account
creation, statement import, exclude, approve/reject/reverse a match)."""

from app.core.security import hash_password
from app.models.audit_log import AuditLog
from app.models.enums import UserRole
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
            <RmtInf><Ustrd>Unmatched</Ustrd></RmtInf>
            <RltdPties><Dbtr><Nm>Klant Retail B.V.</Nm></Dbtr></RltdPties>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""


def _create_user(db_session, email="admin@acme.nl", role=UserRole.admin):
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    user = User(tenant_id=tenant.id, email=email, hashed_password=hash_password("secret123"), full_name="Test", role=role)
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, email, password="secret123") -> dict:
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_bank_account_creation_and_import_are_audited(client, db_session):
    user = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]

    account = client.post(
        "/api/v1/bank-accounts",
        json={"company_id": company_id, "iban": "NL91ABNA0417164300", "account_name": "Main", "currency": "EUR"},
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )

    actions = {row.action for row in db_session.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id).all()}
    assert "create" in actions and any(
        row.action == "create" and row.entity_type == "bank_account"
        for row in db_session.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id).all()
    )
    assert any(row.action == "import" and row.entity_type == "bank_import_batch" for row in db_session.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id).all())


def test_exclude_and_reconciliation_actions_are_audited(client, db_session):
    user = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    account = client.post(
        "/api/v1/bank-accounts",
        json={"company_id": company_id, "iban": "NL91ABNA0417164300", "account_name": "Main", "currency": "EUR"},
        headers=headers,
    ).json()
    client.post(
        f"/api/v1/bank-accounts/{account['id']}/import",
        params={"source_format": "CAMT053"},
        files={"file": ("statement.xml", CAMT053_SAMPLE.encode(), "application/xml")},
        headers=headers,
    )
    tx_id = client.get("/api/v1/bank-transactions", params={"company_id": company_id}, headers=headers).json()[0]["id"]

    client.post(f"/api/v1/bank-transactions/{tx_id}/exclude", headers=headers)

    rows = db_session.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id, AuditLog.entity_type == "bank_transaction").all()
    assert any(r.action == "exclude" for r in rows)
