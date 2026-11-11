"""Format + checksum validation for Dutch business identifiers. Pure
functions, no I/O -- the KVK API (app.services.kvk_provider) is the only
authoritative source for *existence*; these only reject values that cannot
possibly be valid, so a typo is caught before it is saved.

Rules implemented (all public, from Belastingdienst / KVK documentation):
- KVK number: exactly 8 digits.
- RSIN: 9 digits passing the elfproef (same test as the old BSN rule).
- BTW-id: "NL" + 9 digits + "B" + 2 digits. Since 2020 sole traders get an
  id whose digits are random, so the only checksum that holds for EVERY
  btw-id is the ISO 7064 mod-97 test over the whole string (letters mapped
  A=10..Z=35, "NL" included). Legal entities' ids still also pass the
  elfproef on the 9 digits, but that is not required here.
- IBAN: ISO 13616 mod-97 over the rearranged string; NL IBANs are 18 chars.
"""

import re

_KVK_RE = re.compile(r"^\d{8}$")
_RSIN_RE = re.compile(r"^\d{9}$")
_BTW_RE = re.compile(r"^NL\d{9}B\d{2}$")
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{11,30}$")


def normalize(value: str | None) -> str:
    return re.sub(r"[\s.\-]", "", (value or "")).upper()


def _elfproef(digits: str) -> bool:
    # Weighted sum 9..2 for the first eight digits, MINUS the ninth, divisible by 11.
    total = sum(int(d) * w for d, w in zip(digits[:8], range(9, 1, -1))) - int(digits[8])
    return total % 11 == 0


def _mod97(value: str) -> int:
    numeric = "".join(str(ord(c) - 55) if c.isalpha() else c for c in value)
    remainder = 0
    for chunk_start in range(0, len(numeric), 9):
        remainder = int(str(remainder) + numeric[chunk_start:chunk_start + 9]) % 97
    return remainder


def is_valid_kvk(value: str | None) -> bool:
    return bool(_KVK_RE.match(normalize(value)))


def is_valid_rsin(value: str | None) -> bool:
    v = normalize(value)
    return bool(_RSIN_RE.match(v)) and _elfproef(v)


def is_valid_btw(value: str | None) -> bool:
    v = normalize(value)
    if not _BTW_RE.match(v):
        return False
    # ISO 7064 mod 97-10 over the whole id: valid when the remainder is 1.
    return _mod97(v) == 1


def is_valid_iban(value: str | None) -> bool:
    v = normalize(value)
    if not _IBAN_RE.match(v):
        return False
    if v.startswith("NL") and len(v) != 18:
        return False
    return _mod97(v[4:] + v[:4]) == 1
