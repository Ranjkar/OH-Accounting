from datetime import date, timedelta
from decimal import Decimal

from app.core.security import hash_password
from app.models.accounting import AccountingTransaction
from app.models.banking import BankTransaction
from app.models.enums import LedgerSide, ReconciliationStatus, TransactionType, UserRole
from app.models.tenant import Tenant
from app.models.user import User


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


def _setup_company_with_fy(client, headers, year=2027):
    company_id = client.post("/api/v1/companies", json={"name": "Test B.V."}, headers=headers).json()["id"]
    fy = client.post(f"/api/v1/companies/{company_id}/financial-years", json={"year": year}, headers=headers).json()
    return company_id, fy


def _create_purchase_invoice(db_session, company_id, fy_id, user_id, tenant_id, invoice_number="INV-1", counterparty="Acme Supplies"):
    tx = AccountingTransaction(
        tenant_id=tenant_id, company_id=company_id, financial_year_id=fy_id,
        transaction_type=TransactionType.purchase_invoice, ledger_side=LedgerSide.purchases,
        invoice_number=invoice_number, counterparty_name=counterparty,
        invoice_date=date(2027, 2, 1), due_date=date(2027, 6, 1),
        net_amount=Decimal("100.00"), vat_amount=Decimal("21.00"), gross_amount=Decimal("121.00"),
        created_by_user_id=user_id,
    )
    db_session.add(tx)
    db_session.commit()
    return tx


def _create_bank_tx(db_session, company_id, tenant_id, bank_account_id, import_batch_id, booking_date, counterparty_name=None):
    tx = BankTransaction(
        tenant_id=tenant_id, company_id=company_id, bank_account_id=bank_account_id, import_batch_id=import_batch_id,
        dedupe_hash=f"hash-{booking_date}-{counterparty_name}", booking_date=booking_date, amount=Decimal("-50.00"),
        currency="EUR", counterparty_name=counterparty_name, source_format="CSV", raw_data={},
        reconciliation_status=ReconciliationStatus.unmatched,
    )
    db_session.add(tx)
    db_session.commit()
    return tx


def _create_bank_account_and_batch(db_session, company_id, tenant_id, user_id):
    from app.models.banking import BankAccount, BankImportBatch

    account = BankAccount(tenant_id=tenant_id, company_id=company_id, iban="NL91ABNA0417164300", account_name="Main")
    db_session.add(account)
    db_session.flush()
    batch = BankImportBatch(
        tenant_id=tenant_id, company_id=company_id, bank_account_id=account.id,
        source_format="CSV", original_filename="f.csv", storage_path="x", imported_by_user_id=user_id,
    )
    db_session.add(batch)
    db_session.commit()
    return account, batch


# ---- categorization rules ----


def test_create_and_list_categorization_rules(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.post(
        "/api/v1/categorization-rules",
        json={"company_id": company_id, "rule_type": "SUPPLIER_NAME", "match_value": "Acme Supplies", "category": "Office expenses"},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    rules = client.get("/api/v1/categorization-rules", params={"company_id": company_id}, headers=headers).json()
    assert len(rules) == 1
    assert rules[0]["category"] == "Office expenses"


def test_apply_categorization_rules_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_purchase_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)
    client.post(
        "/api/v1/categorization-rules",
        json={"company_id": company_id, "rule_type": "SUPPLIER_NAME", "match_value": "Acme Supplies", "category": "Office expenses"},
        headers=headers,
    )

    response = client.post(f"/api/v1/companies/{company_id}/apply-categorization-rules", headers=headers)
    assert response.status_code == 200
    assert response.json()["rules_applied"] == 1


def test_categorize_transaction_manually_and_remember_rule(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    tx = _create_purchase_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)

    response = client.post(
        f"/api/v1/transactions/{tx.id}/categorize",
        json={"category": "Equipment", "remember_as_rule": True},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["expense_category"] == "Equipment"
    assert response.json()["rule_created_id"] is not None

    rules = client.get("/api/v1/categorization-rules", params={"company_id": company_id}, headers=headers).json()
    assert len(rules) == 1


def test_category_suggestion_uses_stub_provider_without_api_key(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    tx = _create_purchase_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)

    response = client.get(f"/api/v1/transactions/{tx.id}/category-suggestion", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["requires_accountant_review"] is True


def test_categorization_rules_do_not_cross_company(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_a, _ = _setup_company_with_fy(client, headers, year=2027)
    company_b, _ = _setup_company_with_fy(client, headers, year=2028)

    client.post(
        "/api/v1/categorization-rules",
        json={"company_id": company_a, "rule_type": "SUPPLIER_NAME", "match_value": "Acme Supplies", "category": "Office expenses"},
        headers=headers,
    )
    rules_b = client.get("/api/v1/categorization-rules", params={"company_id": company_b}, headers=headers).json()
    assert rules_b == []


# ---- recurring + anomalies ----


def test_detect_recurring_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account, batch = _create_bank_account_and_batch(db_session, company_id, admin.tenant_id, admin.id)
    base = date(2027, 1, 5)
    for i in range(4):
        _create_bank_tx(db_session, company_id, admin.tenant_id, account.id, batch.id, base + timedelta(days=30 * i), counterparty_name="Telco B.V.")

    response = client.post(f"/api/v1/companies/{company_id}/detect-recurring", headers=headers)
    assert response.status_code == 200
    assert len(response.json()) == 1

    listed = client.get(f"/api/v1/companies/{company_id}/recurring-patterns", headers=headers).json()
    assert len(listed) == 1


def test_detect_and_acknowledge_anomaly(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_purchase_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id, invoice_number="INV-1")
    account, batch = _create_bank_account_and_batch(db_session, company_id, admin.tenant_id, admin.id)
    stale_date = date.today() - timedelta(days=30)
    _create_bank_tx(db_session, company_id, admin.tenant_id, account.id, batch.id, stale_date)

    response = client.post(f"/api/v1/companies/{company_id}/detect-anomalies", headers=headers)
    assert response.status_code == 200
    flags = response.json()
    assert len(flags) == 1

    listed = client.get(f"/api/v1/companies/{company_id}/anomalies", headers=headers).json()
    assert len(listed) == 1

    ack = client.post(f"/api/v1/anomalies/{listed[0]['id']}/acknowledge", headers=headers)
    assert ack.status_code == 200
    assert ack.json()["status"] == "ACKNOWLEDGED"

    open_only = client.get(f"/api/v1/companies/{company_id}/anomalies", params={"status_filter": "OPEN"}, headers=headers).json()
    assert open_only == []


def test_dismiss_anomaly(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    account, batch = _create_bank_account_and_batch(db_session, company_id, admin.tenant_id, admin.id)
    stale_date = date.today() - timedelta(days=30)
    _create_bank_tx(db_session, company_id, admin.tenant_id, account.id, batch.id, stale_date)
    client.post(f"/api/v1/companies/{company_id}/detect-anomalies", headers=headers)
    flag_id = client.get(f"/api/v1/companies/{company_id}/anomalies", headers=headers).json()[0]["id"]

    response = client.post(f"/api/v1/anomalies/{flag_id}/dismiss", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "DISMISSED"


# ---- automation centre + cash flow ----


def test_automation_centre_summary(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)
    _create_purchase_invoice(db_session, company_id, fy["id"], admin.id, admin.tenant_id)

    response = client.get(f"/api/v1/companies/{company_id}/automation-centre", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["company_id"] == company_id
    assert body["expenses_awaiting_categorization"] == 1


def test_cash_flow_forecast_endpoint(client, db_session):
    admin = _create_user(db_session)
    headers = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers)

    response = client.get(f"/api/v1/companies/{company_id}/cash-flow-forecast", headers=headers)
    assert response.status_code == 200
    assert "net_bank_transaction_movement_disclaimer" in response.json()


# ---- permissions / tenant isolation ----


def test_viewer_cannot_create_categorization_rule(client, db_session):
    admin = _create_user(db_session)
    headers_admin = _login(client, "admin@acme.nl")
    company_id, fy = _setup_company_with_fy(client, headers_admin)

    viewer = User(tenant_id=admin.tenant_id, email="viewer@acme.nl", hashed_password=hash_password("secret123"), full_name="Viewer", role=UserRole.viewer)
    db_session.add(viewer)
    db_session.commit()
    headers_viewer = _login(client, "viewer@acme.nl")

    response = client.post(
        "/api/v1/categorization-rules",
        json={"company_id": company_id, "rule_type": "SUPPLIER_NAME", "match_value": "x", "category": "Other"},
        headers=headers_viewer,
    )
    assert response.status_code == 403


def test_cross_tenant_cannot_access_automation_centre(client, db_session):
    _create_user(db_session, tenant_name="A", email="a@a.nl")
    headers_a = _login(client, "a@a.nl")
    company_a, _ = _setup_company_with_fy(client, headers_a)

    _create_user(db_session, tenant_name="B", email="b@b.nl")
    headers_b = _login(client, "b@b.nl")
    response = client.get(f"/api/v1/companies/{company_a}/automation-centre", headers=headers_b)
    assert response.status_code == 404
