from cryptography.fernet import Fernet

from app.core import crypto
from app.core.config import settings


def test_encrypt_decrypt_roundtrip():
    token = crypto.encrypt_bsn("123456789")
    assert crypto.decrypt_bsn(token) == "123456789"


def test_mask_bsn_shows_only_last_three_digits():
    assert crypto.mask_bsn("123456789") == "******789"


def test_decrypting_garbage_raises_value_error():
    import pytest
    with pytest.raises(ValueError):
        crypto.decrypt_bsn(b"not-a-real-fernet-token")


def test_rotation_old_ciphertext_still_decrypts_with_previous_key_listed(monkeypatch):
    """Simulates a key rotation: a BSN encrypted under the OLD key must
    still decrypt once BSN_ENCRYPTION_KEY is changed to a NEW key, as long
    as the old key is listed in BSN_ENCRYPTION_KEY_PREVIOUS -- this is the
    whole point of MultiFernet-based rotation (never breaking existing
    ciphertext the moment the primary key changes)."""
    old_key = settings.bsn_encryption_key
    monkeypatch.setattr(settings, "bsn_encryption_key_previous", "")
    old_ciphertext = crypto.encrypt_bsn("987654321")

    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "bsn_encryption_key", new_key)
    monkeypatch.setattr(settings, "bsn_encryption_key_previous", old_key)

    # Old ciphertext still decrypts because the old key is in the previous list.
    assert crypto.decrypt_bsn(old_ciphertext) == "987654321"
    # New values encrypt with the NEW (current) key only.
    new_ciphertext = crypto.encrypt_bsn("111222333")
    monkeypatch.setattr(settings, "bsn_encryption_key_previous", "")
    assert crypto.decrypt_bsn(new_ciphertext) == "111222333"


def test_rotate_bsn_with_current_key_migrates_off_the_old_key(monkeypatch):
    old_key = settings.bsn_encryption_key
    monkeypatch.setattr(settings, "bsn_encryption_key_previous", "")
    old_ciphertext = crypto.encrypt_bsn("555666777")

    new_key = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "bsn_encryption_key", new_key)
    monkeypatch.setattr(settings, "bsn_encryption_key_previous", old_key)

    migrated_ciphertext = crypto.reencrypt_bsn_with_current_key(old_ciphertext)

    # Now drop the old key entirely -- the migrated ciphertext must still decrypt.
    monkeypatch.setattr(settings, "bsn_encryption_key_previous", "")
    assert crypto.decrypt_bsn(migrated_ciphertext) == "555666777"
