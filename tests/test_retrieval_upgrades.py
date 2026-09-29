"""Contextual headers, heading detection, neighbour expansion and iterative follow-ups. No network."""
import pytest

from agent import loop
from core import config
from ingest import context
from ingest.chunking import is_heading, split_text, split_with_headings
from retrieval import expand


@pytest.mark.parametrize("p,expected", [
    ('4.1.1.  "iss" (Issuer) Claim', True), ("1. Introduction", True), ("# Setup guide", True), ("ABSTRACT", True),
    ("Appendix A. Examples", True),
    ("The maximum is 64 octets.", False), ("10 minutes is RECOMMENDED.", False),
    ("1. Introduction . . . . . . . . . 4", False), ("Why does this matter?", False),
])
def test_heading_detection(p, expected):
    assert is_heading(p) is expected


def test_chunks_carry_the_nearest_heading():
    text = "1. Overview\n\n" + "Intro sentence. " * 5 + "\n\n2. Limits\n\n" + "Limits sentence. " * 5
    pieces = split_with_headings(text, target=120, overlap=20)
    assert pieces[0][1] == "1. Overview" and pieces[-1][1] == "2. Limits"
    assert split_text(text, target=120, overlap=20) == [c for c, _ in pieces]


def test_header_format_and_strip_roundtrip():
    h = context.header("RFC 7519", "JSON Web Token (JWT) specification", '4.1.1. "iss" (Issuer) Claim')
    assert h == '[RFC 7519 - JSON Web Token (JWT) specification > 4.1.1. "iss" (Issuer) Claim]'
    assert context.strip_header(h + "\nBody text.") == "Body text."
    assert context.header("T", "", "") == "[T]"
    assert "]" not in context.header("T]x", "d]", "h]")[1:-1]


def test_merge_drops_the_chunker_overlap():
    a = "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda"
    b = "zeta eta theta iota kappa lambda mu nu"                       # repeats the last 35 characters of `a`
    assert expand.merge(a, b) == "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu"
    assert expand.merge("no overlap here at all", "different text entirely") == "no overlap here at all\ndifferent text entirely"


class FakeConn:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, sql, params):
        return self

    def fetchall(self):
        return self.rows


def test_expand_merges_neighbours_and_marks_expanded():
    rows = [(1, 4, "left part of the passage"), (1, 6, "right part of the passage")]
    hit = {"id": 9, "document_id": 1, "position": 5, "content": "middle", "title": "T", "score": 1.0}
    out = expand.expand(FakeConn(rows), [hit], radius=1)
    assert out[0]["content"] == "left part of the passage\nmiddle\nright part of the passage" and out[0]["expanded"]
    assert out[0]["id"] == 9 and hit["content"] == "middle"                       # input untouched
    assert expand.expand(FakeConn([]), [hit], 0) == [hit]                          # radius 0 is a no-op


def chunk(i):
    return {"id": i, "title": "D", "position": 0, "content": f"c{i}", "score": 1.0}


def test_iterative_followups_stop_when_sufficient_and_respect_the_cap(monkeypatch):
    replies = iter([{"queries": ["A", "B"]},
                    {"sufficient": False, "missing": "C", "next_query": "C"},
                    {"sufficient": False, "missing": "D", "next_query": "D"},
                    {"sufficient": True}])
    monkeypatch.setattr(loop.llm, "chat_json", lambda m, **kw: next(replies))
    searched = []
    monkeypatch.setattr(loop, "hybrid", lambda conn, q, k, rerank: searched.append(q) or [chunk(len(searched))])
    monkeypatch.setattr(loop, "_search", lambda q, rerank, k: searched.append(q) or [chunk(len(searched))])
    monkeypatch.setattr(loop, "MAX_FOLLOWUPS", 3)
    monkeypatch.setattr(config, "NEIGHBOR_EXPAND", 0)
    events = list(loop.run(None, "compare A and B and C and D"))
    assert sorted(searched[:2]) == ["A", "B"] and searched[2:] == ["C", "D"]      # two follow-up hops, then sufficient
    assert [e["type"] for e in events].count("reflect") == 3
