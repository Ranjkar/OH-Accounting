"""Local-disk document storage.

Paths are built only from integer IDs and an already-sanitized filename —
never from raw user input — so there is no path-traversal surface.
Swap this module for an Azure Blob-backed one in Phase 5 without touching callers.
"""

from pathlib import Path

from app.core.config import settings


def _root() -> Path:
    root = Path(settings.storage_root)
    root.mkdir(parents=True, exist_ok=True)
    return root


def save(tenant_id: int, company_id: int, document_id: int, filename: str, content: bytes) -> str:
    rel_path = Path(str(tenant_id)) / str(company_id) / f"{document_id}_{filename}"
    full_path = _root() / rel_path
    full_path.parent.mkdir(parents=True, exist_ok=True)
    full_path.write_bytes(content)
    return str(rel_path)


def read(storage_path: str) -> bytes:
    full_path = (_root() / storage_path).resolve()
    if not str(full_path).startswith(str(_root().resolve())):
        raise ValueError("Invalid storage path")
    return full_path.read_bytes()


def delete(storage_path: str) -> None:
    full_path = (_root() / storage_path).resolve()
    if not str(full_path).startswith(str(_root().resolve())):
        raise ValueError("Invalid storage path")
    full_path.unlink(missing_ok=True)
