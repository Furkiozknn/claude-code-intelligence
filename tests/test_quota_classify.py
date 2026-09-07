from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from cci.model import (AccountRef, QuotaSnapshot, QuotaWindow, WindowScope, classify_duration,
                       normalize_windows)

DAY = 86400
NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize("duration,scoped,expected", [
    (5 * 3600, False, "session_5h"),
    (7 * DAY, False, "weekly_all"),
    (7 * DAY, True, "weekly_scoped"),
    (28 * DAY, False, "monthly"),
    (30 * DAY, False, "monthly"),
    (31 * DAY, False, "monthly"),
    (27 * DAY, False, "unclassified"),
    (4 * 3600, False, "unclassified"),
    (None, False, "unclassified"),
])
def test_classify_by_duration(duration, scoped, expected):
    assert classify_duration(duration, scoped=scoped) == expected


def w(kind="unclassified", duration=None, util=0.5, model=None):
    return QuotaWindow(kind=kind, duration_s=duration, utilization=util, resets_at=NOW,
                       scope=WindowScope(model_display=model))


def test_declared_kind_is_overridden_by_duration():
    out, ok = normalize_windows([w(kind="weekly_all", duration=5 * 3600)])
    assert out[0].kind == "session_5h" and ok


def test_five_hour_plus_weekly_is_authoritative():
    out, ok = normalize_windows([w(duration=5 * 3600), w(duration=7 * DAY)])
    assert [x.kind for x in out] == ["session_5h", "weekly_all"] and ok


def test_duplicate_kind_is_not_authoritative():
    _, ok = normalize_windows([w(duration=5 * 3600), w(duration=5 * 3600)])
    assert not ok


def test_unclassified_window_is_not_authoritative():
    out, ok = normalize_windows([w(duration=5 * 3600), w(duration=27 * DAY)])
    assert out[1].kind == "unclassified" and not ok


def test_scoped_windows_are_per_model():
    _, ok = normalize_windows([w(duration=7 * DAY, model="Opus"), w(duration=7 * DAY, model="Sonnet")])
    assert ok
    _, ok2 = normalize_windows([w(duration=7 * DAY, model="Opus"), w(duration=7 * DAY, model="Opus")])
    assert not ok2


def test_declared_kinds_kept_when_duration_unknown():
    out, ok = normalize_windows([w(kind="session_5h"), w(kind="weekly_all", model="Opus")])
    assert [x.kind for x in out] == ["session_5h", "weekly_scoped"] and ok


def test_snapshot_build_sets_authoritative_and_storable():
    snap = QuotaSnapshot.build(
        snapshot_id="s1", provider="anthropic",
        account=AccountRef(provider="anthropic", account_key="acc-uuid"),
        fetched_at=NOW, source="usage_api", raw_hash="a" * 64,
        windows=[w(duration=5 * 3600, util=0.72), w(duration=7 * DAY, util=0.84)],
    )
    assert snap.authoritative and snap.storable
    assert snap.window("session_5h").utilization == 0.72
    assert snap.window("weekly_all").utilization == 0.84
    assert snap.window("monthly") is None


def test_snapshot_without_account_is_not_storable():
    snap = QuotaSnapshot.build(snapshot_id="s2", provider="anthropic", fetched_at=NOW,
                               source="statusline", raw_hash="b" * 64, windows=[w(duration=5 * 3600)])
    assert not snap.storable


def test_utilization_is_a_ratio_not_percent():
    with pytest.raises(ValidationError):
        QuotaWindow(kind="session_5h", utilization=72.0)


def test_naive_reset_time_rejected():
    with pytest.raises(ValidationError):
        QuotaWindow(kind="session_5h", resets_at=datetime(2026, 9, 7, 12, 0))
