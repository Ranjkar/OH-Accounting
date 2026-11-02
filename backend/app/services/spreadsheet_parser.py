"""Deterministic parsing of XLSX/CSV rows into line items. No AI involved —
the data is already structured, so we just map columns by best-effort header match."""

from io import BytesIO

import pandas as pd

from app.models.enums import DocumentType

COLUMN_ALIASES = {
    "description": {"description", "omschrijving", "desc", "item"},
    "quantity": {"quantity", "qty", "aantal"},
    "unit_price": {"unit_price", "price", "prijs", "stukprijs"},
    "net_amount": {"net_amount", "net", "amount_excl_vat", "bedrag excl btw", "excl btw"},
    "vat_rate": {"vat_rate", "vat_percentage", "btw", "btw %", "btw%", "vat %", "vat%"},
    "vat_amount": {"vat_amount", "btw bedrag", "vat"},
    "gross_amount": {"gross_amount", "total", "totaal", "bedrag incl btw", "incl btw", "amount"},
}

BANK_STATEMENT_HINTS = {"saldo", "balance", "iban", "tegenrekening", "valutadatum"}


def _normalize(col: str) -> str:
    return str(col).strip().lower()


def _match_column(columns: list[str], aliases: set[str]) -> str | None:
    normalized = {c: _normalize(c) for c in columns}
    for col, norm in normalized.items():
        if norm in aliases:
            return col
    return None


def parse_rows(content: bytes, kind: str) -> tuple[list[dict], DocumentType]:
    if kind == "csv":
        df = pd.read_csv(BytesIO(content))
    else:
        df = pd.read_excel(BytesIO(content), engine="openpyxl")

    columns = list(df.columns)
    column_map = {field: _match_column(columns, aliases) for field, aliases in COLUMN_ALIASES.items()}

    normalized_columns = {_normalize(c) for c in columns}
    document_type = (
        DocumentType.bank_statement if normalized_columns & BANK_STATEMENT_HINTS else DocumentType.other
    )

    rows = []
    for idx, row in df.iterrows():
        entry = {"line_number": idx + 1, "source_ref": f"row {idx + 2}"}  # +2: header + 1-indexed
        for field, col in column_map.items():
            if col is None:
                entry[field] = None
                continue
            value = row[col]
            entry[field] = None if pd.isna(value) else value
        rows.append(entry)
    return rows, document_type
