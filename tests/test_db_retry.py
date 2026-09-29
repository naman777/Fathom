"""db.connect retries a dropped fresh connection; no database needed."""
import psycopg
import pytest

from core import db


class FakeConn:
    closed = False

    def close(self):
        self.closed = True


def test_retries_then_succeeds(monkeypatch):
    calls, conns = [], []

    def flaky(url, autocommit):
        calls.append(1)
        if len(calls) < 3:
            raise psycopg.OperationalError("server closed the connection unexpectedly")
        conns.append(FakeConn())
        return conns[-1]

    monkeypatch.setattr(db.psycopg, "connect", flaky)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    assert db.connect(vectors=False) is conns[0] and len(calls) == 3


def test_gives_up_after_the_last_attempt_and_closes_half_open_connections(monkeypatch):
    made = []

    def connect(url, autocommit):
        made.append(FakeConn())
        return made[-1]

    def bad_register(conn):
        raise psycopg.OperationalError("dropped while registering vector type")

    monkeypatch.setattr(db.psycopg, "connect", connect)
    monkeypatch.setattr(db, "register_vector", bad_register)
    monkeypatch.setattr(db.time, "sleep", lambda s: None)
    with pytest.raises(psycopg.OperationalError):
        db.connect(attempts=2)
    assert len(made) == 2 and all(c.closed for c in made)
