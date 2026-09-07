from datetime import UTC, datetime, timedelta

import pytest

from cci.model import QuotaWindow
from cci.quota import POST_RESET_GRACE_S, compute_pace, evaluation_time, stage_for

H5 = 5 * 3600
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def window(util, remaining_s, duration=H5, kind="session_5h"):
    return QuotaWindow(kind=kind, duration_s=duration, utilization=util, resets_at=NOW + timedelta(seconds=remaining_s))


@pytest.mark.parametrize("delta,stage", [(0, "on_track"), (2, "on_track"), (-2, "on_track"), (5, "slightly_ahead"),
                                         (-5, "slightly_behind"), (10, "ahead"), (-10, "behind"), (30, "far_ahead"),
                                         (-30, "far_behind")])
def test_stage_thresholds(delta, stage):
    assert stage_for(delta) == stage


def test_on_track_when_usage_matches_elapsed_fraction():
    p = compute_pace(window(0.5, remaining_s=H5 / 2), NOW)
    assert p.stage == "on_track" and p.delta_pct == 0 and p.expected_pct == 50 and p.will_last_to_reset
    assert p.eta_s is None and p.estimator.id == "pace_v1"


def test_ahead_gives_eta_before_reset():
    # 2.5 saat gecti, %80 kullanildi -> hiz %32/saat -> kalan %20 icin 0.625 saat < 2.5 saat
    p = compute_pace(window(0.8, remaining_s=H5 / 2), NOW)
    assert p.stage == "far_ahead" and p.delta_pct == pytest.approx(30)
    assert p.eta_s == pytest.approx(0.625 * 3600) and not p.will_last_to_reset
    assert p.run_out_at == timedelta(seconds=p.eta_s)


def test_behind_lasts_to_reset():
    p = compute_pace(window(0.1, remaining_s=H5 / 2), NOW)
    assert p.stage == "far_behind" and p.will_last_to_reset and p.eta_s is None


def test_zero_usage_after_elapsed_time_lasts():
    p = compute_pace(window(0.0, remaining_s=H5 / 4), NOW)
    assert p.will_last_to_reset and p.stage == "far_behind"


def test_fresh_window_with_backfilled_usage_yields_none():
    assert compute_pace(window(0.3, remaining_s=H5), NOW) is None


def test_window_not_yet_open_yields_none():
    assert compute_pace(window(0.0, remaining_s=H5 + 60), NOW) is None


def test_missing_fields_yield_none():
    assert compute_pace(QuotaWindow(kind="session_5h", duration_s=H5, utilization=0.5), NOW) is None
    assert compute_pace(QuotaWindow(kind="unclassified", utilization=0.5, resets_at=NOW + timedelta(hours=1)), NOW) is None
    assert compute_pace(window(None, remaining_s=100), NOW) is None


def test_post_reset_grace():
    resets_at = NOW - timedelta(seconds=30)
    assert evaluation_time(resets_at, NOW) is None
    assert evaluation_time(resets_at, NOW, allow_post_reset_grace=True) == resets_at - timedelta(seconds=1)
    assert evaluation_time(NOW - timedelta(seconds=POST_RESET_GRACE_S + 1), NOW, allow_post_reset_grace=True) is None
    w = QuotaWindow(kind="session_5h", duration_s=H5, utilization=0.9, resets_at=resets_at)
    assert compute_pace(w, NOW) is None
    p = compute_pace(w, NOW, allow_post_reset_grace=True)
    assert p is not None and p.remaining_s == 1 and p.expected_pct == pytest.approx(100 - 100 / H5, abs=0.01)


def test_weekly_window_scale():
    week = 7 * 86400
    p = compute_pace(window(0.84, remaining_s=3 * 86400 + 7 * 3600, duration=week, kind="weekly_all"), NOW)
    assert p.expected_pct == pytest.approx((week - (3 * 86400 + 7 * 3600)) / week * 100)
    assert p.stage in ("far_ahead", "ahead", "slightly_ahead", "on_track")
