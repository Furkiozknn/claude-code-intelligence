import math
from datetime import UTC, datetime, timedelta

from cci.model import AccountRef, QuotaSnapshot, QuotaWindow
from cci.quota.forecast import backtest, blend, cycles, forecast, observations

ACC = AccountRef(provider="anthropic", account_key="acc")
H5 = 5 * 3600
T0 = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


def snap(at, util, resets_at):
    return QuotaSnapshot(snapshot_id=f"s-{at.isoformat()}", provider="anthropic", account=ACC, fetched_at=at, source="usage_api",
                         authoritative=True, raw_hash="a" * 64,
                         windows=(QuotaWindow(kind="session_5h", duration_s=H5, utilization=util, resets_at=resets_at),))


def curve(p, peak=0.9, k=1.2):
    return min(1.0, peak * (p ** k))


def history(n_cycles, per_cycle=8, peak=0.9, current_progress=0.5, jitter=0.0):
    """n tamamlanmis dongu + mevcut dongu (current_progress'e kadar). Doner: (snapshots, now)."""
    snaps = []
    start = T0
    for c in range(n_cycles):
        resets = start + timedelta(seconds=H5)
        pk = peak + (jitter * ((-1) ** c))
        for i in range(1, per_cycle + 1):
            p = i / per_cycle
            snaps.append(snap(start + timedelta(seconds=H5 * p), curve(p, pk), resets))
        start = resets
    resets = start + timedelta(seconds=H5)
    now = start + timedelta(seconds=H5 * current_progress)
    for i in range(1, per_cycle + 1):
        p = i / per_cycle
        if p <= current_progress:
            snaps.append(snap(start + timedelta(seconds=H5 * p), curve(p, peak), resets))
    return snaps, now


def test_observations_and_cycles_split_done_vs_current():
    snaps, now = history(3)
    obs = observations(snaps, "session_5h")
    done, current = cycles(obs, now)
    assert len(done) == 3 and current is not None and current.resets_at > now
    assert all(c.obs[0].at < c.obs[-1].at for c in done) and math.isclose(done[0].peak, 0.9)


def test_learning_gate_with_few_cycles():
    snaps, now = history(2)
    f = forecast(snaps, "session_5h", now)
    assert f is not None and f.verdict == "learning" and f.projected_at_reset is None
    assert not f.value.released and "2/5" in f.value.withheld_because and f.cycles_completed == 2


def test_forecast_after_enough_cycles_projects_within_band_and_not_learning():
    snaps, now = history(6, current_progress=0.5)
    f = forecast(snaps, "session_5h", now)
    assert f is not None and f.verdict != "learning" and f.confidence in ("medium", "high")
    proj = float(f.projected_at_reset.median)
    assert f.current_utilization * 100 <= proj <= 100
    assert float(f.projected_at_reset.band.lo) <= 90.0 <= float(f.projected_at_reset.band.hi) + 5  # gercek tepe 90
    assert f.value.released and f.value.evidence_class.value == "predicted" and f.value.estimator.id == "blend_v2"
    assert f.diagnostics["cycles_completed"] == 6 and f.diagnostics["recent_n"] >= 2
    assert f.verdict in ("enough", "watch")


def test_at_risk_when_projection_exceeds_100():
    snaps, now = history(6, peak=1.0, current_progress=0.6)
    for i in range(3):  # son gozlemleri sertlestir: hizli tuketim
        snaps.append(snap(now + timedelta(minutes=5 * (i + 1)), min(1.0, 0.7 + 0.1 * (i + 1)), snaps[-1].windows[0].resets_at))
    now2 = now + timedelta(minutes=16)
    f = forecast(snaps, "session_5h", now2)
    assert f is not None and f.verdict in ("at_risk", "watch") and f.run_out_at is not None and f.run_out_at >= now2
    # henuz %100 degilken: hizli egimle run_out gelecekte
    snaps2, now3 = history(6, peak=1.0, current_progress=0.6)
    resets = snaps2[-1].windows[0].resets_at
    for i, u in enumerate((0.74, 0.8, 0.86)):
        snaps2.append(snap(now3 + timedelta(minutes=5 * (i + 1)), u, resets))
    f2 = forecast(snaps2, "session_5h", now3 + timedelta(minutes=16))
    assert f2 is not None and f2.run_out_at is not None and f2.run_out_at > now3 + timedelta(minutes=16)


def test_blend_uses_only_past_data_and_backtest_reports_methods():
    snaps, now = history(7, jitter=0.03)
    rep = backtest(snaps, "session_5h", now)
    assert rep["cycles"] == 7 and rep["evaluations"] > 0 and set(rep["methods"]) == {"last_value", "linear", "recent", "historical", "blend"}
    assert rep["methods"]["blend"]["mae"] is not None and rep["best"] is not None
    assert rep["methods"]["blend"]["mae"] < rep["methods"]["last_value"]["mae"]
    assert 0 <= rep["blend_band_coverage"] <= 1


def test_no_current_cycle_returns_none():
    snaps, now = history(2)
    assert forecast(snaps, "session_5h", now + timedelta(days=2)) is None
    assert forecast([], "session_5h", now) is None


def test_blend_fresh_window_bails_without_progress():
    snaps, now = history(6, current_progress=0.125)
    f = forecast(snaps, "session_5h", now)
    assert f is not None  # ilerleme %12.5: fallback + tarihsel var
    assert f.diagnostics["progress"] > 0.1
