from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from cci.model import (AccountRef, Attribution, CollectorRef, Cost, EvidenceClass, Figure, Flags,
                       ModelRef, SessionRef, SourceInstance, Tokens, UsageRecord)

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
SRC = SourceInstance(provider="anthropic", instance_id="cli-1", label="Default Claude", kind="cli",
                     schema_verified=True)
COL = CollectorRef(name="transcript", version="0.0.1", schema_version=1)


def rec(**over):
    base = dict(
        provider="anthropic", source=SRC, session=SessionRef(session_id="sess-1"),
        message_id="msg_1", request_id="req_1", ts=NOW,
        model=ModelRef(id="claude-opus-5", display="Opus 5"),
        tokens=Tokens(input=100, output=20, cache_read=40, cache_write_5m=6, cache_write_1h=4,
                      cache_write_total=10),
        cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "fiyat tablosu yok")),
        collector=COL,
    )
    base.update(over)
    return UsageRecord(**base)


def test_dedup_key_with_request_id_is_source_independent():
    # OTel api_request (message_id yok) ile transcript kaydi ayni anahtara duser
    assert rec().dedup_key == "anthropic:req:req_1"
    assert rec(message_id=None, uuid="u-otel").dedup_key == "anthropic:req:req_1"
    assert rec().message_key == "anthropic:msg:msg_1:sess-1"


def test_dedup_key_without_request_id():
    assert rec(request_id=None).dedup_key == "anthropic:msg:msg_1:sess-1"


def test_dedup_key_uuid_fallback():
    assert rec(message_id=None, request_id=None, uuid="u-1").dedup_key == "anthropic:uuid:u-1:sess-1"


def test_missing_all_ids_raises():
    with pytest.raises(ValidationError):
        rec(request_id=None, message_id=None, uuid=None)
    assert rec(message_id=None, uuid=None).dedup_key == "anthropic:req:req_1"  # yalniz request_id yeter


def test_record_id_is_stable_and_derived_from_key():
    a, b = rec(), rec(ts=NOW + timedelta(seconds=5))
    assert a.record_id == b.record_id and len(a.record_id) == 32


def test_input_total_includes_cache():
    t = rec().tokens
    assert t.input == 100 and t.input_total == 150 and t.billable_total == 170


def test_cache_split_must_sum_to_total():
    with pytest.raises(ValidationError):
        Tokens(input=1, output=1, cache_write_5m=5, cache_write_1h=5, cache_write_total=11)


def test_timestamp_rules():
    with pytest.raises(ValidationError):
        rec(ts=datetime(2026, 9, 7, 12, 0))  # naive
    with pytest.raises(ValidationError):
        rec(ts=datetime(1999, 12, 31, tzinfo=UTC))
    assert rec(ts=datetime(2026, 9, 7, 15, 0, tzinfo=UTC).astimezone()).ts.tzinfo is UTC


def test_synthetic_record_cannot_carry_tokens():
    with pytest.raises(ValidationError):
        rec(flags=Flags(synthetic=True))
    ok = rec(flags=Flags(synthetic=True), tokens=Tokens(input=0, output=0),
             model=ModelRef(id="<synthetic>", display="synthetic", unknown=True))
    assert ok.flags.synthetic


def test_vendor_cost_must_be_vendor_estimated():
    with pytest.raises(ValidationError):
        rec(cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "x"),
                      vendor_usd=Figure.observed(1, "nanoUSD")))


def test_prefer_over_rules():
    small = rec()
    big = rec(tokens=Tokens(input=500, output=20))
    assert big.prefer_over(small) and not small.prefer_over(big)
    parent = rec()
    replay = rec(session=SessionRef(session_id="sess-1", is_sidechain=True),
                 tokens=Tokens(input=9999, output=1))
    assert parent.prefer_over(replay) and not replay.prefer_over(parent)
    old = rec()
    new = rec(attribution=Attribution(speed="fast"))
    assert new.prefer_over(old) and not old.prefer_over(new)


def test_extra_keys_rejected_everywhere():
    with pytest.raises(ValidationError):
        rec(prompt_text="gizli")
    with pytest.raises(ValidationError):
        AccountRef(provider="anthropic", account_key="k", token="sk-ant-x")  # type: ignore[call-arg]
