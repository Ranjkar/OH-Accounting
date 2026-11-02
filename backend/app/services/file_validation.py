"""Content-based file-type detection and filename sanitization.

Never trust the client-supplied filename or MIME type: sniff magic bytes
and, for container formats (xlsx), confirm the payload actually parses.
"""

import hashlib
import re
from io import BytesIO

SUPPORTED_KINDS = {"pdf", "jpeg", "png", "xlsx", "csv"}

CONTENT_TYPES = {
    "pdf": "application/pdf",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "csv": "text/csv",
}


class UnsupportedFileType(ValueError):
    pass


def detect_kind(original_filename: str, content: bytes) -> str:
    """Determine the real file kind from content, falling back to extension only for CSV."""
    if content[:4] == b"%PDF":
        return "pdf"
    if content[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if content[:4] == b"PK\x03\x04":
        # zip container: confirm it's actually an xlsx workbook, not just any zip
        try:
            import openpyxl

            openpyxl.load_workbook(BytesIO(content), read_only=True)
            return "xlsx"
        except Exception as exc:
            raise UnsupportedFileType("File looks like a zip but is not a valid XLSX workbook") from exc

    # CSV has no magic bytes: require a plausible extension and valid text decoding
    if original_filename.lower().endswith(".csv"):
        try:
            content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UnsupportedFileType("File claims to be CSV but is not valid UTF-8 text") from exc
        return "csv"

    raise UnsupportedFileType("Unrecognized or unsupported file type")


def secure_filename(original_filename: str) -> str:
    base = original_filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    base = re.sub(r"[^A-Za-z0-9._-]", "_", base).strip("._") or "file"
    return base[-200:]


def sha256_hex(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()
