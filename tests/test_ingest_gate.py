from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cci.events import EVENT_TYPES, Envelope, SourceRef, new_ulid, payload_hash
from cci.ingest import EVENT_ALLOWLIST, IngestGate, find_forbidden_key

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
SRC = SourceRef(collector="otlp", instance_id="claude-config:abc", collector_version="0.0.1",
                schema_version=1)


def env(type_="tool.call", payload=None, **kw):
    return Envelope(type=type_, ts=NOW, source=SRC, provider="anthropic",
                    payload=payload if payload is not None else {"tool_name": "Read", "success": True},
                    **kw)


def test_ulid_is_26_chars_and_time_ordered():
    a, b = new_ulid(1_000), new_ulid(2_000)
    assert len(a) == 26 and a < b


def test_payload_hash_is_key_order_independent():
    assert payload_hash({"a": 1, "b": [1, 2]}) == payload_hash({"b": [1, 2], "a": 1})
    assert env().payload_hash == payload_hash({"tool_name": "Read", "success": True})


def test_allowlist_covers_exactly_the_catalog():
    assert set(EVENT_ALLOWLIST) == set(EVENT_TYPES)


def test_accepts_clean_event():
    gate = IngestGate()
    d = gate.check(env())
    assert d.accepted and d.reason == "ok" and gate.counters["ok"] == 1


def test_unknown_type_is_dropped_not_errored():
    gate = IngestGate()
    d = gate.check(env("weird.thing", {"x": 1}))
    assert not d.accepted and d.dropped and gate.counters["dropped_unknown_type"] == 1


@pytest.mark.parametrize("payload", [
    {"tool_name": "Bash", "tool_input": {"command": "rm -rf /"}},
    {"tool_name": "Read", "nested": {"deeper": {"prompt": "gizli"}}},
    {"tool_name": "Read", "items": [{"Authorization": "Bearer x"}]},
    {"tool_name": "Read", "note_text": "icerik"},
    {"tool_name": "Read", "user_email": "a@b.c"},
])
def test_forbidden_keys_are_rejected_without_naming_them(payload):
    gate = IngestGate()
    d = gate.check(env(payload=payload))
    assert not d.accepted and d.reason == "rejected_forbidden_key"
    for key in ("tool_input", "prompt", "Authorization", "note_text", "user_email"):
        assert key not in d.reason


def test_extra_keys_outside_allowlist_are_rejected():
    gate = IngestGate()
    d = gate.check(env(payload={"tool_name": "Read", "cwd": "/home/x"}))
    assert not d.accepted and d.reason == "rejected_extra_key"


def test_too_large_is_rejected():
    gate = IngestGate(max_bytes=200)
    d = gate.check(env(payload={"tool_name": "R" * 500}))
    assert not d.accepted and d.reason == "rejected_too_large"


def test_filter_keeps_only_accepted_and_counts():
    gate = IngestGate()
    kept = gate.filter([env(), env("nope.x", {"a": 1}), env(payload={"tool_name": "R", "body": "x"})])
    assert len(kept) == 1
    assert gate.counters == {"ok": 1, "dropped_unknown_type": 1, "rejected_forbidden_key": 1}


def test_envelope_shape_rules():
    with pytest.raises(ValidationError):
        env("ToolCall")  # nokta yok / buyuk harf
    with pytest.raises(ValidationError):
        Envelope(type="tool.call", ts=datetime(2026, 9, 7), source=SRC)  # naive ts
    e = env()
    assert e.known_type and e.lag_s >= 0 and e.privacy_class == "internal"


def test_find_forbidden_key_depth_guard():
    deep: dict = {}
    cur = deep
    for _ in range(40):
        cur["n"] = {}
        cur = cur["n"]
    assert find_forbidden_key(deep) is True  # asiri derinlik = supheli, reddet
