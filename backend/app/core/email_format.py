"""Shape check for free-text email fields that pydantic does not already
type as EmailStr (the setup draft stores its answers as a plain JSON dict).
Deliberately permissive about the local/domain grammar -- deliverability is
the mail provider's job -- but strict enough to keep "info@" out of the
company profile. Mirrors the client check in frontend/lib/company-setup.ts.
"""

import re

_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def is_valid_email(value: str | None) -> bool:
    if not value:
        return False
    value = value.strip()
    return len(value) <= 254 and bool(_EMAIL_RE.match(value))
