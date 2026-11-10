# BSN encryption key rotation

The only thing encrypted at rest in this system is the employee BSN
(`Employee.bsn_encrypted`), via Fernet symmetric encryption
(`app/core/crypto.py`). Rotation uses `cryptography.fernet.MultiFernet`
(already part of the installed `cryptography` dependency — no new
library), which is designed for exactly this: encrypt new data with one
key, accept decryption with several.

**Never rotate by simply changing `BSN_ENCRYPTION_KEY` and discarding the
old value.** Every BSN already stored was encrypted with the old key —
discarding it without the procedure below makes every existing BSN
permanently undecryptable.

## How it works

- `BSN_ENCRYPTION_KEY` — the current key. All **new** encryption uses this key.
- `BSN_ENCRYPTION_KEY_PREVIOUS` — comma-separated older key(s), still
  accepted for **decryption** only. Empty when no rotation is in progress.

`app/core/crypto.py`'s `_fernet()` builds a `MultiFernet([current] + previous)`
— decryption tries each key in order, encryption always uses the first
(current) one.

## Rotation procedure

1. **Generate a new key:**
   ```
   .venv/bin/python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```
2. **Back up the database first** (see `scripts/backup_db.sh`) — standard
   precaution before any production config change, not specific to this
   procedure.
3. **Move the current key to previous, set the new key as current** in the
   environment (e.g. `.env` or the deployment's secret store):
   ```
   BSN_ENCRYPTION_KEY_PREVIOUS=<old key>
   BSN_ENCRYPTION_KEY=<new key>
   ```
   Restart the app. At this point: existing BSNs still decrypt (via the
   previous key), and any newly-stored BSN uses the new key. Nothing is
   broken by this step alone, and it's safe to leave the system in this
   state indefinitely if needed.
4. **Migrate existing ciphertext onto the new key:**
   ```
   .venv/bin/python scripts/rotate_bsn_key.py --dry-run   # review the count first
   .venv/bin/python scripts/rotate_bsn_key.py              # then apply
   ```
   This re-encrypts every stored BSN with the current key only, using
   `app.core.crypto.reencrypt_bsn_with_current_key()` (decrypts with
   whichever key matches, re-encrypts with the current key).
5. **Verify** a handful of employee BSNs still display correctly (masked,
   via the normal employee API) before proceeding.
6. **Only once step 4 has been applied and verified**, remove the old key:
   ```
   BSN_ENCRYPTION_KEY_PREVIOUS=
   ```
   Restart the app. The old key can now be safely discarded/destroyed.

## What this does NOT do

- It does not rotate `JWT_SECRET` (session tokens, not stored data —
  rotating it just invalidates existing sessions, no migration needed:
  change the value and restart).
- It does not automatically schedule or remind anyone to rotate — this is
  a manual, deliberate operational procedure, run when there's a specific
  reason (suspected compromise, routine policy, offboarding someone who
  had access to the old key).
- It never touches a row that isn't `Employee.bsn_encrypted` — nothing
  else in this system is encrypted at rest.
