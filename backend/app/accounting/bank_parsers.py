"""Deterministic bank statement parsers: CAMT.053, CAMT.054, MT940, CSV.

No live Open Banking provider connection exists in this build (see
docs/bank-integration.md) -- these are the real, working import path.
Every parser returns the same ParsedBankTransaction shape so the importer
and the deduplication logic never need to know which format a statement
came from.
"""

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from xml.etree import ElementTree


class BankFileParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedBankTransaction:
    external_transaction_id: str | None
    booking_date: date
    value_date: date | None
    amount: Decimal  # signed: positive = incoming (credit), negative = outgoing (debit)
    currency: str
    counterparty_name: str | None
    counterparty_iban: str | None
    payment_reference: str | None
    description: str | None
    raw_data: dict

    def dedupe_hash(self) -> str:
        """Deterministic identity for duplicate-import prevention. Prefers the
        bank's own reference when present; falls back to a content hash of
        the fields a re-imported statement would reproduce identically."""
        if self.external_transaction_id:
            basis = f"ext:{self.external_transaction_id}"
        else:
            basis = "|".join(
                [
                    str(self.booking_date),
                    str(self.amount),
                    self.currency,
                    self.counterparty_iban or "",
                    self.payment_reference or "",
                    (self.description or "")[:200],
                ]
            )
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def _local_tag(tag: str) -> str:
    return tag.split("}")[-1]


def _find_text(elem, *local_names: str) -> str | None:
    """Namespace-agnostic descendant search -- CAMT XML namespaces vary by
    minor version; matching on the local tag name only is robust to that."""
    for child in elem.iter():
        if _local_tag(child.tag) in local_names and child.text:
            return child.text.strip()
    return None


def _parse_camt_entries(root, entry_tag: str = "Ntry") -> list[ParsedBankTransaction]:
    transactions = []
    for entry in root.iter():
        if _local_tag(entry.tag) != entry_tag:
            continue

        amount_text = _find_text(entry, "Amt")
        if amount_text is None:
            continue
        try:
            amount = Decimal(amount_text)
        except InvalidOperation:
            continue

        currency = "EUR"
        for child in entry.iter():
            if _local_tag(child.tag) == "Amt" and "Ccy" in child.attrib:
                currency = child.attrib["Ccy"]
                break

        direction = _find_text(entry, "CdtDbtInd") or "CRDT"
        if direction.upper() == "DBIT":
            amount = -amount

        booking_date_text = None
        value_date_text = None
        for child in entry:
            if _local_tag(child.tag) == "BookgDt":
                booking_date_text = _find_text(child, "Dt", "DtTm")
            elif _local_tag(child.tag) == "ValDt":
                value_date_text = _find_text(child, "Dt", "DtTm")
        if booking_date_text is None:
            booking_date_text = _find_text(entry, "Dt") or value_date_text
        if booking_date_text is None:
            continue

        booking_date = _as_date(booking_date_text)
        value_date = _as_date(value_date_text) if value_date_text else None

        external_id = _find_text(entry, "AcctSvcrRef", "EndToEndId")
        reference = _find_text(entry, "Ustrd")
        counterparty_name = _find_text(entry, "Nm")
        counterparty_iban = _find_text(entry, "IBAN")

        transactions.append(
            ParsedBankTransaction(
                external_transaction_id=external_id,
                booking_date=booking_date,
                value_date=value_date,
                amount=amount,
                currency=currency,
                counterparty_name=counterparty_name,
                counterparty_iban=counterparty_iban,
                payment_reference=reference,
                description=reference,
                raw_data={
                    "amount": amount_text,
                    "direction": direction,
                    "booking_date": booking_date_text,
                    "external_id": external_id,
                    "counterparty_name": counterparty_name,
                    "counterparty_iban": counterparty_iban,
                    "reference": reference,
                },
            )
        )
    return transactions


# Phase 17.4 (audit 7.19) -- XXE / entity-expansion hardening.
#
# `<!DOCTYPE` and `<!ENTITY` are matched case-insensitively because XML
# keywords are, and the scan is a single regex over the buffer so it costs
# no extra allocation on a 20 MB upload.
_DTD_PROBE = re.compile(rb"<!(?:doctype|entity)", re.IGNORECASE)


def _safe_fromstring(content: bytes, label: str) -> ElementTree.Element:
    """Parse XML after rejecting any document type declaration.

    CAMT.053/054 bank statements never legitimately carry a DOCTYPE -- they
    identify themselves with `xmlns` attributes on the root element. A
    DOCTYPE is therefore either a malformed file or an attack, and refusing
    it outright removes the whole entity-expansion ("billion laughs") class
    before the parser is ever reached.

    Why an explicit check rather than relying on the stdlib: stock
    `xml.etree.ElementTree` installs no external-entity handler, so
    file-disclosure XXE was never reachable here -- but internal-entity
    expansion is blocked only INCIDENTALLY, by the bundled expat's
    amplification limit. CPython 3.12 aborts at roughly 100x amplification;
    3.9 does not block it at all. `requirements.txt` pins no Python version,
    so the guarantee would silently depend on which interpreter the image was
    built with. This makes it a property of the code instead.

    Residual note: with a single-process uvicorn worker and a 20 MB upload
    cap, ~100x amplification before expat aborts was still enough to OOM the
    service. Rejecting the DTD removes that path entirely.
    """
    if _DTD_PROBE.search(content):
        raise BankFileParseError(
            f"Invalid {label} XML: bank statements must not contain a DOCTYPE or ENTITY "
            "declaration; the file was rejected before parsing"
        )
    return ElementTree.fromstring(content)


def parse_camt053(content: bytes) -> list[ParsedBankTransaction]:
    try:
        root = _safe_fromstring(content, "CAMT.053")
    except ElementTree.ParseError as exc:
        raise BankFileParseError(f"Invalid CAMT.053 XML: {exc}") from exc
    transactions = _parse_camt_entries(root)
    if not transactions:
        raise BankFileParseError("No entries found in CAMT.053 file")
    return transactions


def parse_camt054(content: bytes) -> list[ParsedBankTransaction]:
    try:
        root = _safe_fromstring(content, "CAMT.054")
    except ElementTree.ParseError as exc:
        raise BankFileParseError(f"Invalid CAMT.054 XML: {exc}") from exc
    transactions = _parse_camt_entries(root)
    if not transactions:
        raise BankFileParseError("No entries found in CAMT.054 file")
    return transactions


# MT940 (SWIFT FIN): line-based. This covers the common subset used by Dutch
# banks (:61: transaction lines + :86: remittance info) -- not the full SWIFT
# spec (e.g. exotic transaction-type codes in :61: are not individually
# decoded, just carried through as raw_data). Extend _MT940_61_RE if a real
# statement from a specific bank doesn't match.
_MT940_61_RE = re.compile(
    r"^:61:(?P<value_date>\d{6})(?P<booking_date>\d{4})?"
    r"(?P<sign>[DC]R?)(?P<amount>\d+,\d{2})(?P<type>\w{1,4})?(?P<ref>\S*)"
)


def parse_mt940(content: bytes) -> list[ParsedBankTransaction]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError:
        try:
            text = content.decode("latin-1")
        except UnicodeDecodeError as exc:
            raise BankFileParseError("MT940 file is not valid text") from exc

    lines = [line.rstrip() for line in text.splitlines()]
    transactions: list[ParsedBankTransaction] = []
    current_year = datetime.now().year
    i = 0
    found_any_61 = False
    while i < len(lines):
        line = lines[i]
        if line.startswith(":61:"):
            found_any_61 = True
            match = _MT940_61_RE.match(line)
            if not match:
                i += 1
                continue
            value_date = _mt940_date(match.group("value_date"), current_year)
            booking_suffix = match.group("booking_date")
            booking_date = _mt940_date(match.group("value_date")[:2] + booking_suffix, current_year) if booking_suffix else value_date
            amount = Decimal(match.group("amount").replace(",", "."))
            if match.group("sign").startswith("D"):
                amount = -amount
            reference = match.group("ref") or None

            description = None
            j = i + 1
            while j < len(lines) and lines[j].startswith(":86:"):
                description = lines[j][4:].strip()
                j += 1
            while j < len(lines) and not lines[j].startswith(":"):
                description = f"{description or ''} {lines[j].strip()}".strip()
                j += 1

            transactions.append(
                ParsedBankTransaction(
                    external_transaction_id=reference,
                    booking_date=booking_date,
                    value_date=value_date,
                    amount=amount,
                    currency="EUR",
                    counterparty_name=None,
                    counterparty_iban=None,
                    payment_reference=reference,
                    description=description,
                    raw_data={"line": line, "description": description},
                )
            )
            i = j
        else:
            i += 1

    if not found_any_61:
        raise BankFileParseError("No :61: transaction lines found in MT940 file")
    return transactions


def _mt940_date(yymmdd: str, fallback_year: int) -> date:
    yy, mm, dd = yymmdd[:2], yymmdd[2:4], yymmdd[4:6]
    year = 2000 + int(yy)
    return date(year, int(mm), int(dd))


# CSV: flexible column matching since Dutch bank exports (ING/ABN AMRO/
# Rabobank/...) all use different header names for the same fields.
_CSV_COLUMN_ALIASES = {
    "booking_date": {"date", "datum", "boekdatum", "transactiedatum"},
    "amount": {"amount", "bedrag", "bedrag (eur)"},
    "currency": {"currency", "munt", "valuta"},
    "counterparty_name": {"counterparty", "naam", "naam / omschrijving", "tegenpartij"},
    "counterparty_iban": {"iban", "tegenrekening", "rekening tegenpartij"},
    "reference": {"reference", "betalingskenmerk", "kenmerk"},
    "description": {"description", "omschrijving", "omschrijving-1", "mededelingen"},
}


def _normalize_header(h: str) -> str:
    return h.strip().lower()


def parse_csv(content: bytes) -> list[ParsedBankTransaction]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BankFileParseError("CSV file is not valid UTF-8 text") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise BankFileParseError("CSV file has no header row")

    normalized = {_normalize_header(h): h for h in reader.fieldnames}
    column_map = {}
    for field, aliases in _CSV_COLUMN_ALIASES.items():
        for norm, original in normalized.items():
            if norm in aliases:
                column_map[field] = original
                break

    if "booking_date" not in column_map or "amount" not in column_map:
        raise BankFileParseError("CSV file is missing a recognizable date or amount column")

    transactions = []
    for row in reader:
        raw_date = row.get(column_map["booking_date"], "")
        raw_amount = row.get(column_map["amount"], "")
        if not raw_date or not raw_amount:
            continue
        try:
            amount = Decimal(raw_amount.replace(",", ".").replace(" ", ""))
        except InvalidOperation:
            continue
        booking_date = _parse_flexible_date(raw_date)
        if booking_date is None:
            continue

        transactions.append(
            ParsedBankTransaction(
                external_transaction_id=None,
                booking_date=booking_date,
                value_date=None,
                amount=amount,
                currency=row.get(column_map.get("currency", ""), "EUR") or "EUR",
                counterparty_name=row.get(column_map.get("counterparty_name", "")) or None,
                counterparty_iban=row.get(column_map.get("counterparty_iban", "")) or None,
                payment_reference=row.get(column_map.get("reference", "")) or None,
                description=row.get(column_map.get("description", "")) or None,
                raw_data=dict(row),
            )
        )
    if not transactions:
        raise BankFileParseError("No valid transaction rows found in CSV file")
    return transactions


def _parse_flexible_date(value: str) -> date | None:
    value = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _as_date(value: str) -> date:
    value = value.strip()
    if "T" in value:
        value = value.split("T")[0]
    return date.fromisoformat(value)
