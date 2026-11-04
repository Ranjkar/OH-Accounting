"""Shared redaction for AuditLog before/after snapshots (Phase 15). A
snapshot is typically built from `{k: getattr(obj, k) for k in changed_keys}`
or a request payload's `model_dump()` -- this strips any key that could
carry a secret before it reaches the database, rather than trusting every
call site to remember to exclude it by hand.

Matching is substring-based on the lowercased key name, deliberately broad
(catches `hashed_password`, `new_password`, `mfa_secret_encrypted`,
`bsn_encrypted`, `encrypted_access_token`, `token_hash`, etc.) since a
false positive here only means a field reads "[REDACTED]" in the audit
trail -- a false negative means a secret leaks into a permanent record.
"""

_SENSITIVE_SUBSTRINGS = (
    "password",
    "secret",
    "token",
    "hashed_",
    "encrypted",
    "bsn",
    "mfa_",
    "credential",
    "iban",
    "api_key",
    "webhook_secret",
    "private_key",
)

REDACTED = "[REDACTED]"


def redact(snapshot: dict | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        key: REDACTED if any(s in key.lower() for s in _SENSITIVE_SUBSTRINGS) else value
        for key, value in snapshot.items()
    }
