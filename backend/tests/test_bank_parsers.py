from decimal import Decimal

import pytest

from app.accounting.bank_parsers import (
    BankFileParseError,
    parse_camt053,
    parse_camt054,
    parse_csv,
    parse_mt940,
)

CAMT053_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Acct><Id><IBAN>NL91ABNA0417164300</IBAN></Id></Acct>
      <Ntry>
        <Amt Ccy="EUR">1210.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-02-10</Dt></BookgDt>
        <ValDt><Dt>2026-02-10</Dt></ValDt>
        <AcctSvcrRef>REF-0001</AcctSvcrRef>
        <NtryDtls>
          <TxDtls>
            <RmtInf><Ustrd>Invoice INV-2026-001</Ustrd></RmtInf>
            <RltdPties>
              <Dbtr><Nm>Klant Retail B.V.</Nm></Dbtr>
              <DbtrAcct><Id><IBAN>NL80RABO0123456789</IBAN></Id></DbtrAcct>
            </RltdPties>
          </TxDtls>
        </NtryDtls>
      </Ntry>
      <Ntry>
        <Amt Ccy="EUR">45.50</Amt>
        <CdtDbtInd>DBIT</CdtDbtInd>
        <BookgDt><Dt>2026-02-11</Dt></BookgDt>
        <ValDt><Dt>2026-02-11</Dt></ValDt>
        <AcctSvcrRef>REF-0002</AcctSvcrRef>
        <NtryDtls>
          <TxDtls>
            <RmtInf><Ustrd>Office supplies</Ustrd></RmtInf>
            <RltdPties>
              <Cdtr><Nm>Kantoor Leveranciers B.V.</Nm></Cdtr>
              <CdtrAcct><Id><IBAN>NL70INGB0123456789</IBAN></Id></CdtrAcct>
            </RltdPties>
          </TxDtls>
        </NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""

CAMT054_SAMPLE = CAMT053_SAMPLE.replace("BkToCstmrStmt", "BkToCstmrDbtCdtNtfctn").replace(
    "<Stmt>", "<Ntfctn>"
).replace("</Stmt>", "</Ntfctn>")

MT940_SAMPLE = (
    ":20:STMT0001\r\n"
    ":25:NL91ABNA0417164300\r\n"
    ":28C:1/1\r\n"
    ":60F:C260201EUR1000,00\r\n"
    ":61:2602100210CR1210,00NTRFREF-0001\r\n"
    ":86:Invoice INV-2026-001 from Klant Retail B.V.\r\n"
    ":61:2602110211DR45,50NTRFREF-0002\r\n"
    ":86:Office supplies payment\r\n"
    ":62F:C260211EUR2164,50\r\n"
)

CSV_SAMPLE = (
    "Datum,Bedrag,Naam / Omschrijving,Tegenrekening,Omschrijving-1\n"
    "2026-02-10,1210.00,Klant Retail B.V.,NL80RABO0123456789,Invoice INV-2026-001\n"
    "2026-02-11,-45.50,Kantoor Leveranciers B.V.,NL70INGB0123456789,Office supplies\n"
)


def test_parse_camt053_extracts_both_entries_with_correct_sign():
    transactions = parse_camt053(CAMT053_SAMPLE.encode("utf-8"))
    assert len(transactions) == 2

    credit = transactions[0]
    assert credit.amount == Decimal("1210.00")
    assert credit.currency == "EUR"
    assert credit.counterparty_name == "Klant Retail B.V."
    assert credit.counterparty_iban == "NL80RABO0123456789"
    assert credit.external_transaction_id == "REF-0001"
    assert credit.booking_date.isoformat() == "2026-02-10"

    debit = transactions[1]
    assert debit.amount == Decimal("-45.50")  # DBIT -> negative
    assert debit.counterparty_name == "Kantoor Leveranciers B.V."


def test_parse_camt053_rejects_invalid_xml():
    with pytest.raises(BankFileParseError):
        parse_camt053(b"not xml at all")


def test_parse_camt053_rejects_xml_with_no_entries():
    with pytest.raises(BankFileParseError):
        parse_camt053(b"<Document><BkToCstmrStmt><Stmt></Stmt></BkToCstmrStmt></Document>")


def test_parse_camt054_handles_notification_variant():
    transactions = parse_camt054(CAMT054_SAMPLE.encode("utf-8"))
    assert len(transactions) == 2
    assert transactions[0].amount == Decimal("1210.00")


def test_parse_mt940_extracts_transactions_with_correct_sign():
    transactions = parse_mt940(MT940_SAMPLE.encode("utf-8"))
    assert len(transactions) == 2

    credit = transactions[0]
    assert credit.amount == Decimal("1210.00")
    assert credit.booking_date.isoformat() == "2026-02-10"
    assert "INV-2026-001" in (credit.description or "")

    debit = transactions[1]
    assert debit.amount == Decimal("-45.50")


def test_parse_mt940_rejects_file_without_transaction_lines():
    with pytest.raises(BankFileParseError):
        parse_mt940(b":20:STMT0001\r\n:25:NL91ABNA0417164300\r\n")


def test_parse_csv_with_dutch_column_names():
    transactions = parse_csv(CSV_SAMPLE.encode("utf-8"))
    assert len(transactions) == 2
    assert transactions[0].amount == Decimal("1210.00")
    assert transactions[0].counterparty_name == "Klant Retail B.V."
    assert transactions[1].amount == Decimal("-45.50")


def test_parse_csv_rejects_file_without_recognizable_columns():
    with pytest.raises(BankFileParseError):
        parse_csv(b"foo,bar\n1,2\n")


def test_dedupe_hash_is_stable_for_identical_transaction():
    t1 = parse_csv(CSV_SAMPLE.encode("utf-8"))[0]
    t2 = parse_csv(CSV_SAMPLE.encode("utf-8"))[0]
    assert t1.dedupe_hash() == t2.dedupe_hash()


def test_dedupe_hash_differs_for_different_amounts():
    rows = parse_csv(CSV_SAMPLE.encode("utf-8"))
    assert rows[0].dedupe_hash() != rows[1].dedupe_hash()


def test_dedupe_hash_prefers_external_id_when_present():
    camt_rows = parse_camt053(CAMT053_SAMPLE.encode("utf-8"))
    # Same external id, deliberately different description -> still same hash.
    from dataclasses import replace

    altered = replace(camt_rows[0], description="completely different text")
    assert camt_rows[0].dedupe_hash() == altered.dedupe_hash()
