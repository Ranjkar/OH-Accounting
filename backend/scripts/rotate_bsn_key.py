"""Re-encrypts every stored BSN with the current BSN_ENCRYPTION_KEY, so a
retired key in BSN_ENCRYPTION_KEY_PREVIOUS can eventually be removed.

Safe to run while the retired key is still listed in
BSN_ENCRYPTION_KEY_PREVIOUS -- app.core.crypto.reencrypt_bsn_with_current_key
decrypts with whichever key (current or previous) matches, and always
re-encrypts with the current key only. It never guesses a key and never
touches a row that isn't a BSN. See docs/encryption-key-rotation.md for
the full procedure this script is one step of.

Usage: .venv/bin/python scripts/rotate_bsn_key.py [--dry-run]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so `app` is importable when run directly

from app.core.crypto import reencrypt_bsn_with_current_key  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.employee import Employee  # noqa: E402


def main(dry_run: bool) -> None:
    db = SessionLocal()
    try:
        employees = db.query(Employee).filter(Employee.bsn_encrypted.isnot(None)).all()
        print(f"Found {len(employees)} employee(s) with a stored BSN.")
        for employee in employees:
            new_ciphertext = reencrypt_bsn_with_current_key(employee.bsn_encrypted)
            if dry_run:
                print(f"  [dry-run] employee {employee.id}: would re-encrypt")
                continue
            employee.bsn_encrypted = new_ciphertext
        if not dry_run:
            db.commit()
            print("Done -- all BSNs now encrypted with the current key.")
        else:
            print("Dry run complete -- no changes written. Re-run without --dry-run to apply.")
    finally:
        db.close()


if __name__ == "__main__":
    main(dry_run="--dry-run" in sys.argv)
