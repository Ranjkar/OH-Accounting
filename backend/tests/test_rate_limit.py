from app.core.config import settings


def test_login_rate_limit_enforced(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_login_per_minute", 3)
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"email": "nobody@acme.nl", "password": "wrong"})
    response = client.post("/api/v1/auth/login", json={"email": "nobody@acme.nl", "password": "wrong"})
    assert response.status_code == 429
