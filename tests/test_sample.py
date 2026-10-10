"""One-click sample corpus endpoints. No database or OpenAI calls: both are stubbed."""
import pytest
from fastapi.testclient import TestClient

from api import main
from core.ratelimit import limiter

client = TestClient(main.app)


class FakeConn:
    def __init__(self, present):
        self.present = present

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params=()):
        self.row = (1,) if params and params[0] in self.present else None
        return self

    def fetchone(self):
        return self.row


@pytest.fixture
def stub(monkeypatch):
    limiter.hits.clear()
    calls, present = [], set()
    monkeypatch.setattr(main.db, "connect", lambda: FakeConn(present))
    monkeypatch.setattr(main, "ingest_text", lambda title, text, source, conn: calls.append((title, text, source))
                        or {"document_id": 1, "title": title, "chunks": 3})
    yield calls, present
    limiter.hits.clear()


def test_lists_rfc_files_smallest_first_and_golden_questions():
    body = client.get("/api/sample").json()
    assert len(body["files"]) == 11 and len(body["questions"]) == 20
    assert [f["kb"] for f in body["files"]] == sorted(f["kb"] for f in body["files"])
    titles = {f["title"] for f in body["files"]}
    assert all(set(q["docs"]) <= titles for q in body["questions"])  # every question maps onto sample documents


def test_load_ingests_cleaned_text_once(stub):
    calls, present = stub
    r = client.post("/api/sample/RFC_7233.txt")
    assert r.status_code == 200 and r.json()["chunks"] == 3
    title, text, source = calls[0]
    assert (title, source) == ("RFC 7233", "RFC_7233.txt")
    assert "[Page " not in text  # page furniture removed, as in the evaluation
    present.add("RFC_7233.txt")
    assert client.post("/api/sample/RFC_7233.txt").json() == {"title": "RFC 7233", "skipped": True}
    assert len(calls) == 1


@pytest.mark.parametrize("name", ["nope.txt", "..%2F..%2F.env", "RFC_7233"])
def test_load_rejects_anything_but_a_sample_file(stub, name):
    assert client.post(f"/api/sample/{name}").status_code == 404
    assert stub[0] == []
