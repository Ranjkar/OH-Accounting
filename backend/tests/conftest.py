import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import app.api.v1.batches as batches_api
import app.api.v1.documents as documents_api
from app.core import rate_limit
from app.core.config import settings
from app.db.session import Base, get_db
from app.main import app
from app.models.legal_form import LegalFormDefinition
from app.models.legal_form_seed_data import LEGAL_FORM_SEED_ROWS
from app.services import ai_assistant_provider, ai_provider, ocr_provider
from tests.fakes import FakeAIProvider, FakeAssistantProvider, FakeOCRProvider

# Reference/lookup tables that are seed data, not per-test user data -- never
# wiped between tests, same rows the Phase 9 migration seeds in the real database.
_REFERENCE_TABLES = {"legal_form_definitions"}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit.reset_all()
    yield
    rate_limit.reset_all()

TEST_DATABASE_URL = settings.database_url.rsplit("/", 1)[0] + "/onholland_accounting_test"


@pytest.fixture(scope="session")
def engine():
    engine = create_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(LegalFormDefinition.__table__.insert(), LEGAL_FORM_SEED_ROWS)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def test_session_local(engine):
    # autoflush=False to match app.db.session.SessionLocal exactly -- a test
    # session that autoflushes would hide bugs where a query right after a
    # same-session mutation silently depends on an implicit flush that the
    # real app session never performs.
    return sessionmaker(bind=engine, autoflush=False)


@pytest.fixture()
def db_session(engine, test_session_local):
    session = test_session_local()
    for table in reversed(Base.metadata.sorted_tables):
        if table.name not in _REFERENCE_TABLES:
            session.execute(table.delete())
    session.commit()
    yield session
    session.close()


@pytest.fixture()
def tmp_storage(monkeypatch):
    storage_dir = tempfile.mkdtemp(prefix="onholland_test_storage_")
    monkeypatch.setattr(settings, "storage_root", storage_dir)
    yield storage_dir
    shutil.rmtree(storage_dir, ignore_errors=True)


@pytest.fixture()
def fake_ai_provider(monkeypatch):
    fake = FakeAIProvider()
    monkeypatch.setattr(ai_provider, "get_ai_provider", lambda: fake)
    return fake


@pytest.fixture()
def fake_ocr_provider(monkeypatch):
    fake = FakeOCRProvider()
    monkeypatch.setattr(ocr_provider, "get_ocr_provider", lambda: fake)
    return fake


@pytest.fixture()
def fake_assistant_provider(monkeypatch):
    fake = FakeAssistantProvider()
    monkeypatch.setattr(ai_assistant_provider, "get_assistant_provider", lambda: fake)
    return fake


@pytest.fixture()
def client(
    db_session, test_session_local, tmp_storage, fake_ai_provider, fake_ocr_provider, fake_assistant_provider, monkeypatch
):
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    # Background document-processing tasks open their own session; point that
    # at the same test database instead of the real dev/prod one.
    monkeypatch.setattr(documents_api, "SessionLocal", test_session_local)
    monkeypatch.setattr(batches_api, "SessionLocal", test_session_local)
    yield TestClient(app)
    app.dependency_overrides.clear()
