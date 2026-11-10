# Accountant ecosystem & multi-company platform

## The gap this closes

The architecture audit at the start of Phase 14 found that
`app.models.user.user_companies` — the table `require_company_access`
checks for every non-admin role — had **no API anywhere that could
populate it**. A business owner had no way to actually grant their
accountant (or anyone else) access to a company; `user_companies` could
only be populated by direct database manipulation. This is the real
substance behind "accountant ecosystem" and "multi-company
permissions" in the Phase 14 brief.

## Company access invitations

`app/models/company_invitation.py` + the endpoints in
`app/api/v1/companies.py` (`/companies/{id}/invitations`,
`/companies/{id}/access`, `/companies/invitations/accept`). Same
one-row-per-request, SHA-256-token-hash-only pattern as
`PasswordResetToken`.

- **Who can invite**: the company's admin or its customer
  (business-owner) persona — not every accountant who happens to have
  access, since granting further access is an ownership decision.
- **Cross-tenant by design**: accepting an invitation adds the
  *accepting user* (who may belong to an entirely different tenant —
  their own accounting firm's account) to the company's `users`
  relationship. It does **not** move them into the inviting tenant or
  create a new user record. This is the actual multi-company
  mechanism: one accountant user, several client companies across
  several tenants, each access grant explicit and revocable.
- **Acceptance requires an existing account matching the invited
  email** — this is access-grant-only, deliberately not a signup flow,
  so a token alone can never create an account.
- **Revocation**: a pending invitation can be revoked before
  acceptance; existing access can be revoked afterward
  (`POST /companies/{id}/access/{user_id}/revoke`), both audit-logged.

## What this does NOT change

- **No per-company role.** `User.role` is still one value for the whole
  account, not scoped per company. An accepted invitation's
  `intended_role` is recorded on the invitation for context but does
  not override the accepting user's own role. Introducing true
  per-company roles would be a larger schema change (a role column on
  `user_companies` itself, with every `require_company_access`/
  `require_editor`-style check updated to read it) — out of scope for
  this phase, stated honestly rather than half-built.
- **Admin still bypasses everything** within their own tenant
  (`require_company_access`'s existing admin-bypass clause, unchanged).

## Consolidated reporting

`GET /dashboard/accountant` (Phase 8, unchanged) already gives a
portfolio view across every company a user can access — revenue, net
profit, VAT payable, and reconciliation status per company, surfaced in
`/financial-overview`. Every row is keyed by `company_id`/`company_name`,
so a consolidated number is always traceable back to its source company
— no company's ledger or tax declaration is ever merged with another's
at the data layer; only the frontend table presents them side by side.

## Status

| Capability | Status |
|---|---|
| Company access invitations (invite/accept/revoke) | IMPLEMENTED, tested (7 tests) |
| Cross-tenant accountant delegation | IMPLEMENTED (invitation accept works across tenants) |
| Per-company role (vs. per-account role) | NOT IMPLEMENTED |
| Consolidated portfolio reporting | IMPLEMENTED (Phase 8, re-verified, company-traceable) |
| Dedicated "Accountant Workspace" page distinct from Financial Overview | NOT IMPLEMENTED this phase -- the existing portfolio dashboard + the new Team Access panel on each company's detail page cover the same ground; a separate page was judged to duplicate rather than add capability given the time available |
