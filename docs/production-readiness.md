# Production readiness assessment

Honest status, not a claim of full readiness.

| Area | Status | Evidence |
|---|---|---|
| Backend tests | READY | 442 passing (`docs/phase-12-implementation.md`) |
| Frontend build/lint/types | READY | `npm run build`/`lint`, `tsc --noEmit` all clean |
| Tenant/employee isolation | READY | Extensively tested across phases; re-verified this phase |
| Session revocation | READY | New this phase, tested |
| Account lockout | READY | New this phase, tested |
| Password reset | PARTIAL | Works end-to-end except email delivery — no provider configured, token is not emailed anywhere yet |
| GDPR self-service | PARTIAL | Export + deactivation implemented; full erasure for unlinked accounts not implemented |
| Docker images | READY | Build clean, non-root, healthchecked (verified with real `docker build`) |
| Production compose | READY (config only) | Valid syntax, never deployed |
| Backup/restore | READY (manual) | Verified twice (Phase 10, Phase 12) against disposable databases; no automated schedule |
| Monitoring | PARTIAL | Structured logs + request correlation + `/ready`; no metrics backend, no alerting |
| MFA | IMPLEMENTED | Optional per-user TOTP (`docs/security.md`); verified end-to-end against a running server. No backup-code recovery path yet. |
| SBR/Digipoort submission | BLOCKED BY EXTERNAL REQUIREMENT | No PKIoverheid/Logius test certificate obtained |
| KVK lookup | SANDBOX VERIFIED | Real network call against KVK's published test sandbox |
| Open Banking | BLOCKED BY EXTERNAL REQUIREMENT | No authorised provider agreement/credentials; DNB/EBA authorization not independently re-verified |
| CI/CD | NOT IMPLEMENTED | No pipeline defined in this repo |
| TLS/reverse proxy | DOCUMENTED, NOT DEPLOYED | `docs/production-deployment.md` has a worked nginx example; not provisioned anywhere |

## Would this go live today?

No. The hard blockers are: no email provider (password reset is incomplete without it), no TLS/reverse proxy actually provisioned, no automated backup schedule, and both external integrations (government, banking) are architecturally ready but not connected to anything real. None of these are large engineering efforts — they're external dependencies (an email provider account, a domain + certificate, a cron entry, a signed agreement with a provider) that this session had no way to obtain.

## Immediate next steps, in priority order

1. Provision TLS (domain + certificate) and put the documented nginx/Caddy config in front of the stack.
2. Wire a real transactional email provider for password reset.
3. Schedule `backup_db.sh` via cron (or the platform's equivalent) and store its output encrypted off-host.
4. Request a Logius SBR test certificate (external, email-based process) to actually exercise the loonheffingen submission path end-to-end.
5. Re-verify an Open Banking provider's DNB/EBA authorization directly against the live register before signing anything.
