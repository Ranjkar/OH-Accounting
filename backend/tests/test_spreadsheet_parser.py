from io import BytesIO

import openpyxl

from app.models.enums import DocumentType
from app.services.spreadsheet_parser import parse_rows


def test_parse_csv_maps_known_columns():
    csv_content = (
        "description,quantity,net_amount,vat_rate,vat_amount,gross_amount\n"
        "Consulting,1,100,21,21,121\n"
        "Hosting,2,50,21,10.5,60.5\n"
    ).encode("utf-8")
    rows, doc_type = parse_rows(csv_content, "csv")
    assert doc_type == DocumentType.other
    assert len(rows) == 2
    assert rows[0]["description"] == "Consulting"
    assert rows[0]["net_amount"] == 100
    assert rows[0]["source_ref"] == "row 2"


def test_parse_csv_detects_bank_statement_columns():
    csv_content = "datum,omschrijving,bedrag,saldo\n2026-01-01,Payment,100,1000\n".encode("utf-8")
    _, doc_type = parse_rows(csv_content, "csv")
    assert doc_type == DocumentType.bank_statement


def test_parse_xlsx_roundtrip():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["description", "net_amount", "vat_rate", "vat_amount", "gross_amount"])
    ws.append(["Office supplies", 40, 21, 8.4, 48.4])
    buf = BytesIO()
    wb.save(buf)

    rows, _ = parse_rows(buf.getvalue(), "xlsx")
    assert len(rows) == 1
    assert rows[0]["description"] == "Office supplies"
    assert rows[0]["gross_amount"] == 48.4
