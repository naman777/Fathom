"""Enterprise API: the role is resolved on the server and reaches every search. Qdrant and the LLM are stubbed."""
import pytest
from fastapi.testclient import TestClient

from api import enterprise as api_ent
from api.main import app
from core import config
from enterprise import acl, search as ent_search


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(api_ent, "_index", lambda: {"ready": True, "chunks": 1, "status": "green"})
    return TestClient(app)


def test_roles_endpoint_lists_roles_and_groups(client):
    j = client.get("/api/enterprise/roles").json()
    assert {r["id"] for r in j["roles"]} == set(acl.ROLES) and j["default"] == acl.DEFAULT_ROLE
    assert next(r for r in j["roles"] if r["id"] == "admin")["groups"] is None


@pytest.mark.parametrize("header,expected", [("hr", "hr"), ("admin", "admin"), ("root", acl.DEFAULT_ROLE),
                                             ("", acl.DEFAULT_ROLE), (None, acl.DEFAULT_ROLE)])
def test_unknown_or_missing_role_gets_least_privilege(header, expected):
    assert api_ent.current_role(header) == expected


def test_chat_passes_the_header_role_to_search_and_expansion(client, monkeypatch):
    seen = {"search": [], "expand": []}

    def fake_search(q, role, k=6, rerank=True, **kw):
        seen["search"].append(role)
        return [{"id": "p1", "doc_id": "d1", "source": "slack", "title": "people-ops", "position": 0, "content": "x", "score": 1.0}]

    def fake_expand(chunks, role, radius=1, collection=None):
        seen["expand"].append(role)
        return chunks

    monkeypatch.setattr(ent_search, "search", fake_search)
    monkeypatch.setattr(ent_search, "expand", fake_expand)
    monkeypatch.setattr("generation.prompt.answer_stream", lambda *a, **k: iter(["ok"]))
    r = client.post("/api/enterprise/chat", json={"question": "what is the leave policy?", "agent": False},
                    headers={"X-Demo-Role": "hr"})
    assert r.status_code == 200 and '"doc_id": "d1"' in r.text and "event: done" in r.text
    assert seen == {"search": ["hr"], "expand": ["hr"]}

    seen["search"].clear(), seen["expand"].clear()
    client.post("/api/enterprise/chat", json={"question": "what is the leave policy?", "agent": False},
                headers={"X-Demo-Role": "ceo"})
    assert seen == {"search": [acl.DEFAULT_ROLE], "expand": [acl.DEFAULT_ROLE]}


def test_search_turns_the_role_into_a_group_filter(monkeypatch):
    calls = []
    monkeypatch.setattr(ent_search.store, "search", lambda q, groups, **kw: calls.append(groups) or [])
    ent_search.search("q", "engineer", rerank=False)
    ent_search.search("q", "admin", rerank=False)
    ent_search.search("q", "nobody", rerank=False)
    assert calls == [["all", "eng", "product"], None, ["all"]]


def test_group_filter_shape():
    from enterprise import store
    f = store.group_filter(["all", "eng"])
    assert f.must[0].key == "groups" and f.must[0].match.any == ["all", "eng"]
    assert store.group_filter(None) is None
    assert store.group_filter([]).must[0].match.any == []  # no groups matches nothing, it does not mean unrestricted


def test_chat_503_when_index_missing(monkeypatch):
    monkeypatch.setattr(config, "RATE_LIMIT_ENABLED", False)
    monkeypatch.setattr(api_ent, "_index", lambda: {"ready": False, "chunks": 0, "status": "unavailable"})
    assert TestClient(app).post("/api/enterprise/chat", json={"question": "hi"}).status_code == 503
