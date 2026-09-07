"""Pace v1 - dogrusal hiz (docs/ANALYTICS.md §2.1; kaynak vibe-bar UsagePace, claude-pace).

expected = elapsed/duration*100 ; delta = actual - expected
asama: |d|<=2 on_track, <=6 slightly, <=12 ahead/behind, >12 far
eta = (100-actual)/(actual/elapsed) ; will_last = eta >= remaining
Kenar durumlar:
- utilization/resets_at/duration yoksa -> None (tahmin uydurma yok)
- pencere henuz acilmadi (remaining > duration) -> None
- elapsed == 0 ve actual > 0 -> None ("taze pencere geri dolduruldu")
- reset sonrasi 180 sn tolerans: allow_post_reset_grace ile reset-1 sn'de degerlendir
Kanit sinifi: delta/expected DERIVED; eta PREDICTED (dogrusal varsayim, estimator pace_v1).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Literal

from cci.model.base import CciModel, F
from cci.model.figure import EstimatorRef
from cci.model.quota import QuotaWindow

POST_RESET_GRACE_S = 180
PACE_ESTIMATOR = EstimatorRef(id="pace_v1", version="1.0")

Stage = Literal["on_track", "slightly_ahead", "ahead", "far_ahead", "slightly_behind", "behind", "far_behind"]


def stage_for(delta: float) -> Stage:
    a = abs(delta)
    if a <= 2:
        return "on_track"
    if a <= 6:
        return "slightly_ahead" if delta > 0 else "slightly_behind"
    if a <= 12:
        return "ahead" if delta > 0 else "behind"
    return "far_ahead" if delta > 0 else "far_behind"


def evaluation_time(resets_at: datetime, now: datetime, *, allow_post_reset_grace: bool = False) -> datetime | None:
    """Reset gecmisse ve tolerans icindeysek reset-1 sn; degilse None."""
    remaining = (resets_at - now).total_seconds()
    if remaining > 0:
        return now
    if not allow_post_reset_grace or remaining < -POST_RESET_GRACE_S:
        return None
    return resets_at - timedelta(seconds=1)


class Pace(CciModel):
    stage: Stage = F("public")
    delta_pct: float = F("internal")
    expected_pct: float = F("internal", ge=0, le=100)
    actual_pct: float = F("internal", ge=0, le=100)
    elapsed_s: float = F("internal", ge=0)
    remaining_s: float = F("internal", ge=0)
    eta_s: float | None = F("internal", default=None, ge=0)   # 100'e ulasma suresi (dogrusal), predicted
    will_last_to_reset: bool = F("public")
    estimator: EstimatorRef = F("internal", default=PACE_ESTIMATOR)

    @property
    def run_out_at(self) -> timedelta | None:
        return None if self.eta_s is None else timedelta(seconds=self.eta_s)


def compute_pace(window: QuotaWindow, now: datetime, *, allow_post_reset_grace: bool = False) -> Pace | None:
    if window.utilization is None or window.resets_at is None or not window.duration_s:
        return None
    eval_at = evaluation_time(window.resets_at, now, allow_post_reset_grace=allow_post_reset_grace)
    if eval_at is None:
        return None
    duration = float(window.duration_s)
    remaining = (window.resets_at - eval_at).total_seconds()
    if remaining > duration:
        return None  # pencere henuz acilmadi
    elapsed = min(max(duration - remaining, 0.0), duration)
    expected = min(max(elapsed / duration * 100.0, 0.0), 100.0)
    actual = min(max(window.utilization * 100.0, 0.0), 100.0)
    if elapsed == 0 and actual > 0:
        return None  # taze pencere, geri doldurulmus durum
    delta = actual - expected
    eta: float | None = None
    will_last = False
    if elapsed > 0 and actual > 0:
        rate = actual / elapsed  # yuzde / saniye
        candidate = max(0.0, 100.0 - actual) / rate
        if candidate >= remaining:
            will_last = True
        else:
            eta = candidate
    elif elapsed > 0 and actual == 0:
        will_last = True
    return Pace(stage=stage_for(delta), delta_pct=delta, expected_pct=expected, actual_pct=actual,
                elapsed_s=elapsed, remaining_s=remaining, eta_s=eta, will_last_to_reset=will_last)
