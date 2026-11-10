"""Re-encrypts every stored secret with the CURRENT key for its class, so a
retired key listed in a *_PREVIOUS variable can eventually be removed.

Phase 17.4 (audit 7.5). `scripts/rotate_bsn_key.py` already did this for
BSNs, but the other two secret classes had no equivalent even though their
modules accepted a *_PREVIOUS key: `app/core/token_crypto.py` (Open Banking
access/refresh tokens) and `app/core/mfa_crypto.py` (TOTP MFA secrets). The
matching `reencrypt_*_with_current_key()` functions were added to those
modules in this phase; this script drives all three.

This script does NOT rotate a key. It never reads, generates, prints or
changes any key value -- it only migrates existing CIPHERTEXT from whatever
key currently decrypts it onto whatever key is currently configured to
encrypt with it. Changing the key itself is an operator action (edit the
environment), described in docs/encryption-key-rotation.md.

Rollback: there is nothing to roll back in the database. Because the retired
key stays in *_PREVIOUS throughout, the OLD key still decrypts everything at
every point in this procedure -- both ciphertext written before it ran and
ciphertext written after. Rolling back is therefore purely an environment
change: put the old key back as the current one and drop the new key. Do not
remove a key from *_PREVIOUS until this script has run to completion and a
sample of each secret class has been verified to still work.

Never deletes a row, never writes plaintext, never prints a key or a secret.

Usage:
    .venv/bin/python scripts/rotate_encryption_keys.py --dry-run          # report counts only
    .venv/bin/python scripts/rotate_encryption_keys.py --class bsn        # one class
    .venv/bin/python scripts/rotate_encryption_keys.py --yes              # all three, for real
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `app` is importable when run directly

from sqlalchemy.orm import Session  # noqa: E402

from app.core import config as app_config  # noqa: E402
from app.core.crypto import reencrypt_bsn_with_current_key  # noqa: E402
from app.core.mfa_crypto import reencrypt_mfa_secret_with_current_key  # noqa: E402
from app.core.token_crypto import reencrypt_token_with_current_key  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.banking import BankAccount  # noqa: E402
from app.models.employee import Employee  # noqa: E402
from app.models.user import User  # noqa: E402

BATCH_SIZE = 500

# (class name, environment variable the operator must have changed, [(model, column, reencrypt fn)])
SECRET_CLASSES: dict[str, tuple[str, list[tuple[type, str, object]]]] = {
    "bsn": (
        "BSN_ENCRYPTION_KEY",
        [(Employee, "bsn_encrypted", reencrypt_bsn_with_current_key)],
    ),
    "open_banking": (
        "OPEN_BANKING_TOKEN_ENCRYPTION_KEY",
        [
            (BankAccount, "encrypted_access_token", reencrypt_token_with_current_key),
            (BankAccount, "encrypted_refresh_token", reencrypt_token_with_current_key),
        ],
    ),
    "mfa": (
        "MFA_SECRET_ENCRYPTION_KEY",
        [(User, "mfa_secret_encrypted", reencrypt_mfa_secret_with_current_key)],
    ),
}


def _refuse_if_key_is_still_the_placeholder(class_name: str, env_var: str) -> None:
    """Migrating ciphertext onto a key that is public in the repository would
    be worse than doing nothing: it would give the operator a false sense
    that a rotation had happened."""
    offenders = dict(app_config.insecure_placeholder_secrets())
    if env_var in offenders:
        raise SystemExit(
            f"Refusing to re-encrypt the '{class_name}' class: {env_var} is still the committed "
            "insecure placeholder value. Generate a real Fernet key and set it in the environment "
            "first (see the remediation hint printed at startup, or docs/encryption-key-rotation.md)."
        )


def _rotate_class(db: Session, class_name: str, dry_run: bool) -> int:
    env_var, targets = SECRET_CLASSES[class_name]
    _refuse_if_key_is_still_the_placeholder(class_name, env_var)

    total = 0
    for model, column, reencrypt in targets:
        attribute = getattr(model, column)
        rows = db.query(model).filter(attribute.isnot(None)).yield_per(BATCH_SIZE)
        count = 0
        for row in rows:
            ciphertext = getattr(row, column)
            if ciphertext is None:
                continue
            new_ciphertext = reencrypt(ciphertext)
            count += 1
            if not dry_run:
                setattr(row, column, new_ciphertext)
            if not dry_run and count % BATCH_SIZE == 0:
                db.commit()
        db.commit()
        verb = "would re-encrypt" if dry_run else "re-encrypted"
        print(f"  [{class_name}] {model.__tablename__}.{column}: {verb} {count} row(s)")
        total += count
    return total


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="report what would change, write nothing")
    parser.add_argument(
        "--class",
        dest="classes",
        action="append",
        choices=sorted(SECRET_CLASSES),
        help="restrict to one secret class (repeatable); defaults to all three",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="required to actually write; without it or --dry-run the script refuses to run",
    )
    args = parser.parse_args(argv)

    if not args.dry_run and not args.yes:
        parser.error("refusing to write without either --dry-run or --yes")

    selected = args.classes or sorted(SECRET_CLASSES)
    print(f"Environment: {app_config.settings.environment}")
    print(f"Secret classes: {', '.join(selected)}")
    print("Mode: DRY RUN (nothing will be written)" if args.dry_run else "Mode: WRITE")
    print()

    db = SessionLocal()
    try:
        grand_total = 0
        for class_name in selected:
            grand_total += _rotate_class(db, class_name, args.dry_run)
        print()
        if args.dry_run:
            print(f"Dry run complete: {grand_total} value(s) would be re-encrypted. Re-run with --yes to apply.")
        else:
            print(f"Done: {grand_total} value(s) now encrypted with the current key.")
            print(
                "Next: verify a sample of each class still works (a masked BSN displays, an MFA "
                "code verifies, an Open Banking sync succeeds) BEFORE removing any key from its "
                "*_PREVIOUS variable."
            )
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
