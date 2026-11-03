"""Phase 14: company access invitations -- a business owner (or admin)
authorising another user (typically their accountant) to access a
specific company. Covers the gap found during the Phase 14 architecture
audit: app.models.user.user_companies existed with no API to populate
it at all."""

from app.core.security import hash_password
from app.models.company import Company
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _setup(db_session):
    tenant = Tenant(name="Acme Accounting")
    db_session.add(tenant)
    db_session.flush()
    owner = User(tenant_id=tenant.id, email="owner@acme.nl", hashed_password=hash_password("secret123"), full_name="Owner", role=UserRole.customer)
    accountant = User(tenant_id=tenant.id, email="accountant@firm.nl", hashed_password=hash_password("secret123"), full_name="Accountant", role=UserRole.accountant)
    outsider = User(tenant_id=tenant.id, email="outsider@elsewhere.nl", hashed_password=hash_password("secret123"), full_name="Outsider", role=UserRole.accountant)
    db_session.add_all([owner, accountant, outsider])
    db_session.flush()
    company = Company(tenant_id=tenant.id, name="Client BV")
    db_session.add(company)
    db_session.flush()
    company.users.append(owner)
    db_session.commit()
    return tenant, owner, accountant, outsider, company


def _login(client, email, password="secret123") -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(client, email):
    return {"Authorization": f"Bearer {_login(client, email)}"}


def test_owner_can_invite_an_accountant_and_accountant_can_accept(client, db_session):
    _, owner, accountant, _, company = _setup(db_session)

    create = client.post(
        f"/api/v1/companies/{company.id}/invitations",
        headers=_headers(client, "owner@acme.nl"),
        json={"invited_email": "accountant@firm.nl", "intended_role": "accountant"},
    )
    assert create.status_code == 201, create.text
    token = create.json()["raw_token"]
    assert create.json()["invitation"]["status"] == "PENDING"

    accept = client.post("/api/v1/companies/invitations/accept", headers=_headers(client, "accountant@firm.nl"), json={"token": token})
    assert accept.status_code == 200, accept.text
    assert accept.json()["email"] == "accountant@firm.nl"

    access = client.get(f"/api/v1/companies/{company.id}/access", headers=_headers(client, "owner@acme.nl"))
    assert {a["email"] for a in access.json()} == {"owner@acme.nl", "accountant@firm.nl"}


def test_accountant_without_access_cannot_see_the_company(client, db_session):
    _, owner, accountant, _, company = _setup(db_session)
    response = client.get(f"/api/v1/companies/{company.id}", headers=_headers(client, "accountant@firm.nl"))
    assert response.status_code == 403


def test_invitation_rejects_a_different_accepting_email(client, db_session):
    _, owner, accountant, outsider, company = _setup(db_session)
    create = client.post(
        f"/api/v1/companies/{company.id}/invitations",
        headers=_headers(client, "owner@acme.nl"),
        json={"invited_email": "accountant@firm.nl", "intended_role": "accountant"},
    )
    token = create.json()["raw_token"]

    wrong_person = client.post("/api/v1/companies/invitations/accept", headers=_headers(client, "outsider@elsewhere.nl"), json={"token": token})
    assert wrong_person.status_code == 403


def test_invitation_cannot_be_accepted_twice(client, db_session):
    _, owner, accountant, _, company = _setup(db_session)
    create = client.post(
        f"/api/v1/companies/{company.id}/invitations",
        headers=_headers(client, "owner@acme.nl"),
        json={"invited_email": "accountant@firm.nl", "intended_role": "accountant"},
    )
    token = create.json()["raw_token"]
    client.post("/api/v1/companies/invitations/accept", headers=_headers(client, "accountant@firm.nl"), json={"token": token})

    second = client.post("/api/v1/companies/invitations/accept", headers=_headers(client, "accountant@firm.nl"), json={"token": token})
    assert second.status_code == 409


def test_owner_can_revoke_a_pending_invitation(client, db_session):
    _, owner, accountant, _, company = _setup(db_session)
    create = client.post(
        f"/api/v1/companies/{company.id}/invitations",
        headers=_headers(client, "owner@acme.nl"),
        json={"invited_email": "accountant@firm.nl", "intended_role": "accountant"},
    )
    invitation_id = create.json()["invitation"]["id"]
    token = create.json()["raw_token"]

    revoke = client.post(f"/api/v1/companies/{company.id}/invitations/{invitation_id}/revoke", headers=_headers(client, "owner@acme.nl"))
    assert revoke.status_code == 200
    assert revoke.json()["status"] == "REVOKED"

    accept = client.post("/api/v1/companies/invitations/accept", headers=_headers(client, "accountant@firm.nl"), json={"token": token})
    assert accept.status_code == 409


def test_owner_can_revoke_existing_access(client, db_session):
    _, owner, accountant, _, company = _setup(db_session)
    create = client.post(
        f"/api/v1/companies/{company.id}/invitations",
        headers=_headers(client, "owner@acme.nl"),
        json={"invited_email": "accountant@firm.nl", "intended_role": "accountant"},
    )
    token = create.json()["raw_token"]
    client.post("/api/v1/companies/invitations/accept", headers=_headers(client, "accountant@firm.nl"), json={"token": token})

    db_session.refresh(accountant)
    revoke = client.post(f"/api/v1/companies/{company.id}/access/{accountant.id}/revoke", headers=_headers(client, "owner@acme.nl"))
    assert revoke.status_code == 204

    after = client.get(f"/api/v1/companies/{company.id}", headers=_headers(client, "accountant@firm.nl"))
    assert after.status_code == 403


def test_an_accountant_with_access_cannot_invite_further_access(client, db_session):
    """Invitation management is an ownership decision (admin/customer),
    not something every accountant who happens to have access can do."""
    _, owner, accountant, outsider, company = _setup(db_session)
    company.users.append(accountant)
    db_session.commit()

    response = client.post(
        f"/api/v1/companies/{company.id}/invitations",
        headers=_headers(client, "accountant@firm.nl"),
        json={"invited_email": "outsider@elsewhere.nl", "intended_role": "accountant"},
    )
    assert response.status_code == 403
