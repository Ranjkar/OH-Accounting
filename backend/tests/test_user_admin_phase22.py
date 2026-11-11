"""Phase 22: invitation emails + resend, company access management, no self-elevation."""
from app.core.security import hash_password
from app.models.email_outbox import EmailOutbox
from app.models.enums import UserRole
from app.models.tenant import Tenant
from app.models.user import User


def _tenant(db_session, name, owner_email):
    tenant = Tenant(name=name)
    db_session.add(tenant)
    db_session.flush()
    owner = User(tenant_id=tenant.id, email=owner_email, hashed_password=hash_password("secret123"), full_name="Owner", role=UserRole.owner)
    db_session.add(owner)
    db_session.commit()
    return tenant, owner


def _headers(client, email, password="secret123"):
    token = client.post("/api/v1/auth/login", json={"email": email, "password": password}).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_invitation_falls_back_to_link_when_no_provider_and_resend_rotates_token(client, db_session):
    _tenant(db_session, "A", "owner@a.nl")
    h = _headers(client, "owner@a.nl")
    r = client.post("/api/v1/users/invitations", json={"invited_email": "new@a.nl", "intended_role": "accountant"}, headers=h)
    assert r.status_code == 201
    body = r.json()
    assert body["email_sent"] is False and body["raw_token"]  # no provider -> link shown to the inviter
    first_token = body["raw_token"]
    assert db_session.query(EmailOutbox).filter(EmailOutbox.template == "user_invitation").count() == 1

    r = client.post(f"/api/v1/users/invitations/{body['invitation']['id']}/resend", headers=h)
    assert r.status_code == 200
    second_token = r.json()["raw_token"]
    assert second_token != first_token
    # The earlier link is dead; the new one works and enforces the password policy.
    assert client.post("/api/v1/users/invitations/accept", json={"token": first_token, "full_name": "N", "password": "longer-pass-1"}).status_code == 404
    assert client.post("/api/v1/users/invitations/accept", json={"token": second_token, "full_name": "N", "password": "short"}).status_code in (400, 422)
    assert client.post("/api/v1/users/invitations/accept", json={"token": second_token, "full_name": "N", "password": "longer-pass-1"}).status_code == 200


def test_company_access_update_is_tenant_scoped(client, db_session):
    _tenant(db_session, "A", "owner@a.nl")
    _tenant(db_session, "B", "owner@b.nl")
    h_a, h_b = _headers(client, "owner@a.nl"), _headers(client, "owner@b.nl")
    company_a = client.post("/api/v1/companies", json={"name": "A1"}, headers=h_a).json()["id"]
    company_b = client.post("/api/v1/companies", json={"name": "B1"}, headers=h_b).json()["id"]
    inv = client.post("/api/v1/users/invitations", json={"invited_email": "acc@a.nl", "intended_role": "accountant"}, headers=h_a).json()
    acc = client.post("/api/v1/users/invitations/accept", json={"token": inv["raw_token"], "full_name": "Acc", "password": "longer-pass-1"}).json()

    r = client.put(f"/api/v1/users/{acc['id']}/companies", json={"company_ids": [company_a]}, headers=h_a)
    assert r.status_code == 200 and [c["id"] for c in r.json()["companies"]] == [company_a]
    # Foreign company id -> refused, nothing granted.
    assert client.put(f"/api/v1/users/{acc['id']}/companies", json={"company_ids": [company_a, company_b]}, headers=h_a).status_code == 400
    # Other tenant's owner cannot see or touch this user.
    assert client.put(f"/api/v1/users/{acc['id']}/companies", json={"company_ids": [company_b]}, headers=h_b).status_code == 404
    # The accountant cannot manage access (admin only) nor elevate themselves.
    h_acc = _headers(client, "acc@a.nl", "longer-pass-1")
    assert client.put(f"/api/v1/users/{acc['id']}/companies", json={"company_ids": []}, headers=h_acc).status_code == 403
    assert client.patch(f"/api/v1/users/{acc['id']}/role", json={"role": "owner"}, headers=h_acc).status_code == 403
    # Accountant can read company A but not B.
    assert client.get(f"/api/v1/companies/{company_a}", headers=h_acc).status_code == 200
    assert client.get(f"/api/v1/companies/{company_b}", headers=h_acc).status_code == 404
