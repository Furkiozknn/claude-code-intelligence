from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from cci.analytics.anomaly import baseline, blocks_from_records, detect
from cci.events import Envelope, SourceRef
from cci.model import (AccountRef, CollectorRef, Cost, EvidenceClass, Figure, ModelRef, SessionRef, SourceInstance,
                       Tokens, UsageRecord)

SRC = SourceInstance(provider="anthropic", instance_id="x", label="x", kind="cli", schema_verified=True, verified_at=date(2026, 9, 7))
COL = CollectorRef(name="transcript", version="0.0.1", schema_version=1)
ESRC = SourceRef(collector="otlp", instance_id="otlp:claude-code", collector_version="0.0.1", schema_version=1)
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def rec(i, ts, tokens=1000, session="s1"):
    return UsageRecord(provider="anthropic", source=SRC, account=None, session=SessionRef(session_id=session), request_id=f"r{i}",
                       ts=ts, model=ModelRef(id="claude-opus-5", display="Opus 5"), tokens=Tokens(input=tokens, output=10),
                       cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "x")), collector=COL)


def history(days=3, per_block=5, tokens=1000):
    """Gunde 2 blok (09:00, 15:00), blok basina `per_block` istek."""
    recs = []
    i = 0
    for d in range(days, 0, -1):
        for hour in (9, 15):
            start = NOW - timedelta(days=d)
            start = start.replace(hour=hour, minute=5)
            for k in range(per_block):
                recs.append(rec(i, start + timedelta(minutes=10 * k), tokens=tokens))
                i += 1
    return recs


def test_blocks_follow_ccusage_rules():
    recs = history(days=2)
    blocks = blocks_from_records(recs, NOW)
    assert len(blocks) == 4 and all(b.start.minute == 0 for b in blocks) and not blocks[-1].active
    assert all(b.requests == 5 and b.tokens == 5 * 1010 for b in blocks)
    active = blocks_from_records(recs + [rec(99, NOW - timedelta(minutes=30))], NOW)
    assert active[-1].active and len(active) == 5


def test_baseline_requires_enough_blocks():
    b = baseline(history(days=1), [], NOW)
    assert b.block_tokens_p50 is None and any("blok" in n for n in b.notes)
    b2 = baseline(history(days=3), [Decimal(1_000_000_000)] * 5, NOW)
    assert b2.blocks_completed == 6 and b2.block_tokens_p50 == 5050.0 and b2.session_cost_p50_nano == Decimal(1_000_000_000)


def test_volume_ratio_warning_and_critical():
    past = history(days=3)  # 30 kayit, blok P50 = 5050
    hot = [rec(200 + k, NOW - timedelta(minutes=60 - k), tokens=2500) for k in range(5)]  # aktif blok 12550 -> 2.5x
    anomalies, base = detect(past + hot, [], NOW)
    kinds = {a.kind: a for a in anomalies}
    assert "volume.ratio" in kinds and kinds["volume.ratio"].severity == "warning"
    assert kinds["volume.ratio"].evidence[0].ratio >= 2
    hotter = [rec(300 + k, NOW - timedelta(minutes=60 - k), tokens=6000) for k in range(5)]  # 30050 -> 5.9x
    anomalies2, _ = detect(past + hotter, [], NOW)
    assert {a.kind: a.severity for a in anomalies2}["volume.ratio"] == "critical"


def test_no_volume_alert_without_baseline_or_records():
    few = history(days=1) + [rec(50, NOW - timedelta(minutes=5), tokens=100000)]
    anomalies, base = detect(few, [], NOW)
    assert not [a for a in anomalies if a.kind == "volume.ratio"] and base.block_tokens_p50 is None


def test_cost_spike_and_retry_storm_and_schema_change():
    costs = {f"s{i}": Decimal(500_000_000) for i in range(6)}
    costs["big"] = Decimal(2_500_000_000)  # 5x
    errors = [Envelope(type="usage.error", ts=NOW - timedelta(minutes=m), source=ESRC, provider="anthropic", session_id="s1",
                       payload={"status_code": 429 if m % 2 else 529, "attempt": 2}) for m in range(1, 7)]
    change = Envelope(type="provider.schema_change", ts=NOW - timedelta(hours=1), source=ESRC, provider="anthropic",
                      payload={"field_added": "x"})
    anomalies, _ = detect(history(days=3), errors + [change], NOW, session_costs=costs)
    kinds = {a.kind: a for a in anomalies}
    assert kinds["cost.spike"].subject_id == "big" and kinds["cost.spike"].severity == "critical"
    assert kinds["retry.storm"].severity == "critical" and kinds["retry.storm"].evidence[0].value == 6
    assert kinds["rate_limit.burst"].severity == "warning" and kinds["provider.schema_change"].severity == "info"
