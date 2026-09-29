"""Rate limiter, input caps, admin auth and CORS. None of these tests call OpenAI."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from core import config
from core.ratelimit import limiter


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    limiter.hits.clear()
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", True)
    monkeypatch.setattr(config, "TRUST_PROXY", False)
    monkeypatch.setattr(config, "ADMIN_TOKEN", "")
    for name, val in dict(RL_CHAT_PER_MINUTE=3, RL_CHAT_PER_DAY=5, RL_UPLOAD_PER_HOUR=2,
                          RL_DELETE_PER_HOUR=2, RL_GLOBAL_PER_MINUTE=1000).items():
        monkeypatch.setattr(config, name, val)
    yield
    limiter.hits.clear()


client = TestClient(app)
BAD = {"question": ""}  # rejected with 400 before any LLM call, but still counted by the limiter


def chat(**kw):
    return client.post("/api/chat", json=BAD, **kw)


def test_chat_per_minute_limit_then_429_with_retry_after():
    assert [chat().status_code for _ in range(3)] == [400, 400, 400]
    r = chat()
    assert r.status_code == 429
    assert int(r.headers["retry-after"]) > 0
    assert r.json()["limit"] == "chat-min"


def test_limits_are_per_ip():
    for _ in range(3):
        chat()
    assert chat().status_code == 429
    other = client.post("/api/chat", json=BAD, headers={"x-forwarded-for": "9.9.9.9"})
    assert other.status_code == 429  # TRUST_PROXY off: header ignored, same client IP


def test_trust_proxy_uses_forwarded_ip(monkeypatch):
    monkeypatch.setattr(config, "TRUST_PROXY", True)
    for _ in range(3):
        chat(headers={"x-forwarded-for": "1.1.1.1"})
    assert chat(headers={"x-forwarded-for": "1.1.1.1"}).status_code == 429
    assert chat(headers={"x-forwarded-for": "2.2.2.2"}).status_code == 400


def test_daily_cap(monkeypatch):
    monkeypatch.setattr(config, "RL_CHAT_PER_MINUTE", 0)  # 0 disables the per-minute rule
    assert [chat().status_code for _ in range(5)] == [400] * 5
    r = chat()
    assert r.status_code == 429 and r.json()["limit"] == "chat-day"
    assert "Daily" in r.json()["detail"]


def test_disabled_limiter(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    assert all(chat().status_code == 400 for _ in range(10))


def test_upload_limit():
    files = {"file": ("x.exe", b"data")}
    assert client.post("/api/documents", files=files).status_code == 400
    assert client.post("/api/documents", files=files).status_code == 400
    assert client.post("/api/documents", files=files).status_code == 429


def test_delete_limit():
    assert client.delete("/api/documents/999999").status_code == 200
    assert client.delete("/api/documents/999999").status_code == 200
    assert client.delete("/api/documents/999999").status_code == 429


def test_rejected_requests_do_not_consume_other_buckets():
    for _ in range(4):
        chat()
    assert client.get("/api/health").status_code == 200  # health is only under the global bucket


def test_question_too_long(monkeypatch):
    monkeypatch.setattr(config, "MAX_QUESTION_CHARS", 20)
    r = client.post("/api/chat", json={"question": "a" * 21})
    assert r.status_code == 413


def test_upload_too_large(monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_MB", 0)
    r = client.post("/api/documents", files={"file": ("a.txt", b"hello")})
    assert r.status_code == 413


def test_unsupported_extension():
    assert client.post("/api/documents", files={"file": ("a.exe", b"x")}).status_code == 400


def test_admin_token_required_for_mutations(monkeypatch):
    monkeypatch.setattr(config, "ADMIN_TOKEN", "s3cret")
    monkeypatch.setattr(config, "RL_DELETE_PER_HOUR", 10)
    monkeypatch.setattr(config, "RL_UPLOAD_PER_HOUR", 10)
    assert client.delete("/api/documents/999999").status_code == 401
    assert client.delete("/api/documents/999999", headers={"x-admin-token": "wrong"}).status_code == 401
    assert client.delete("/api/documents/999999", headers={"x-admin-token": "s3cret"}).status_code == 200
    assert client.post("/api/documents", files={"file": ("a.txt", b"x")}).status_code == 401
    assert client.get("/api/documents").status_code == 200  # reading stays public


def test_cors_restricted_to_configured_origins():
    ok = client.options("/api/chat", headers={"origin": "http://localhost:3000", "access-control-request-method": "POST"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:3000"
    bad = client.options("/api/chat", headers={"origin": "https://evil.example", "access-control-request-method": "POST"})
    assert "access-control-allow-origin" not in bad.headers


def test_429_carries_cors_header_for_allowed_origin():
    for _ in range(3):
        chat()
    r = chat(headers={"origin": "http://localhost:3000"})
    assert r.status_code == 429
    assert r.headers.get("access-control-allow-origin") == "http://localhost:3000"
