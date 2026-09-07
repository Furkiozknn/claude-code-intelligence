from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from cci.analytics import (ConservationError, check_conservation, price_records, summarize_daily,
                           summarize_sessions, sum_tokens)
from cci.model import (AccountRef, CollectorRef, Cost, EvidenceClass, Figure, Flags, ModelRef, SessionRef,
                       SourceInstance, Tokens, UsageRecord, Workspace)
from cci.pricing import PricingTable

IST = ZoneInfo("Europe/Istanbul")
SRC = SourceInstance(provider="anthropic", instance_id="claude-config:x", label="Default Claude", kind="cli",
                     schema_verified=True, verified_at=date(2026, 9, 7))
COL = CollectorRef(name="transcript", version="0.0.1", schema_version=1)
ACC = AccountRef(provider="anthropic", account_key="acc")
TABLE = PricingTable.load_bundled()


def rec(i, *, ts, model="claude-opus-5", session="s1", project="p1", out=100, synthetic=False, sidechain=False,
        agent=None, split=True, vendor=None):
    tokens = Tokens(input=0, output=0) if synthetic else Tokens(
        input=1000, output=out, cache_read=2000, cache_write_total=500,
        cache_write_5m=300 if split else None, cache_write_1h=200 if split else None)
    return UsageRecord(
        provider="anthropic", source=SRC, account=ACC, session=SessionRef(session_id=session, is_sidechain=sidechain, agent_id=agent),
        request_id=f"req_{i}", ts=ts, model=ModelRef(id=model, display=model, unknown=(model == "<synthetic>")),
        tokens=tokens, cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "yok"),
                                 vendor_usd=Figure(value=vendor, unit="nanoUSD", evidence_class=EvidenceClass.VENDOR_ESTIMATED,
                                                   released=True, released_as="reconciled") if vendor is not None else None),
        workspace=Workspace(project_key=project), flags=Flags(synthetic=synthetic, api_error=synthetic), collector=COL)


T0 = datetime(2026, 9, 7, 10, 0, tzinfo=UTC)


def test_sum_tokens_keeps_split_only_when_all_known():
    a = Tokens(input=1, output=2, cache_read=3, cache_write_total=10, cache_write_5m=4, cache_write_1h=6)
    b = Tokens(input=1, output=2, cache_read=3, cache_write_total=5, cache_write_5m=5, cache_write_1h=0)
    s = sum_tokens([a, b])
    assert (s.input, s.output, s.cache_read, s.cache_write_total, s.cache_write_5m, s.cache_write_1h) == (2, 4, 6, 15, 9, 6)
    c = Tokens(input=1, output=1, cache_write_total=3)
    assert sum_tokens([a, c]).cache_write_5m is None and sum_tokens([a, c]).cache_write_total == 13


def test_price_records_fills_cost_and_marks_synthetic_zero():
    priced = price_records([rec(1, ts=T0), rec(2, ts=T0, synthetic=True, model="<synthetic>")], TABLE)
    assert priced[0].cost.usd.released and priced[0].cost.usd.estimator.id == "pricing.litellm"
    assert priced[0].cost.pricing_effective_at == TABLE.fetched_at
    assert priced[1].cost.usd.value == 0 and priced[1].cost.usd.evidence_class is EvidenceClass.OBSERVED


def test_daily_summary_groups_by_local_day_and_conserves():
    recs = price_records([
        rec(1, ts=T0), rec(2, ts=T0 + timedelta(hours=1), model="claude-sonnet-5", project="p2"),
        rec(3, ts=datetime(2026, 9, 7, 21, 30, tzinfo=UTC)),  # 00:30 Istanbul -> 8 Eylul
        rec(4, ts=T0, synthetic=True, model="<synthetic>"),
    ], TABLE)
    days = summarize_daily(recs, IST, pricing_version=TABLE.version, strict=True)
    assert [d.day for d in days] == [date(2026, 9, 7), date(2026, 9, 8)] and days[0].tz == "Europe/Istanbul"
    d0 = days[0]
    assert d0.totals.requests == 2 and d0.totals.synthetic == 1 and d0.conservation.ok
    assert [m.model_id for m in d0.models] == ["<synthetic>", "claude-opus-5", "claude-sonnet-5"]
    assert {p.project_key for p in d0.projects} == {"p1", "p2"}
    assert d0.totals.cost.released and d0.totals.cost.value == sum(m.totals.cost.value for m in d0.models)
    assert d0.totals.tokens.billable_total == sum(m.totals.tokens.billable_total for m in d0.models)
    assert d0.summary_version == 1 and d0.pricing_version == TABLE.version
    assert not d0.totals.vendor_cost.released and "yok" in d0.totals.vendor_cost.withheld_because


def test_unknown_model_withholds_day_cost_but_keeps_tokens():
    recs = price_records([rec(1, ts=T0), rec(2, ts=T0, model="gpt-9")], TABLE)
    d = summarize_daily(recs, IST)[0]
    assert not d.totals.cost.released and "bilinmeyen model" in d.totals.cost.withheld_because
    assert d.totals.tokens.billable_total > 0 and d.conservation.ok  # token korunumu maliyetten bagimsiz


def test_draft_cost_propagates_to_day():
    recs = price_records([rec(1, ts=T0, split=False), rec(2, ts=T0)], TABLE)
    d = summarize_daily(recs, IST)[0]
    assert d.totals.cost.released and d.totals.cost.released_as == "draft"


def test_vendor_cost_is_summed_when_complete_and_withheld_when_partial():
    full = price_records([rec(1, ts=T0, vendor=1_000_000_000), rec(2, ts=T0, vendor=500_000_000)], TABLE)
    assert summarize_daily(full, IST)[0].totals.vendor_cost.render() == "$1.50"
    partial = price_records([rec(1, ts=T0, vendor=1_000_000_000), rec(2, ts=T0)], TABLE)
    vc = summarize_daily(partial, IST)[0].totals.vendor_cost
    assert not vc.released and "1 kayitta eksik" in vc.withheld_because


def test_session_summary_basics():
    recs = price_records([rec(1, ts=T0, session="s1"), rec(2, ts=T0 + timedelta(minutes=5), session="s1", agent="a1"),
                          rec(3, ts=T0, session="s2", sidechain=True, project="p2")], TABLE)
    sessions = summarize_sessions(recs, strict=True)
    assert [s.session_id for s in sessions] == ["s1", "s2"]
    s1 = sessions[0]
    assert s1.totals.requests == 2 and s1.subagent_requests == 1 and s1.project_key == "p1"
    assert s1.started_at == T0 and s1.last_at == T0 + timedelta(minutes=5) and s1.conservation.ok
    assert sessions[1].sidechain_requests == 1


def test_conservation_violation_is_loud():
    from cci.analytics.summaries import ModelBucket, Totals, _totals
    recs = price_records([rec(1, ts=T0)], TABLE)
    totals = _totals(recs)
    bogus = ModelBucket(model_id="x", display="x", totals=_totals(price_records([rec(2, ts=T0, out=1)], TABLE)))
    c = check_conservation(totals, [bogus], [])
    assert not c.ok and "toplam=" in c.detail
    with pytest.raises(ConservationError):
        check_conservation(totals, [bogus], [], strict=True)
