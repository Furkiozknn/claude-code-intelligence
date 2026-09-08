import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from cci.act import apply_file_change, list_records, undo
from cci.advisor import advise
from cci.analytics.anomaly import Anomaly
from cci.analytics.diagnostics import ContextUtilization, LoopFingerprint, SessionDiagnostics
from cci.model import AccountRef, Evidence, QuotaSnapshot, QuotaWindow

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
H5 = 5 * 3600


def quota(util, remaining_s):
    return QuotaSnapshot(snapshot_id="q", provider="anthropic", account=AccountRef(provider="anthropic", account_key="a"), fetched_at=NOW,
                         source="usage_api", authoritative=True, raw_hash="a" * 64,
                         windows=(QuotaWindow(kind="session_5h", duration_s=H5, utilization=util, resets_at=NOW + timedelta(seconds=remaining_s)),))


def diag(loops=0, ctx=None, attention="ok"):
    lp = tuple(LoopFingerprint(tool_name="Bash", fingerprint="f", count=4, first_index=0, last_index=3, severity="high") for _ in range(loops))
    c = ContextUtilization(used_pct=ctx, risk="critical") if ctx else None
    return SessionDiagnostics(session_id="sess-1", requests=1, errors=0, retry_events=0, error_rate=0, tool_calls=4, tool_failures=0,
                              tool_timeouts=0, loops=lp, compactions=0, context=c, health=60 if loops else 100, attention=attention)


def test_ladder_wait_vs_reduce_and_ok():
    # %99 / 30 dk kalan: bu hizla reset'ten once tukenir -> bekle
    recs = advise(now=NOW, quota=quota(0.99, 1800), forecasts={}, diagnostics=[], anomalies=[], telemetry_enabled=True)
    assert recs[0].kind == "wait_for_reset" and recs[0].action.type == "wait" and not recs[0].expected.released
    # %90 / 30 dk kalan: beklenen hizda -> uyari yok
    assert [r.kind for r in advise(now=NOW, quota=quota(0.9, 1800), forecasts={}, diagnostics=[], anomalies=[], telemetry_enabled=True)] == ["ok"]
    recs = advise(now=NOW, quota=quota(0.9, 2 * 3600), forecasts={}, diagnostics=[], anomalies=[], telemetry_enabled=True)
    assert recs[0].kind == "reduce_spend"
    recs = advise(now=NOW, quota=quota(0.1, 2 * 3600), forecasts={}, diagnostics=[], anomalies=[], telemetry_enabled=True)
    assert [r.kind for r in recs] == ["ok"]


def test_ladder_session_and_telemetry_and_anomaly():
    an = Anomaly(kind="retry.storm", severity="critical", subject_kind="session", subject_id="sess-1", message="6 hata",
                 evidence=(Evidence(metric="errors_10m", value=Decimal(6), evidence_class="observed"),))
    recs = advise(now=NOW, quota=None, forecasts={}, diagnostics=[diag(loops=1, ctx=90, attention="loops")], anomalies=[an], telemetry_enabled=False)
    kinds = [r.kind for r in recs]
    assert kinds == ["stop_loop", "compact_context", "back_off", "enable_otlp"]
    assert recs[-1].action.type == "settings_change" and recs[-1].action.reversible and recs[-1].action.plan_hash
    assert all(r.why for r in recs)


def test_act_apply_undo_stale_and_force(tmp_path):
    data, f = tmp_path / "d", tmp_path / "settings.json"
    f.write_text('{"a":1}', encoding="utf-8")
    rec = apply_file_change(data, f, '{"a":1,"env":{}}', "env ekle")
    assert f.read_text(encoding="utf-8") == '{"a":1,"env":{}}' and rec["backup"] and rec["hash_before"] != rec["hash_after"]
    with pytest.raises(RuntimeError):
        apply_file_change(data, f, "x", "bayat", expected_hash=rec["hash_before"])
    f.write_text("{}", encoding="utf-8")  # kullanici sonradan degistirdi
    with pytest.raises(RuntimeError):
        undo(data, rec["id"])
    u = undo(data, rec["id"][:8], force=True)
    assert f.read_text(encoding="utf-8") == '{"a":1}' and u["status"] == "reverted"
    with pytest.raises(RuntimeError):
        undo(data, rec["id"], force=True)
    new = apply_file_change(data, tmp_path / "yeni.json", "{}", "yeni dosya")
    assert new["backup"] is None
    undo(data, new["id"])
    assert not (tmp_path / "yeni.json").exists() and len(list_records(data)) == 4
