"""Phase 17.4 -- security-configuration regression tests.

Covers audit findings 6.4 (committed Fernet/HMAC defaults, fail-open),
7.5 (two of three secret classes could not be rotated), 7.19 (unhardened XML
parsing of attacker-supplied bank statements) and 8.1 (CORS allow-list).

Two properties these tests guard that are easy to get wrong:

  * The secret checks must NEVER render a configured secret value. A hygiene
    check that prints the key it is complaining about is worse than no check.
    test_no_guarded_secret_value_ever_reaches_a_log_or_exception_message
    asserts this directly with a unique canary value.

  * Fail-closed must mean fail-closed. An unrecognised ENVIRONMENT string
    (a typo, a renamed tier) must refuse to start rather than fall through to
    the permissive branch -- test_unrecognised_environment_fails_closed.
"""

import importlib.util
import logging
import sys
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.accounting.bank_parsers import BankFileParseError, parse_camt053, parse_camt054
from app.core import config as app_config
from app.core import crypto, mfa_crypto, token_crypto

BACKEND_ROOT = Path(__file__).resolve().parent.parent


def _new_fernet_key() -> str:
    return Fernet.generate_key().decode()


# A legitimate CAMT.053 statement: no DOCTYPE, identifies itself with xmlns on
# the root element, exactly as real Dutch bank exports do.
VALID_CAMT053 = b"""<?xml version="1.0" encoding="UTF-8"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02">
  <BkToCstmrStmt>
    <Stmt>
      <Acct><Id><IBAN>NL91ABNA0417164300</IBAN></Id></Acct>
      <Ntry>
        <Amt Ccy="EUR">121.00</Amt>
        <CdtDbtInd>CRDT</CdtDbtInd>
        <BookgDt><Dt>2026-02-10</Dt></BookgDt>
        <AcctSvcrRef>REF-0001</AcctSvcrRef>
        <NtryDtls><TxDtls>
          <RmtInf><Ustrd>Invoice INV-1</Ustrd></RmtInf>
          <RltdPties><Dbtr><Nm>Klant Retail B.V.</Nm></Dbtr></RltdPties>
        </TxDtls></NtryDtls>
      </Ntry>
    </Stmt>
  </BkToCstmrStmt>
</Document>
"""

# Expands to ~10 million characters from a few hundred bytes. CPython 3.12's
# bundled expat happens to abort on this; 3.9 does not. The fix must not
# depend on which interpreter the image was built with.
BILLION_LAUGHS = b"""<?xml version="1.0"?>
<!DOCTYPE r [
  <!ENTITY a "aaaaaaaaaa">
  <!ENTITY b "&a;&a;&a;&a;&a;&a;&a;&a;&a;&a;">
  <!ENTITY c "&b;&b;&b;&b;&b;&b;&b;&b;&b;&b;">
  <!ENTITY d "&c;&c;&c;&c;&c;&c;&c;&c;&c;&c;">
  <!ENTITY e "&d;&d;&d;&d;&d;&d;&d;&d;&d;&d;">
  <!ENTITY f "&e;&e;&e;&e;&e;&e;&e;&e;&e;&e;">
]>
<Document><BkToCstmrStmt><Stmt><Ntry>
  <Amt Ccy="EUR">1.00</Amt><BookgDt><Dt>2026-01-01</Dt></BookgDt>
  <NtryDtls><TxDtls><RmtInf><Ustrd>&f;</Ustrd></RmtInf></TxDtls></NtryDtls>
</Ntry></Stmt></BkToCstmrStmt></Document>
"""

EXTERNAL_ENTITY = b"""<?xml version="1.0"?>
<!DOCTYPE r [<!ENTITY xxe SYSTEM "file:///etc/passwd">]>
<Document><BkToCstmrStmt><Stmt><Ntry>
  <Amt Ccy="EUR">1.00</Amt><BookgDt><Dt>2026-01-01</Dt></BookgDt>
  <NtryDtls><TxDtls><RmtInf><Ustrd>&xxe;</Ustrd></RmtInf></TxDtls></NtryDtls>
</Ntry></Stmt></BkToCstmrStmt></Document>
"""


# --------------------------------------------------------------------------
# 6.4 -- fail-closed secret validation
# --------------------------------------------------------------------------


@pytest.fixture()
def all_secrets_real(monkeypatch):
    """A configuration in which every guarded secret is a fresh random value,
    so tests can then break exactly one of them."""
    monkeypatch.setattr(app_config.settings, "jwt_secret", "unique-" + _new_fernet_key())
    monkeypatch.setattr(app_config.settings, "bsn_encryption_key", _new_fernet_key())
    monkeypatch.setattr(app_config.settings, "open_banking_token_encryption_key", _new_fernet_key())
    monkeypatch.setattr(app_config.settings, "mfa_secret_encryption_key", _new_fernet_key())
    monkeypatch.setattr(app_config.settings, "billing_webhook_secret", _new_fernet_key())
    return app_config.settings


def test_all_real_secrets_produce_no_offenders(all_secrets_real):
    assert app_config.insecure_placeholder_secrets() == []
    app_config._enforce_secret_hygiene()  # must not raise


@pytest.mark.parametrize("environment", ["production", "staging", "prod", "acceptance"])
def test_non_development_environments_fail_closed(all_secrets_real, monkeypatch, environment):
    monkeypatch.setattr(app_config.settings, "environment", environment)
    monkeypatch.setattr(app_config.settings, "mfa_secret_encryption_key", app_config.INSECURE_DEFAULT_MFA_SECRET_KEY)

    with pytest.raises(RuntimeError) as exc:
        app_config._enforce_secret_hygiene()

    message = str(exc.value)
    assert "MFA_SECRET_ENCRYPTION_KEY" in message
    assert environment in message
    # Names the offender and how to fix it; never the value.
    assert "Fernet.generate_key" in message


def test_unrecognised_environment_fails_closed(all_secrets_real, monkeypatch):
    """A typo must not fall through to the permissive branch. 'prodction' is
    not in PERMISSIVE_ENVIRONMENTS, so it must refuse to start."""
    monkeypatch.setattr(app_config.settings, "environment", "prodction")
    monkeypatch.setattr(app_config.settings, "jwt_secret", app_config.INSECURE_DEFAULT_JWT_SECRET)

    with pytest.raises(RuntimeError):
        app_config._enforce_secret_hygiene()


@pytest.mark.parametrize("environment", ["development", "dev", "test", "testing", "Development", " TEST "])
def test_development_environments_warn_instead_of_raising(all_secrets_real, monkeypatch, caplog, environment):
    monkeypatch.setattr(app_config.settings, "environment", environment)
    monkeypatch.setattr(app_config.settings, "bsn_encryption_key", app_config.INSECURE_DEFAULT_BSN_ENCRYPTION_KEY)

    with caplog.at_level(logging.WARNING, logger="app.core.config"):
        app_config._enforce_secret_hygiene()  # must not raise

    rendered = [record.getMessage() for record in caplog.records]
    assert any("BSN_ENCRYPTION_KEY" in message for message in rendered)


@pytest.mark.parametrize(
    "attribute,env_name",
    [
        ("jwt_secret", "JWT_SECRET"),
        ("bsn_encryption_key", "BSN_ENCRYPTION_KEY"),
        ("open_banking_token_encryption_key", "OPEN_BANKING_TOKEN_ENCRYPTION_KEY"),
        ("mfa_secret_encryption_key", "MFA_SECRET_ENCRYPTION_KEY"),
        ("billing_webhook_secret", "BILLING_WEBHOOK_SECRET"),
    ],
)
def test_every_guarded_secret_is_individually_enforced(all_secrets_real, monkeypatch, attribute, env_name):
    """Each of the five must be caught on its own -- a table where one row was
    wired to the wrong attribute would otherwise pass unnoticed."""
    monkeypatch.setattr(app_config.settings, "environment", "production")
    placeholder = {
        "jwt_secret": app_config.INSECURE_DEFAULT_JWT_SECRET,
        "bsn_encryption_key": app_config.INSECURE_DEFAULT_BSN_ENCRYPTION_KEY,
        "open_banking_token_encryption_key": app_config.INSECURE_DEFAULT_OPEN_BANKING_KEY,
        "mfa_secret_encryption_key": app_config.INSECURE_DEFAULT_MFA_SECRET_KEY,
        "billing_webhook_secret": app_config.INSECURE_DEFAULT_BILLING_WEBHOOK_SECRET,
    }[attribute]
    monkeypatch.setattr(app_config.settings, attribute, placeholder)

    offenders = dict(app_config.insecure_placeholder_secrets())
    assert env_name in offenders
    with pytest.raises(RuntimeError):
        app_config._enforce_secret_hygiene()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_secrets_are_an_offence(all_secrets_real, monkeypatch, blank):
    """`JWT_SECRET=` in an env file yields an empty string. An empty HMAC
    signing key is worse than a placeholder and a value-equality check alone
    would not catch it."""
    monkeypatch.setattr(app_config.settings, "environment", "production")
    monkeypatch.setattr(app_config.settings, "jwt_secret", blank)

    offenders = dict(app_config.insecure_placeholder_secrets())
    assert "JWT_SECRET" in offenders
    with pytest.raises(RuntimeError):
        app_config._enforce_secret_hygiene()


def test_the_env_template_jwt_literal_is_also_rejected(all_secrets_real, monkeypatch):
    """backend/.env.example ships JWT_SECRET=change-me-in-production, which is
    NOT the same string as the code default. Copying that template into
    .env.prod must not sail past the guard while running a publicly-known
    signing key."""
    monkeypatch.setattr(app_config.settings, "environment", "production")
    monkeypatch.setattr(app_config.settings, "jwt_secret", app_config.INSECURE_TEMPLATE_JWT_SECRET)

    assert app_config.INSECURE_TEMPLATE_JWT_SECRET == "change-me-in-production"
    offenders = dict(app_config.insecure_placeholder_secrets())
    assert "JWT_SECRET" in offenders


def test_no_guarded_secret_value_ever_reaches_a_log_or_exception_message(all_secrets_real, monkeypatch, caplog):
    """The single most important property of a secret check: it must not leak
    the secret. Four of the five are set to unique canaries and the fifth is
    broken with its PUBLIC placeholder, so the guard fires -- and the canaries
    prove nothing configured was rendered into the complaint."""
    canaries = {
        "jwt_secret": "CANARY-JWT-" + _new_fernet_key(),
        "bsn_encryption_key": _new_fernet_key(),
        "open_banking_token_encryption_key": _new_fernet_key(),
        "billing_webhook_secret": "CANARY-BILLING-" + _new_fernet_key(),
    }
    for attribute, value in canaries.items():
        monkeypatch.setattr(app_config.settings, attribute, value)

    # The one offender: MFA left on the committed public key.
    monkeypatch.setattr(
        app_config.settings, "mfa_secret_encryption_key", app_config.INSECURE_DEFAULT_MFA_SECRET_KEY
    )
    monkeypatch.setattr(app_config.settings, "environment", "production")

    with caplog.at_level(logging.WARNING):
        with pytest.raises(RuntimeError) as exc:
            app_config._enforce_secret_hygiene()

    message = str(exc.value)
    assert "MFA_SECRET_ENCRYPTION_KEY" in message
    for attribute, canary in canaries.items():
        assert canary not in message, f"{attribute} value leaked into the exception message"
    for record in caplog.records:
        rendered = record.getMessage()
        for canary in canaries.values():
            assert canary not in rendered, "a configured secret value leaked into a log line"


def test_settings_repr_never_renders_a_secret_value(monkeypatch):
    """Found while writing these tests: a failing test's fixture repr printed
    a configured billing secret straight to the console, because pydantic
    renders every plain-`str` field in `repr(settings)`. Any f-string, debug
    log, exception context or test failure that touched the settings object
    did the same. All secret fields are now `repr=False`."""
    canaries = {
        "jwt_secret": "REPR-CANARY-JWT",
        "database_url": "postgresql+psycopg://u:REPR-CANARY-DB-PASSWORD@h/db",
        "anthropic_api_key": "REPR-CANARY-ANTHROPIC",
        "bsn_encryption_key": "REPR-CANARY-BSN",
        "bsn_encryption_key_previous": "REPR-CANARY-BSN-PREV",
        "open_banking_token_encryption_key": "REPR-CANARY-OB",
        "open_banking_token_encryption_key_previous": "REPR-CANARY-OB-PREV",
        "mfa_secret_encryption_key": "REPR-CANARY-MFA",
        "mfa_secret_encryption_key_previous": "REPR-CANARY-MFA-PREV",
        "billing_webhook_secret": "REPR-CANARY-BILLING",
        "kvk_api_key": "REPR-CANARY-KVK",
    }
    for attribute, value in canaries.items():
        monkeypatch.setattr(app_config.settings, attribute, value)

    rendered = repr(app_config.settings)
    str_rendered = str(app_config.settings)
    dumped = app_config.settings.model_dump()

    for attribute, canary in canaries.items():
        assert canary not in rendered, f"{attribute} leaked into repr(settings)"
        assert canary not in str_rendered, f"{attribute} leaked into str(settings)"
        # model_dump is a deliberate, explicit export -- it is NOT expected to
        # hide anything, so this asserts the values are still readable there
        # and by every normal consumer.
        assert dumped[attribute] == canary, f"{attribute} must still be readable by consumers"

    # A non-secret field is still rendered, so repr stays useful for debugging.
    assert "environment" in rendered


def test_production_mode_lists_every_offender_not_just_the_first(all_secrets_real, monkeypatch):
    """An operator fixing one variable at a time would otherwise have to
    restart five times to discover all of them."""
    monkeypatch.setattr(app_config.settings, "environment", "production")
    monkeypatch.setattr(app_config.settings, "bsn_encryption_key", app_config.INSECURE_DEFAULT_BSN_ENCRYPTION_KEY)
    monkeypatch.setattr(app_config.settings, "mfa_secret_encryption_key", app_config.INSECURE_DEFAULT_MFA_SECRET_KEY)
    monkeypatch.setattr(app_config.settings, "billing_webhook_secret", "")

    offenders = dict(app_config.insecure_placeholder_secrets())
    assert set(offenders) == {"BSN_ENCRYPTION_KEY", "MFA_SECRET_ENCRYPTION_KEY", "BILLING_WEBHOOK_SECRET"}

    with pytest.raises(RuntimeError) as exc:
        app_config._enforce_secret_hygiene()
    for name in offenders:
        assert name in str(exc.value)


def test_env_templates_document_every_guarded_variable():
    """The audit found .env.example and .env.prod.example each omitted three
    of the five guarded secrets, so following the documented setup GUARANTEED
    running on the committed defaults. Pin the templates so they cannot drift
    out of sync with _GUARDED_SECRETS again."""
    required = {env_name for _, env_name, _, _ in app_config._GUARDED_SECRETS}
    for template in (BACKEND_ROOT / ".env.example", BACKEND_ROOT.parent / ".env.prod.example"):
        text = template.read_text()
        missing = {name for name in required if f"{name}=" not in text}
        assert not missing, f"{template.name} is missing: {sorted(missing)}"
        assert "ENVIRONMENT=" in text, f"{template.name} does not mention ENVIRONMENT"


# --------------------------------------------------------------------------
# 7.5 -- the two secret classes that previously could not be rotated
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "module,encrypt,decrypt,reencrypt,current_attr,previous_attr",
    [
        (crypto, crypto.encrypt_bsn, crypto.decrypt_bsn, crypto.reencrypt_bsn_with_current_key,
         "bsn_encryption_key", "bsn_encryption_key_previous"),
        (token_crypto, token_crypto.encrypt_token, token_crypto.decrypt_token,
         token_crypto.reencrypt_token_with_current_key,
         "open_banking_token_encryption_key", "open_banking_token_encryption_key_previous"),
        (mfa_crypto, mfa_crypto.encrypt_mfa_secret, mfa_crypto.decrypt_mfa_secret,
         mfa_crypto.reencrypt_mfa_secret_with_current_key,
         "mfa_secret_encryption_key", "mfa_secret_encryption_key_previous"),
    ],
)
def test_full_rotation_procedure_for_every_secret_class(
    monkeypatch, module, encrypt, decrypt, reencrypt, current_attr, previous_attr
):
    """The procedure an operator actually follows, end to end:

      1. everything is encrypted under OLD;
      2. operator sets current=NEW, previous=OLD -- old ciphertext still reads;
      3. re-encrypt migrates it onto NEW;
      4. operator removes OLD from previous -- and it STILL reads.

    Step 4 is the one that was impossible for Open Banking tokens and MFA
    secrets before this phase: neither module had a reencrypt function, so a
    retired key could never actually be removed.
    """
    plaintext = "sensitive-value-under-test"
    old_key, new_key = _new_fernet_key(), _new_fernet_key()

    monkeypatch.setattr(app_config.settings, current_attr, old_key)
    monkeypatch.setattr(app_config.settings, previous_attr, "")
    ciphertext = encrypt(plaintext)
    assert decrypt(ciphertext) == plaintext

    monkeypatch.setattr(app_config.settings, current_attr, new_key)
    monkeypatch.setattr(app_config.settings, previous_attr, old_key)
    assert decrypt(ciphertext) == plaintext, "old ciphertext must still read mid-rotation"

    migrated = reencrypt(ciphertext)
    assert migrated != ciphertext
    assert decrypt(migrated) == plaintext

    # Retire the old key entirely.
    monkeypatch.setattr(app_config.settings, previous_attr, "")
    assert decrypt(migrated) == plaintext, "migrated ciphertext must not need the retired key"
    with pytest.raises(ValueError):
        decrypt(ciphertext)


def test_rotation_script_refuses_to_migrate_onto_a_public_placeholder_key(all_secrets_real, monkeypatch):
    """Re-encrypting onto a key that is committed to the repository would be
    worse than doing nothing -- it would look like a rotation had happened."""
    monkeypatch.setattr(app_config.settings, "mfa_secret_encryption_key", app_config.INSECURE_DEFAULT_MFA_SECRET_KEY)
    script = _load_rotation_script()

    with pytest.raises(SystemExit) as exc:
        script._refuse_if_key_is_still_the_placeholder("mfa", "MFA_SECRET_ENCRYPTION_KEY")
    assert "MFA_SECRET_ENCRYPTION_KEY" in str(exc.value)

    # And it does not object once the key is real.
    monkeypatch.setattr(app_config.settings, "mfa_secret_encryption_key", _new_fernet_key())
    script._refuse_if_key_is_still_the_placeholder("mfa", "MFA_SECRET_ENCRYPTION_KEY")


def _load_rotation_script():
    path = BACKEND_ROOT / "scripts" / "rotate_encryption_keys.py"
    spec = importlib.util.spec_from_file_location("rotate_encryption_keys", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault("rotate_encryption_keys", module)
    spec.loader.exec_module(module)
    return module


def test_rotation_script_covers_all_three_secret_classes():
    script = _load_rotation_script()
    assert set(script.SECRET_CLASSES) == {"bsn", "open_banking", "mfa"}
    for env_var, targets in script.SECRET_CLASSES.values():
        assert env_var in {name for _, name, _, _ in app_config._GUARDED_SECRETS}
        assert targets, f"{env_var} has no columns to migrate"


# --------------------------------------------------------------------------
# 7.19 -- XML hardening for attacker-supplied bank statements
# --------------------------------------------------------------------------


def test_legitimate_camt053_still_parses():
    """The guard must not break real bank exports. Real CAMT files carry no
    DOCTYPE -- they identify themselves with xmlns on the root element."""
    parsed = parse_camt053(VALID_CAMT053)
    assert len(parsed) == 1
    assert parsed[0].amount == pytest.approx(121.0)
    assert parsed[0].counterparty_name == "Klant Retail B.V."


def test_legitimate_camt054_still_parses():
    camt054 = VALID_CAMT053.replace(b"camt.053.001.02", b"camt.054.001.02")
    assert len(parse_camt054(camt054)) == 1


@pytest.mark.parametrize("parser", [parse_camt053, parse_camt054])
def test_billion_laughs_payload_is_rejected(parser):
    """Must be rejected by THIS CODE, not incidentally by the interpreter's
    expat build -- CPython 3.9 does not block this payload at all."""
    with pytest.raises(BankFileParseError) as exc:
        parser(BILLION_LAUGHS)
    assert "DOCTYPE" in str(exc.value) or "ENTITY" in str(exc.value)


@pytest.mark.parametrize("parser", [parse_camt053, parse_camt054])
def test_external_entity_payload_is_rejected(parser):
    with pytest.raises(BankFileParseError):
        parser(EXTERNAL_ENTITY)


@pytest.mark.parametrize("parser", [parse_camt053, parse_camt054])
@pytest.mark.parametrize(
    "prolog",
    [
        b'<!DOCTYPE r [<!ENTITY a "b">]>',
        b'<!doctype r [<!entity a "b">]>',          # XML keywords are case-insensitive
        b'<!DocType r [<!EnTiTy a "b">]>',
        b'<!ENTITY a "b">',                          # entity without a doctype keyword
    ],
)
def test_dtd_rejection_is_case_insensitive_and_catches_bare_entities(parser, prolog):
    payload = b'<?xml version="1.0"?>' + prolog + b"<Document><BkToCstmrStmt><Stmt><Ntry>" \
              b"<Amt Ccy=\"EUR\">1.00</Amt><BookgDt><Dt>2026-01-01</Dt></BookgDt>" \
              b"</Ntry></Stmt></BkToCstmrStmt></Document>"
    with pytest.raises(BankFileParseError):
        parser(payload)


def test_rejection_is_a_clean_domain_error_not_a_500():
    """The caller (banking.import_bank_statement) maps BankFileParseError to a
    4xx. A raw ElementTree.ParseError or an expat crash would surface as a 500
    and leak a traceback."""
    with pytest.raises(BankFileParseError):
        parse_camt053(EXTERNAL_ENTITY)


def test_malformed_xml_without_a_dtd_still_reports_as_a_parse_error():
    with pytest.raises(BankFileParseError) as exc:
        parse_camt053(b"<Document><unclosed>")
    assert "Invalid CAMT.053 XML" in str(exc.value)


# --------------------------------------------------------------------------
# 8.1 / 6.9 -- CORS allow-list validation
# --------------------------------------------------------------------------


@pytest.fixture()
def cors_origins(monkeypatch):
    def _set(origins: list[str], environment: str = "production"):
        import app.main as main_module

        monkeypatch.setattr(main_module, "_allowed_origins", origins)
        monkeypatch.setattr(app_config.settings, "environment", environment)
        return main_module

    return _set


@pytest.mark.parametrize(
    "origin",
    [
        "http://192.168.68.105:3000",   # the developer LAN IP baked into the default
        "http://10.0.0.5:3000",
        "http://172.16.4.9",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://[fd00::1]:3000",
    ],
)
def test_production_rejects_private_loopback_and_link_local_origins(cors_origins, origin):
    main_module = cors_origins([origin])
    with pytest.raises(RuntimeError) as exc:
        main_module._validate_cors_origins()
    assert origin in str(exc.value)


def test_production_rejects_a_wildcard_origin(cors_origins):
    main_module = cors_origins(["*"])
    with pytest.raises(RuntimeError) as exc:
        main_module._validate_cors_origins()
    assert "wildcard" in str(exc.value)


def test_production_rejects_plain_http_on_a_public_hostname(cors_origins):
    """Credentialed cross-origin calls over cleartext are interceptable."""
    main_module = cors_origins(["http://accounting.example.nl"])
    with pytest.raises(RuntimeError) as exc:
        main_module._validate_cors_origins()
    assert "http://" in str(exc.value)


def test_production_accepts_a_public_https_origin(cors_origins):
    main_module = cors_origins(["https://accounting.example.nl"])
    main_module._validate_cors_origins()  # must not raise


def test_production_accepts_multiple_https_origins(cors_origins):
    main_module = cors_origins(["https://app.example.nl", "https://admin.example.nl"])
    main_module._validate_cors_origins()


def test_development_permits_localhost_and_lan_origins(cors_origins, caplog):
    """Local development must keep working unchanged -- this is why the guard
    is environment-aware rather than absolute."""
    main_module = cors_origins(
        ["http://localhost:3000", "http://127.0.0.1:3000", "http://192.168.68.105:3000"],
        environment="development",
    )
    with caplog.at_level(logging.WARNING):
        main_module._validate_cors_origins()  # must not raise
    assert any("CORS_ALLOWED_ORIGINS" in r.getMessage() for r in caplog.records)


def test_development_warns_about_a_lan_origin_but_not_about_loopback(cors_origins, caplog):
    """Loopback is the documented dev default, so warning about it on every
    startup would be noise that trains people to ignore the warning that
    actually matters -- the routable LAN address."""
    main_module = cors_origins(
        ["http://localhost:3000", "http://127.0.0.1:3000"], environment="development"
    )
    with caplog.at_level(logging.WARNING):
        main_module._validate_cors_origins()
    cors_warnings = [r.getMessage() for r in caplog.records if "CORS_ALLOWED_ORIGINS" in r.getMessage()]
    assert cors_warnings == [], f"loopback-only origins should not warn in dev: {cors_warnings}"

    main_module = cors_origins(["http://192.168.68.105:3000"], environment="development")
    caplog.clear()
    with caplog.at_level(logging.WARNING):
        main_module._validate_cors_origins()
    cors_warnings = [r.getMessage() for r in caplog.records if "CORS_ALLOWED_ORIGINS" in r.getMessage()]
    assert len(cors_warnings) == 1
    assert "192.168.68.105" in cors_warnings[0]


def test_production_rejects_loopback_origins_too(cors_origins):
    """The dev noise suppression must not weaken the strict path: a production
    deployment has no business allowing localhost."""
    main_module = cors_origins(["http://localhost:3000"])
    with pytest.raises(RuntimeError):
        main_module._validate_cors_origins()


def test_cors_guard_flags_every_bad_origin_not_just_the_first(cors_origins):
    main_module = cors_origins(["https://good.example.nl", "http://10.0.0.5:3000", "*"])
    with pytest.raises(RuntimeError) as exc:
        main_module._validate_cors_origins()
    message = str(exc.value)
    assert "http://10.0.0.5:3000" in message
    assert "*" in message
