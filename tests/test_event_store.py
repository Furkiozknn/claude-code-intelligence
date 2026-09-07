import os
import stat
from datetime import UTC, datetime, timedelta

import pytest

from cci.events import Envelope, SourceRef
from cci.store import EventStore, idempotency_key

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
SRC = SourceRef(collector="otlp", instance_id="otlp:claude-code", collector_version="0.0.1", schema_version=1)


def env(type_="tool.call", ts=NOW, payload=None, session="sess-1", **kw):
    return Envelope(type=type_, ts=ts, received_at=ts, source=SRC, provider="anthropic", session_id=session,
                    payload=payload if payload is not None else {"tool_name": "Read", "success": True}, **kw)


@pytest.fixture
def store(tmp_path):
    with EventStore(tmp_path / "cci" / "events.db") as s:
        yield s


def test_wal_mode_and_schema_version(store):
    assert store.journal_mode.lower() == "wal" and store.schema_version() == 1


def test_append_is_idempotent_on_type_ts_instance_payload(store):
    a = env()
    b = env()  # farkli event_id, ayni tur/ts/kaynak/payload
    assert a.event_id != b.event_id and idempotency_key(a) == idempotency_key(b)
    assert store.append(a) is True and store.append(b) is False and store.count() == 1
    c = env(ts=NOW + timedelta(seconds=1))
    assert store.append(c) is True and store.count() == 2


def test_append_many_reports_written_and_skipped(store):
    written, skipped = store.append_many([env(), env(), env(ts=NOW + timedelta(seconds=5))])
    assert (written, skipped) == (2, 1)


def test_query_filters_and_order(store):
    store.append_many([env(ts=NOW + timedelta(minutes=i), session="s1" if i % 2 else "s2",
                           payload={"tool_name": f"T{i}"}) for i in range(5)] +
                      [env("usage.error", ts=NOW, payload={"model": "m", "status_code": 500})])
    got = list(store.query(types=["tool.call"], session_id="s1"))
    assert [e.payload["tool_name"] for e in got] == ["T1", "T3"]
    got2 = list(store.query(since=NOW + timedelta(minutes=2), until=NOW + timedelta(minutes=4)))
    assert [e.payload["tool_name"] for e in got2] == ["T2", "T3"]
    assert list(store.query(types=["tool.call"], limit=1))[0].payload["tool_name"] == "T0"
    assert len(list(store.query(limit=2))) == 2
    e0 = list(store.query(types=["usage.error"]))[0]
    assert e0.ts == NOW and e0.source == SRC and e0.evidence_class.value == "observed"


def test_prune_deletes_old_rows_and_prune_payloads_keeps_hash(store):
    old = env(ts=NOW - timedelta(days=40), payload={"tool_name": "OLD"})
    mid = env(ts=NOW - timedelta(days=10), payload={"tool_name": "MID"})
    new = env(ts=NOW, payload={"tool_name": "NEW"})
    store.append_many([old, mid, new])
    assert store.prune(now=NOW) == 1 and store.count() == 2
    assert store.prune_payloads(older_than_days=7, now=NOW) == 1
    assert [e.payload["tool_name"] for e in store.query()] == ["NEW"]
    pruned = [e for e in store.query(include_pruned=True) if e.payload == {}]
    assert len(pruned) == 1 and pruned[0].payload_hash  # zarf + hash duruyor
    assert store.stats()["events"] == 2


@pytest.mark.skipif(os.name == "nt", reason="POSIX izinleri")
def test_permissions(tmp_path):
    with EventStore(tmp_path / "d" / "events.db") as s:
        s.append(env())
    assert stat.S_IMODE(os.stat(tmp_path / "d").st_mode) == 0o700
    assert stat.S_IMODE(os.stat(tmp_path / "d" / "events.db").st_mode) == 0o600


def test_read_only_reader_sees_writer_data(tmp_path):
    path = tmp_path / "events.db"
    with EventStore(path) as w:
        w.append(env())
        with EventStore(path, read_only=True) as r:
            assert r.count() == 1
            with pytest.raises(PermissionError):
                r.append(env(ts=NOW + timedelta(seconds=1)))


def test_stats_shape(store):
    store.append(env())
    st = store.stats()
    assert st["by_type"] == {"tool.call": 1} and st["db_bytes"] > 0 and st["oldest_ts"] == st["newest_ts"]
