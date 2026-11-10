"""Phase 17.2 -- cross-tenant isolation regression tests.

Covers the seven vulnerable endpoints plus the membership-grant defect
found by the technical audit (docs/QWEN_TECHNICAL_AUDIT_REPORT.md,
section 6.7). Before Phase 17.1, `require_company_access` returned
immediately for ADMIN_ROLES with no tenant comparison, so isolation
depended on each of the 61 call sites writing its own
`tenant_id != user.tenant_id` filter. Seven did not:

  CRITICAL-1  POST /companies/{id}/financial-years/{fy}/lock     (WRITE)
  CRITICAL-1  POST /companies/{id}/financial-years/{fy}/unlock   (WRITE)
  CRITICAL-2  POST /payment-matches/bulk-approve-high-confidence (WRITE)
  HIGH-1      GET  /companies/{id}/financial-years               (read)
  HIGH-2      GET  /companies/{id}/invitations                   (read, PII)
  HIGH-3      POST /companies/{id}/invitations/{inv}/revoke      (WRITE)
  MEDIUM-1    GET  /companies/{id}/notes                         (read, free text)
  HIGH-4      POST /companies/invitations/accept                 (membership grant)

Every endpoint test below follows the same three-part shape: attempt the
operation from a second, independent tenant; assert it is denied; assert
that NO database row changed. `test_same_tenant_*` positive controls prove
the rightful tenant can still perform every one of these operations, so
the fix cannot pass by simply breaking the endpoints for everybody.

Denied cross-tenant access returns 404, not 403, matching the convention
every pre-existing per-endpoint tenant check in this codebase already used
(documents.py:44, banking.py:45, transactions.py:33, ...): a caller from
another tenant learns neither that the company exists nor anything about
its id space. Same-tenant non-members keep the original 403 -- asserted
explicitly by test_same_tenant_non_member_still_gets_403_not_404 so that
distinction cannot silently regress.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.core.deps import require_company_access
from app.core.security import generate_password_reset_token, hash_password, hash_reset_token
from app.models.accounting import AccountingTransaction, Payment
from app.models.audit_log import AuditLog
from app.models.banking import BankAccount, BankImportBatch, BankTransaction, PaymentMatch
from app.models.company import Company
from app.models.company_invitation import CompanyInvitation
from app.models.enums import (
    BankSourceFormat,
    CompanyInvitationStatus,
    LedgerSide,
    NoteType,
    ReconciliationStatus,
    TransactionType,
    UserRole,
)
from app.models.financial_year import FinancialYear
from app.models.note import AccountantNote
from app.models.tenant import Tenant
from app.models.user import User

PASSWORD = "secret123"


# --------------------------------------------------------------------------
# World construction: two fully independent tenants, four roles each.
# --------------------------------------------------------------------------


def _login(client, email, password=PASSWORD) -> str:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def _headers(client, email) -> dict:
    return {"Authorization": f"Bearer {_login(client, email)}"}


def _user(db_session, tenant, email, role) -> User:
    user = User(
        tenant_id=tenant.id,
        email=email,
        hashed_password=hash_password(PASSWORD),
        full_name=f"{role.value} {tenant.name}",
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return user


def _build_tenant(db_session, suffix: str) -> SimpleNamespace:
    """One self-contained tenant: four role-holders, a company they all
    belong to, an unlocked 2026 financial year, an accountant note, a
    pending company invitation, and one HIGH-confidence SUGGESTED payment
    match wired to a real bank transaction and accounting transaction."""
    tenant = Tenant(name=f"Tenant {suffix}")
    db_session.add(tenant)
    db_session.flush()

    owner = _user(db_session, tenant, f"owner@{suffix}.nl", UserRole.owner)
    admin = _user(db_session, tenant, f"admin@{suffix}.nl", UserRole.admin)
    accountant = _user(db_session, tenant, f"accountant@{suffix}.nl", UserRole.accountant)
    viewer = _user(db_session, tenant, f"viewer@{suffix}.nl", UserRole.viewer)
    # A same-tenant admin who is deliberately NOT a member of the company,
    # used to prove admins still reach companies inside their own tenant.
    other_admin = _user(db_session, tenant, f"otheradmin@{suffix}.nl", UserRole.admin)

    company = Company(tenant_id=tenant.id, name=f"{suffix} Client BV")
    db_session.add(company)
    db_session.flush()
    company.users.extend([owner, admin, accountant, viewer])

    financial_year = FinancialYear(
        company_id=company.id, year=2026, start_date=date(2026, 1, 1), end_date=date(2026, 12, 31)
    )
    db_session.add(financial_year)

    note = AccountantNote(
        tenant_id=tenant.id,
        company_id=company.id,
        author_user_id=accountant.id,
        note_type=NoteType.internal,
        body=f"Confidential {suffix} note: client disputes the Q3 VAT position.",
    )
    db_session.add(note)

    _, token_hash = generate_password_reset_token()
    invitation = CompanyInvitation(
        tenant_id=tenant.id,
        company_id=company.id,
        invited_email=f"external@{suffix}.nl",
        intended_role=UserRole.accountant,
        invited_by_user_id=owner.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(invitation)

    bank_account = BankAccount(
        tenant_id=tenant.id,
        company_id=company.id,
        iban=f"NL00BANK00000000{suffix.zfill(2)}",
        account_name=f"{suffix} Operating",
        currency="EUR",
    )
    db_session.add(bank_account)
    db_session.flush()

    import_batch = BankImportBatch(
        tenant_id=tenant.id,
        company_id=company.id,
        bank_account_id=bank_account.id,
        source_format=BankSourceFormat.csv,
        original_filename=f"{suffix}_statement.csv",
        storage_path=f"{tenant.id}/{company.id}/{suffix}_statement.csv",
        imported_by_user_id=admin.id,
    )
    db_session.add(import_batch)
    db_session.flush()

    bank_tx = BankTransaction(
        tenant_id=tenant.id,
        company_id=company.id,
        bank_account_id=bank_account.id,
        import_batch_id=import_batch.id,
        dedupe_hash=f"{suffix}-dedupe-1",
        booking_date=date(2026, 3, 15),
        amount=Decimal("1210.00"),
        currency="EUR",
        counterparty_name=f"{suffix} Customer",
        payment_reference=f"INV-{suffix}-001",
        source_format=BankSourceFormat.csv,
        raw_data={"amount": "1210.00"},
        reconciliation_status=ReconciliationStatus.suggested_match,
    )
    db_session.add(bank_tx)

    acc_tx = AccountingTransaction(
        tenant_id=tenant.id,
        company_id=company.id,
        financial_year_id=financial_year.id,
        transaction_type=TransactionType.sales_invoice,
        ledger_side=LedgerSide.sales,
        invoice_number=f"INV-{suffix}-001",
        counterparty_name=f"{suffix} Customer",
        invoice_date=date(2026, 2, 28),
        due_date=date(2026, 3, 31),
        net_amount=Decimal("1000.00"),
        vat_amount=Decimal("210.00"),
        gross_amount=Decimal("1210.00"),
        net_amount_eur=Decimal("1000.00"),
        vat_amount_eur=Decimal("210.00"),
        gross_amount_eur=Decimal("1210.00"),
        created_by_user_id=admin.id,
    )
    db_session.add(acc_tx)
    db_session.flush()

    match = PaymentMatch(
        tenant_id=tenant.id,
        company_id=company.id,
        bank_transaction_id=bank_tx.id,
        accounting_transaction_id=acc_tx.id,
        allocated_amount=Decimal("1210.00"),
        confidence_score=Decimal("95.00"),
        confidence_level="HIGH",
        match_signals={"exact_amount": True, "invoice_number_in_reference": True},
        status="SUGGESTED",
    )
    db_session.add(match)
    db_session.commit()

    return SimpleNamespace(
        tenant=tenant,
        owner=owner,
        admin=admin,
        accountant=accountant,
        viewer=viewer,
        other_admin=other_admin,
        company=company,
        financial_year=financial_year,
        note=note,
        invitation=invitation,
        bank_account=bank_account,
        bank_tx=bank_tx,
        acc_tx=acc_tx,
        match=match,
        emails={
            UserRole.owner: owner.email,
            UserRole.admin: admin.email,
            UserRole.accountant: accountant.email,
            UserRole.viewer: viewer.email,
        },
    )


@pytest.fixture()
def world(db_session):
    """Two independent tenants. `victim` owns all the data; `attacker` is a
    completely separate organisation whose users must never reach it."""
    victim = _build_tenant(db_session, "victim")
    attacker = _build_tenant(db_session, "attacker")
    return SimpleNamespace(victim=victim, attacker=attacker, db=db_session)


def _attacker_headers(client, world, role: UserRole) -> dict:
    return _headers(client, world.attacker.emails[role])


def _entity_audit_count(db, entity_type: str, entity_id: int) -> int:
    """Audit rows for one specific entity.

    Deliberately NOT scoped to the victim's tenant: the whole point of audit
    CRITICAL-1/HIGH-3 was that a successful cross-tenant write stamps the
    AuditLog row with the ATTACKER's tenant_id, so it never appears in the
    victim's own audit trail. Filtering by entity proves the write did not
    happen regardless of whose tenant it would have been logged into.
    """
    return (
        db.query(AuditLog)
        .filter(AuditLog.entity_type == entity_type, AuditLog.entity_id == entity_id)
        .count()
    )


# --------------------------------------------------------------------------
# Unit-level: the helper itself.
# --------------------------------------------------------------------------


def test_require_company_access_rejects_every_role_from_another_tenant(world):
    """The core fix. Previously returned immediately for owner/admin."""
    for role in (UserRole.owner, UserRole.admin, UserRole.accountant, UserRole.viewer):
        attacker_user = getattr(world.attacker, role.value)
        with pytest.raises(HTTPException) as exc:
            require_company_access(world.victim.company.id, attacker_user, world.db)
        assert exc.value.status_code == 404, f"{role.value} should get 404, not {exc.value.status_code}"


def test_require_company_access_allows_same_tenant_admin_without_membership(world):
    """Admins must still reach any company inside their OWN tenant -- the
    fix must not break the legitimate admin bypass, only scope it."""
    company = require_company_access(world.victim.company.id, world.victim.other_admin, world.db)
    assert company.id == world.victim.company.id
    assert world.victim.other_admin not in world.victim.company.users


def test_require_company_access_returns_the_company_for_members(world):
    company = require_company_access(world.victim.company.id, world.victim.accountant, world.db)
    assert company.id == world.victim.company.id


def test_same_tenant_non_member_still_gets_403_not_404(db_session, world):
    """A same-tenant user who is not a member keeps the ORIGINAL 403. Only
    the cross-tenant case became 404. Guards against the two being collapsed
    into one status code, which would either leak existence across tenants
    or change documented behaviour for non-admin roles."""
    tenant = Tenant(name="Tenant Third")
    db_session.add(tenant)
    db_session.flush()
    stranger = _user(db_session, tenant, "stranger@third.nl", UserRole.accountant)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        require_company_access(world.victim.company.id, stranger, db_session)
    assert exc.value.status_code == 404  # different tenant -> no existence leak

    # Now a same-tenant non-member: 403, unchanged from before Phase 17.1.
    outsider = _user(db_session, world.victim.tenant, "outsider@victim.nl", UserRole.accountant)
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        require_company_access(world.victim.company.id, outsider, db_session)
    assert exc.value.status_code == 403


def test_require_company_access_unknown_company_is_404(world):
    with pytest.raises(HTTPException) as exc:
        require_company_access(999_999, world.victim.owner, world.db)
    assert exc.value.status_code == 404


# --------------------------------------------------------------------------
# CRITICAL-1 -- cross-tenant financial-year lock / unlock.
# --------------------------------------------------------------------------


def test_cross_tenant_financial_year_lock_is_denied_and_changes_nothing(client, world):
    """Audit CRITICAL-1. Locking a victim's financial year halts their
    bookkeeping (ledger_service._ensure_financial_year_open blocks new and
    corrected postings), and the AuditLog row used to land in the ATTACKER's
    tenant so the victim's trail showed nothing."""
    db = world.db
    fy = world.victim.financial_year
    assert fy.is_locked is False

    # Log in first: a successful login writes its own AuditLog row, so headers
    # must be captured before the audit snapshot is taken.
    attacker_sessions = {role: _attacker_headers(client, world, role) for role in (UserRole.owner, UserRole.admin)}
    audit_before = _entity_audit_count(db, "financial_year", fy.id)

    for role, headers in attacker_sessions.items():
        response = client.post(
            f"/api/v1/companies/{world.victim.company.id}/financial-years/{fy.id}/lock",
            headers=headers,
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"

    db.refresh(fy)
    assert fy.is_locked is False
    assert fy.locked_at is None
    assert fy.locked_by_user_id is None
    assert _entity_audit_count(db, "financial_year", fy.id) == audit_before


def test_cross_tenant_financial_year_unlock_is_denied_and_changes_nothing(client, world):
    """The mirror image: unlocking removes the period-integrity control that
    stops postings being backdated into an already-filed period."""
    db = world.db
    fy = world.victim.financial_year
    fy.is_locked = True
    fy.locked_at = datetime.now(timezone.utc)
    fy.locked_by_user_id = world.victim.owner.id
    db.commit()
    locked_at = fy.locked_at

    attacker_sessions = {role: _attacker_headers(client, world, role) for role in (UserRole.owner, UserRole.admin)}
    audit_before = _entity_audit_count(db, "financial_year", fy.id)

    for role, headers in attacker_sessions.items():
        response = client.post(
            f"/api/v1/companies/{world.victim.company.id}/financial-years/{fy.id}/unlock",
            headers=headers,
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"

    db.refresh(fy)
    assert fy.is_locked is True
    assert fy.locked_at == locked_at
    assert fy.locked_by_user_id == world.victim.owner.id
    assert _entity_audit_count(db, "financial_year", fy.id) == audit_before


def test_cross_tenant_lock_with_a_mismatched_pair_is_also_denied(client, world):
    """The attacker's own company_id paired with the victim's
    financial_year_id -- the combination the old `financial_year.company_id
    != company_id` tie could not catch, because both values were
    attacker-supplied."""
    response = client.post(
        f"/api/v1/companies/{world.attacker.company.id}/financial-years/{world.victim.financial_year.id}/lock",
        headers=_attacker_headers(client, world, UserRole.owner),
    )
    assert response.status_code == 404
    world.db.refresh(world.victim.financial_year)
    assert world.victim.financial_year.is_locked is False


# --------------------------------------------------------------------------
# CRITICAL-2 -- cross-tenant bulk payment-match approval.
# --------------------------------------------------------------------------


def test_cross_tenant_bulk_match_approval_is_denied_and_posts_nothing(client, world):
    """Audit CRITICAL-2. The query filtered only on company_id, so any admin
    of any tenant could approve every HIGH-confidence suggested match on an
    arbitrary company's books in one request -- posting real Payment rows and
    flipping reconciliation state on someone else's ledger."""
    db = world.db
    match = world.victim.match
    assert match.status == "SUGGESTED"
    payments_before = db.query(Payment).count()

    for role in (UserRole.owner, UserRole.admin, UserRole.accountant):
        response = client.post(
            "/api/v1/payment-matches/bulk-approve-high-confidence",
            params={"company_id": world.victim.company.id},
            headers=_attacker_headers(client, world, role),
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"

    db.refresh(match)
    assert match.status == "SUGGESTED"
    assert match.approved_by_user_id is None
    assert match.approved_at is None
    assert match.payment_id is None
    assert db.query(Payment).count() == payments_before
    db.refresh(world.victim.bank_tx)
    assert world.victim.bank_tx.reconciliation_status == ReconciliationStatus.suggested_match


# --------------------------------------------------------------------------
# HIGH-1 -- cross-tenant financial-year listing.
# --------------------------------------------------------------------------


def test_cross_tenant_financial_year_listing_is_denied(client, world):
    """Audit HIGH-1. Leaked fiscal years, is_locked, and via
    FinancialYearOut's nested periods every VAT period label, start/end,
    filing and payment deadline -- and handed over the exact
    financial_year_id values needed to drive CRITICAL-1."""
    for role in (UserRole.owner, UserRole.admin, UserRole.accountant, UserRole.viewer):
        response = client.get(
            f"/api/v1/companies/{world.victim.company.id}/financial-years",
            headers=_attacker_headers(client, world, role),
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"


# --------------------------------------------------------------------------
# HIGH-2 / HIGH-3 -- cross-tenant invitation listing and revocation.
# --------------------------------------------------------------------------


def test_cross_tenant_invitation_listing_is_denied(client, world):
    """Audit HIGH-2. Leaked invited_email, intended_role, status,
    invited_by_user_id, expires_at and token_hash for another tenant's
    pending accountant invitations."""
    for role in (UserRole.owner, UserRole.admin):
        response = client.get(
            f"/api/v1/companies/{world.victim.company.id}/invitations",
            headers=_attacker_headers(client, world, role),
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"
        assert "external@victim.nl" not in response.text


def test_cross_tenant_invitation_revocation_is_denied_and_changes_nothing(client, world):
    """Audit HIGH-3. An owner in tenant A could revoke any pending invitation
    in tenant B, silently blocking that firm from onboarding its accountant,
    with the audit row landing in the attacker's tenant."""
    db = world.db
    invitation = world.victim.invitation
    assert invitation.status == CompanyInvitationStatus.pending

    attacker_sessions = {role: _attacker_headers(client, world, role) for role in (UserRole.owner, UserRole.admin)}
    audit_before = _entity_audit_count(db, "company_invitation", invitation.id)

    for role, headers in attacker_sessions.items():
        response = client.post(
            f"/api/v1/companies/{world.victim.company.id}/invitations/{invitation.id}/revoke",
            headers=headers,
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"

    db.refresh(invitation)
    assert invitation.status == CompanyInvitationStatus.pending
    assert invitation.revoked_at is None
    assert _entity_audit_count(db, "company_invitation", invitation.id) == audit_before


def test_cross_tenant_invitation_revoke_with_attacker_company_id_is_denied(client, world):
    """Attacker's own company_id paired with the victim's invitation_id --
    caught by the new invitation.tenant_id predicate even before the company
    check, so the defence-in-depth layer is exercised independently."""
    response = client.post(
        f"/api/v1/companies/{world.attacker.company.id}/invitations/{world.victim.invitation.id}/revoke",
        headers=_attacker_headers(client, world, UserRole.owner),
    )
    assert response.status_code == 404
    world.db.refresh(world.victim.invitation)
    assert world.victim.invitation.status == CompanyInvitationStatus.pending


# --------------------------------------------------------------------------
# MEDIUM-1 -- cross-tenant accountant notes.
# --------------------------------------------------------------------------


def test_cross_tenant_accountant_notes_are_denied(client, world):
    """Audit MEDIUM-1. Guarded only by get_current_user, so ANY role in ANY
    tenant -- including a read-only viewer -- could read another firm's
    free-text accountant notes about a client."""
    secret = world.victim.note.body
    for role in (UserRole.owner, UserRole.admin, UserRole.accountant, UserRole.viewer):
        response = client.get(
            f"/api/v1/companies/{world.victim.company.id}/notes",
            headers=_attacker_headers(client, world, role),
        )
        assert response.status_code == 404, f"{role.value}: {response.status_code} {response.text}"
        assert secret not in response.text


# --------------------------------------------------------------------------
# HIGH-4 -- cross-tenant membership grant via invitation acceptance.
# --------------------------------------------------------------------------


def test_cross_tenant_invitation_cannot_be_accepted(client, world):
    """Audit HIGH-4. User.email is globally unique, not per-tenant, so a
    tenant-B admin could invite an address already belonging to a tenant-A
    user; that user then joined company.users for a company in tenant B,
    creating a cross-tenant grant that defeated require_company_access's
    membership check on every endpoint that relied on it alone."""
    db = world.db

    # Tenant B invites an address that belongs to a tenant-A user.
    victim_accountant_email = world.victim.accountant.email
    create = client.post(
        f"/api/v1/companies/{world.attacker.company.id}/invitations",
        headers=_attacker_headers(client, world, UserRole.owner),
        json={"invited_email": victim_accountant_email, "intended_role": "accountant"},
    )
    assert create.status_code == 201, create.text
    token = create.json()["raw_token"]

    members_before = {u.id for u in world.attacker.company.users}

    response = client.post(
        "/api/v1/companies/invitations/accept",
        headers=_headers(client, victim_accountant_email),
        json={"token": token},
    )
    assert response.status_code == 403, response.text

    db.refresh(world.attacker.company)
    assert {u.id for u in world.attacker.company.users} == members_before
    assert world.victim.accountant not in world.attacker.company.users

    # And the victim's accountant still cannot read the attacker's company
    # now that the cross-tenant membership was refused. Different tenant, so
    # 404 rather than 403 -- no existence leak.
    probe = client.get(
        f"/api/v1/companies/{world.attacker.company.id}/notes",
        headers=_headers(client, victim_accountant_email),
    )
    assert probe.status_code == 404, probe.text
    assert "Confidential attacker note" not in probe.text


def test_accepting_an_invitation_for_a_missing_company_is_404_not_500(client, world, db_session, monkeypatch):
    """Audit HIGH-4 second half: `company` was dereferenced with no None
    check, so an invitation whose company had gone away raised
    AttributeError/500 instead of a clean 404.

    That state is not reachable through the schema -- `company_invitations`
    has a NOT NULL foreign key to `companies`, so deleting a company that
    still has invitations raises ForeignKeyViolation (verified: an earlier
    version of this test tried exactly that and Postgres refused). The check
    is defence-in-depth against raw-SQL deletion or a future schema change,
    so it is exercised here by making the lookup return None rather than by
    corrupting referential integrity."""
    raw_token, token_hash = generate_password_reset_token()
    invitation = CompanyInvitation(
        tenant_id=world.victim.tenant.id,
        company_id=world.victim.company.id,
        invited_email=world.victim.accountant.email,
        intended_role=UserRole.accountant,
        invited_by_user_id=world.victim.owner.id,
        token_hash=token_hash,
        expires_at=datetime.now(timezone.utc) + timedelta(days=14),
    )
    db_session.add(invitation)
    db_session.commit()

    # The app under test shares this session (conftest's override_get_db), so
    # patching `get` here is enough to make the company lookup miss. Only
    # `Company` is affected -- the invitation is fetched with a query, and
    # login/get_current_user resolve the user by email query too.
    real_get = db_session.get

    def get_returning_none_for_company(model, pk, *args, **kwargs):
        if model is Company:
            return None
        return real_get(model, pk, *args, **kwargs)

    monkeypatch.setattr(db_session, "get", get_returning_none_for_company)

    response = client.post(
        "/api/v1/companies/invitations/accept",
        headers=_headers(client, world.victim.accountant.email),
        json={"token": raw_token},
    )
    assert response.status_code == 404, response.text
    assert "no longer exists" in response.json()["detail"]


# --------------------------------------------------------------------------
# Positive controls: the rightful tenant can still do everything.
# --------------------------------------------------------------------------


def test_same_tenant_financial_year_lock_and_unlock_still_work(client, world):
    headers = _headers(client, world.victim.admin.email)
    url = f"/api/v1/companies/{world.victim.company.id}/financial-years/{world.victim.financial_year.id}"

    lock = client.post(f"{url}/lock", headers=headers)
    assert lock.status_code == 200, lock.text
    assert lock.json()["is_locked"] is True

    # An admin of the same tenant who is NOT a company member must also
    # still work -- that is the legitimate admin scope the fix preserves.
    other = _headers(client, world.victim.other_admin.email)
    unlock = client.post(f"{url}/unlock", headers=other)
    assert unlock.status_code == 200, unlock.text
    assert unlock.json()["is_locked"] is False


def test_same_tenant_financial_year_listing_still_works(client, world):
    for role in (UserRole.owner, UserRole.admin, UserRole.accountant, UserRole.viewer):
        response = client.get(
            f"/api/v1/companies/{world.victim.company.id}/financial-years",
            headers=_headers(client, world.victim.emails[role]),
        )
        assert response.status_code == 200, f"{role.value}: {response.text}"
        assert [fy["year"] for fy in response.json()] == [2026]


def test_same_tenant_bulk_match_approval_still_works(client, world):
    db = world.db
    payments_before = db.query(Payment).count()

    response = client.post(
        "/api/v1/payment-matches/bulk-approve-high-confidence",
        params={"company_id": world.victim.company.id},
        headers=_headers(client, world.victim.accountant.email),
    )
    assert response.status_code == 200, response.text
    assert len(response.json()) == 1

    db.refresh(world.victim.match)
    assert world.victim.match.status == "APPROVED"
    assert world.victim.match.approved_by_user_id == world.victim.accountant.id
    assert world.victim.match.payment_id is not None
    assert db.query(Payment).count() == payments_before + 1


def test_same_tenant_notes_and_invitations_still_work(client, world):
    owner = _headers(client, world.victim.owner.email)

    notes = client.get(f"/api/v1/companies/{world.victim.company.id}/notes", headers=owner)
    assert notes.status_code == 200, notes.text
    assert len(notes.json()) == 1

    # A viewer may read notes but is not an admin/customer, so invitation
    # management stays denied -- unchanged pre-existing behaviour.
    viewer = _headers(client, world.victim.viewer.email)
    assert client.get(f"/api/v1/companies/{world.victim.company.id}/notes", headers=viewer).status_code == 200

    create = client.post(
        f"/api/v1/companies/{world.victim.company.id}/invitations",
        headers=owner,
        json={"invited_email": "newbookkeeper@victim.nl", "intended_role": "accountant"},
    )
    assert create.status_code == 201, create.text

    listed = client.get(f"/api/v1/companies/{world.victim.company.id}/invitations", headers=owner)
    assert listed.status_code == 200, listed.text
    new_id = next(i["id"] for i in listed.json() if i["invited_email"] == "newbookkeeper@victim.nl")

    revoked = client.post(
        f"/api/v1/companies/{world.victim.company.id}/invitations/{new_id}/revoke", headers=owner
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["status"] == "REVOKED"


def test_same_tenant_invitation_acceptance_still_works(client, world):
    """Cross-tenant acceptance is now rejected, but the documented
    same-tenant accountant-delegation flow must keep working."""
    db = world.db
    create = client.post(
        f"/api/v1/companies/{world.victim.company.id}/invitations",
        headers=_headers(client, world.victim.owner.email),
        json={"invited_email": world.attacker.accountant.email, "intended_role": "accountant"},
    )
    assert create.status_code == 201, create.text

    # Invite an address in the SAME tenant that is not yet a member.
    outsider = _user(db, world.victim.tenant, "outsiderbookkeeper@victim.nl", UserRole.accountant)
    db.commit()
    create2 = client.post(
        f"/api/v1/companies/{world.victim.company.id}/invitations",
        headers=_headers(client, world.victim.owner.email),
        json={"invited_email": outsider.email, "intended_role": "accountant"},
    )
    assert create2.status_code == 201, create2.text

    accept = client.post(
        "/api/v1/companies/invitations/accept",
        headers=_headers(client, outsider.email),
        json={"token": create2.json()["raw_token"]},
    )
    assert accept.status_code == 200, accept.text
    db.refresh(world.victim.company)
    assert outsider in world.victim.company.users

    # And the newly-granted accountant can now read the company's notes.
    notes = client.get(
        f"/api/v1/companies/{world.victim.company.id}/notes", headers=_headers(client, outsider.email)
    )
    assert notes.status_code == 200, notes.text
    assert len(notes.json()) == 1


def test_hash_reset_token_roundtrip_is_stable():
    """Guard on the helper the invitation-accept path depends on: the token
    hash used for lookup must be reproducible from the raw token."""
    raw, hashed = generate_password_reset_token()
    assert hash_reset_token(raw) == hashed
    assert raw not in hashed
