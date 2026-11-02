import pytest

from app.services.file_validation import UnsupportedFileType, detect_kind, secure_filename, sha256_hex


def test_detects_pdf_by_magic_bytes():
    assert detect_kind("invoice.pdf", b"%PDF-1.4 rest of file") == "pdf"


def test_detects_jpeg_by_magic_bytes():
    assert detect_kind("photo.jpg", b"\xff\xd8\xff\xe0 rest") == "jpeg"


def test_detects_png_by_magic_bytes():
    assert detect_kind("scan.png", b"\x89PNG\r\n\x1a\n rest") == "png"


def test_rejects_mismatched_extension_claiming_pdf_but_actually_text():
    with pytest.raises(UnsupportedFileType):
        detect_kind("fake.pdf", b"this is not a pdf at all")


def test_csv_requires_valid_utf8_text():
    assert detect_kind("data.csv", "col1,col2\n1,2".encode("utf-8")) == "csv"
    with pytest.raises(UnsupportedFileType):
        detect_kind("data.csv", b"\xff\xfe\x00bad")


def test_zip_that_is_not_a_valid_xlsx_is_rejected():
    with pytest.raises(UnsupportedFileType):
        detect_kind("fake.xlsx", b"PK\x03\x04 not a real workbook")


def test_secure_filename_strips_path_and_special_chars():
    assert secure_filename("../../etc/passwd") == "passwd"
    assert secure_filename("my invoice (final)!.pdf") == "my_invoice__final__.pdf"


def test_sha256_is_deterministic():
    assert sha256_hex(b"abc") == sha256_hex(b"abc")
    assert sha256_hex(b"abc") != sha256_hex(b"abd")
