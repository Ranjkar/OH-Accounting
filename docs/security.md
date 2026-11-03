# Security review (Phase 12)

## Authentication & session management

- Passwords: bcrypt via passlib (`app/core/security.py`), never stored or logged in plaintext.
- JWTs are stateless but revocable: every token carries a `ver` claim (the user's `token_version` at issue time). `/auth/logout` and `/auth/me/deactivate` both bump `token_version`, instantly invalidating every outstanding token for that account — verified by test (`test_logout_revokes_the_token_immediately`).
- Account lockout: 5 consecutive failed logins (configurable, `MAX_FAILED_LOGIN_ATTEMPTS`) locks the account for 15 minutes (`ACCOUNT_LOCKOUT_MINUTES`), logged to `AuditLog`. Successful login resets the counter.
- Password reset: request/confirm flow, SHA-256-hashed single-use tokens (never the raw token) with a 30-minute expiry. **No email provider is configured** — the reset token is not emailed anywhere; this is a documented gap, not hidden behind a fake "email sent" response. Wiring a real transactional-email provider is a prerequisite before exposing this publicly.
- MFA (Phase 13): optional per-user TOTP, RFC 6238, implemented with the stdlib (`hmac`/`hashlib`/`base64`/`struct` -- no new dependency, see `app/core/totp.py`). `POST /auth/mfa/setup` issues an unsaved secret + `otpauth://` provisioning URI; `POST /auth/mfa/enable` only persists it (encrypted) once a real generated code is verified, so an unconfirmed secret is never stored. The encrypted-at-rest secret uses a THIRD, purpose-isolated Fernet key (`app/core/mfa_crypto.py`), separate from the BSN key and the Open Banking token key -- a compromised key only ever exposes one secret class. Login returns `{"mfa_required": true, "access_token": null}` when a code is needed instead of issuing a token; verified end-to-end against a real running server (setup → enable → login without/with wrong/with correct code → disable), not just unit-tested. **Known limitation:** no backup/recovery codes -- a lost authenticator device requires an operator to clear `mfa_enabled` directly in the database.
- Rate limiting: in-memory, per-IP, per-scope (`app/core/rate_limit.py`) on login, password-reset-request, upload, batch endpoints — pre-existing from Phase 6/10, still in effect.

## Authorization / tenant isolation

- Every company-scoped query goes through `require_company_access` (admin bypasses; everyone else checked against `user_companies`). Extensively tested across phases (`test_*_api.py` cross-tenant tests).
- Employee self-service (`/me/*`) is scoped by `get_current_employee`, which resolves the Employee linked via `linked_user_id` — an employee-role account is never added to `user_companies`, so it's rejected from every company-wide endpoint by construction, not by an extra check that could be forgotten on a new route.

## OWASP review

| Risk | Status |
|---|---|
| SQL injection | Not applicable — SQLAlchemy ORM/Core parameterized queries throughout, no raw string-interpolated SQL found (grepped). |
| XSS | React escapes by default; grepped for `dangerouslySetInnerHTML` across the frontend — zero occurrences. |
| CSRF | Not applicable — auth is a Bearer token in the `Authorization` header (localStorage-held), never a cookie; CSRF requires ambient credentials a browser sends automatically, which this app never relies on. |
| Broken access control / IDOR | `require_company_access` / `get_current_employee` pattern audited above; Phase 11's employee self-service tests specifically call the API directly as one employee attempting another's payslip (404) and a forged timesheet submission (403). |
| Insecure file uploads | Already solid before this phase: magic-byte content sniffing (never trusts client MIME/extension), XLSX payloads are actually parsed with openpyxl to confirm validity, filenames sanitized to a safe charset and length-capped, storage paths built server-side from integer IDs (`app/services/file_validation.py`, `app/services/document_intake.py`). |
| Security misconfiguration | `JWT_SECRET`/`BSN_ENCRYPTION_KEY`/`OPEN_BANKING_TOKEN_ENCRYPTION_KEY` all warn loudly at startup if left at their insecure placeholder; CORS origin allow-list is explicit, never `*`. |
| Sensitive data exposure | See below. |
| Weak authentication | Lockout + rate limiting above. |

## Sensitive data

- **Never logged** (grepped every `logger.*` call site against password/bsn/token/secret — zero matches): passwords, BSNs, JWTs, bank tokens.
- BSN: Fernet-encrypted at rest (`app/core/crypto.py`), only ever displayed masked (`******789`), never passed to the AI assistant.
- Open Banking tokens: Fernet-encrypted with a **separate** key (`app/core/token_crypto.py`) from BSN — a compromised key never exposes both secret classes.
- Both encryption keys support rotation via `MultiFernet` without breaking existing ciphertext (`docs/encryption-key-rotation.md`).
- `/health` and `/ready` return only `{"status": ...}` — no schema version, no stack trace, no internal detail, even on failure.
