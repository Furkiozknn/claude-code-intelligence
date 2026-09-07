"""Stage 10 - harman tahmin v2 + backtest (docs/ANALYTICS.md §2.2-2.3; kaynak vibe-bar QuotaPaceForecast).

Yalniz KOTA GOZLEMLERI kullanilir (token -> yuzde donusumu yok). Adaylar:
  yakin egim   0.52 * min(1, n/6)   : mevcut dongudeki son gozlemlerden egim
  tarihsel     0.34 * min(1, k/5)   : tamamlanmis dongulerde ayni ilerlemeden sonra eklenen (medyan)
  davranissal  0.14                 : actual/progress (dogrusal; aktivite haritasi yok)
projected = max(actual, agirlikli ort.)  ; guven = kapsama*0.38 + gecmis*0.30 + tazelik*0.20 + aktivite*0.12
bant = clamp(max(4, 18(1-conf)) + min(12, 0.35*MAD*1.4826 + 0.5*spread), 4, 28)
hedef = clamp(5 + (1-conf)*8, 5, 13) ; hukum atRisk > watch > (learning) > surplus > enough
R-7 kapisi: tamamlanmis dongu < 5 veya guven learning -> hukum learning, projeksiyon YOK, deger withheld.
Backtest: tamamlanmis dongulerde her gozlem aninda "reset'teki kullanim" tahmini vs gercek (MAE, bant kapsama).
"""

from __future__ import annotations

import hashlib
import statistics
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Sequence

from cci.model.estimate import LEARNING_MIN_CYCLES, ProjectedAtReset, QuotaForecast
from cci.model.evidence import EvidenceClass
from cci.model.figure import Band, EstimatorRef, Figure
from cci.model.quota import QuotaSnapshot, QuotaWindow, WindowKind

FORECAST_ESTIMATOR = EstimatorRef(id="blend_v2", version="1.0")
W_RECENT, W_HIST, W_FALLBACK = 0.52, 0.34, 0.14
RECENT_N = 6


@dataclass(frozen=True)
class Obs:
    at: datetime
    util: float          # 0..1
    resets_at: datetime
    duration_s: int

    @property
    def start(self) -> datetime:
        return self.resets_at - timedelta(seconds=self.duration_s)

    @property
    def progress(self) -> float:
        p = (self.at - self.start).total_seconds() / self.duration_s
        return min(max(p, 0.0), 1.0)


@dataclass(frozen=True)
class Cycle:
    resets_at: datetime
    obs: tuple[Obs, ...]   # zaman sirali

    @property
    def peak(self) -> float:
        return max(o.util for o in self.obs)

    def util_at(self, progress: float) -> float:
        """Ilerleme noktasindaki kullanim (dogrusal ara deger; disinda uc deger)."""
        pts = self.obs
        if progress <= pts[0].progress:
            return pts[0].util * (progress / pts[0].progress) if pts[0].progress > 0 else pts[0].util
        for a, b in zip(pts, pts[1:]):
            if a.progress <= progress <= b.progress:
                span = b.progress - a.progress
                return a.util if span <= 0 else a.util + (b.util - a.util) * (progress - a.progress) / span
        return pts[-1].util


def observations(history: Iterable[QuotaSnapshot], kind: WindowKind, model_display: str | None = None) -> list[Obs]:
    out: list[Obs] = []
    for snap in history:
        w = snap.window(kind, model_display)
        if w is None or w.utilization is None or w.resets_at is None or not w.duration_s:
            continue
        out.append(Obs(at=snap.fetched_at, util=w.utilization, resets_at=w.resets_at, duration_s=w.duration_s))
    out.sort(key=lambda o: o.at)
    return out


def cycles(obs: Sequence[Obs], now: datetime) -> tuple[list[Cycle], Cycle | None]:
    """(tamamlanmis donguler, mevcut dongu). Dongu = ayni resets_at."""
    groups: dict[datetime, list[Obs]] = {}
    for o in obs:
        groups.setdefault(o.resets_at, []).append(o)
    done: list[Cycle] = []
    current: Cycle | None = None
    for resets_at, items in sorted(groups.items()):
        items.sort(key=lambda o: o.at)
        c = Cycle(resets_at=resets_at, obs=tuple(items))
        if resets_at <= now:
            if len(items) >= 2:
                done.append(c)
        elif current is None or resets_at > current.resets_at:
            current = c
    return done, current


def _mad(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    med = statistics.median(values)
    return statistics.median(abs(v - med) for v in values)


def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def recent_slope(current: Cycle, n: int = RECENT_N) -> tuple[float | None, int, float]:
    """(egim: kullanim/ilerleme, ornek sayisi, yayilim). En az 2 nokta ve ilerleme farki > 0.01."""
    pts = current.obs[-n:]
    if len(pts) < 2 or pts[-1].progress - pts[0].progress <= 0.01:
        return None, len(pts), 0.0
    xs = [p.progress for p in pts]
    ys = [p.util for p in pts]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    denom = sum((x - mx) ** 2 for x in xs)
    slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom if denom > 0 else 0.0
    resid = [y - (my + slope * (x - mx)) for x, y in zip(xs, ys)]
    spread = statistics.pstdev(resid) * 100 if len(resid) > 1 else 0.0
    return slope, len(pts), spread


def historical_additions(done: Sequence[Cycle], progress: float) -> list[float]:
    """Her tamamlanmis dongude ayni ilerlemeden sonra eklenen kullanim (0..1)."""
    return [max(0.0, c.peak - c.util_at(progress)) for c in done]


@dataclass(frozen=True)
class Blend:
    actual_pct: float
    progress: float
    projected_pct: float            # medyan (kapidan bagimsiz ham deger)
    lower_pct: float
    upper_pct: float
    confidence_score: float
    recent_pct: float | None
    hist_pct: float | None
    fallback_pct: float
    recent_n: int
    cycles_completed: int
    target_remaining_pct: float
    run_out_in_s: float | None


def blend(current: Cycle, done: Sequence[Cycle], now: datetime) -> Blend | None:
    last = current.obs[-1]
    if last.resets_at <= now:
        return None
    duration = last.duration_s
    progress = min(max((now - last.start).total_seconds() / duration, 0.0), 1.0)
    actual = last.util * 100
    future = max(0.0, 1.0 - progress)

    slope, n_recent, spread = recent_slope(current)
    recent = actual + slope * 100 * future if (slope is not None and slope > 0) else None
    adds = historical_additions(done, progress)
    hist = actual + statistics.median(adds) * 100 if adds else None
    fallback = (actual / progress) if progress > 0.015 else actual

    cands: list[tuple[float, float]] = []
    if recent is not None:
        cands.append((recent, W_RECENT * min(1.0, n_recent / 6)))
    if hist is not None:
        cands.append((hist, W_HIST * min(1.0, len(adds) / 5)))
    cands.append((fallback, W_FALLBACK))
    wsum = sum(w for _, w in cands)
    projected = max(actual, sum(v * w for v, w in cands) / wsum)

    # guven
    elapsed = max(1.0, (now - last.start).total_seconds())
    obs_span = (current.obs[-1].at - current.obs[0].at).total_seconds()
    obs_cov = 0.65 * min(1.0, len(current.obs) / 10) + 0.35 * min(1.0, obs_span / elapsed)
    hist_cov = min(1.0, len(done) / 5)
    natural = 300.0 if duration <= 6 * 3600 else 3600.0
    freshness = _clamp(1 - (now - last.at).total_seconds() / max(60.0, natural * 3), 0.0, 1.0)
    conf = _clamp(obs_cov * 0.38 + hist_cov * 0.30 + freshness * 0.20, 0.0, 1.0)  # aktivite haritasi yok: 0.12 bos

    target = _clamp(5 + (1 - conf) * 8, 5, 13)
    hist_spread = _mad([c.peak * 100 for c in done]) * 1.4826
    uncertainty = _clamp(max(4.0, 18 * (1 - conf)) + min(12.0, hist_spread * 0.35 + spread * future * 0.5), 4.0, 28.0)
    lower, upper = max(actual, projected - uncertainty), projected + uncertainty
    run_out = None
    if actual >= 100:
        run_out = 0.0  # zaten tukenmis: tukenme ani = simdi
    elif slope is not None and slope > 0:
        run_out = ((100 - actual) / (slope * 100)) * duration  # ilerleme -> saniye
    return Blend(actual_pct=actual, progress=progress, projected_pct=projected, lower_pct=lower, upper_pct=upper,
                 confidence_score=conf, recent_pct=recent, hist_pct=hist, fallback_pct=fallback, recent_n=n_recent,
                 cycles_completed=len(done), target_remaining_pct=target, run_out_in_s=run_out)


def verdict_for(b: Blend) -> str:
    if b.projected_pct >= 100:
        return "at_risk"
    if b.upper_pct >= 100:
        return "watch"
    median_surplus = 100 - b.projected_pct - b.target_remaining_pct
    conservative = 100 - b.upper_pct - b.target_remaining_pct
    if median_surplus >= 25 and conservative >= 10:
        return "surplus"
    return "enough"


def confidence_label(score: float) -> str:
    return "high" if score >= 0.72 else "medium" if score >= 0.35 else "learning"


def forecast(history: Iterable[QuotaSnapshot], kind: WindowKind, now: datetime, *, model_display: str | None = None,
             estimate_id: str | None = None) -> QuotaForecast | None:
    obs = observations(history, kind, model_display)
    done, current = cycles(obs, now)
    if current is None:
        return None
    b = blend(current, done, now)
    if b is None:
        return None
    inputs = hashlib.sha256(f"{kind}|{model_display}|{len(obs)}|{obs[-1].at.isoformat()}|{now.isoformat()}".encode()).hexdigest()
    label = confidence_label(b.confidence_score)
    learning = b.cycles_completed < LEARNING_MIN_CYCLES or label == "learning"
    diag = {"recent_pct": b.recent_pct, "hist_pct": b.hist_pct, "fallback_pct": b.fallback_pct, "recent_n": b.recent_n,
            "cycles_completed": b.cycles_completed, "progress": round(b.progress, 4), "actual_pct": b.actual_pct,
            "projected_raw_pct": round(b.projected_pct, 2), "lower_pct": round(b.lower_pct, 2), "upper_pct": round(b.upper_pct, 2)}
    common = dict(estimate_id=estimate_id or f"forecast:{kind}:{now.isoformat()}", estimator=FORECAST_ESTIMATOR,
                  target=f"quota.{kind}.projected_at_reset", produced_at=now, inputs_hash=inputs, diagnostics=diag,
                  window_kind=kind, current_utilization=b.actual_pct / 100, confidence=label,
                  confidence_score=b.confidence_score, target_remaining_pct=b.target_remaining_pct,
                  cycles_completed=b.cycles_completed)
    if learning:
        return QuotaForecast(**common, value=Figure.withheld("percent", EvidenceClass.PREDICTED,
                                                            f"ogreniyor ({b.cycles_completed}/{LEARNING_MIN_CYCLES} dongu, guven {label})"),
                             projected_at_reset=None, verdict="learning", run_out_at=None)
    band = Band(lo=Decimal(str(round(b.lower_pct, 2))), hi=Decimal(str(round(min(b.upper_pct, 200.0), 2))))
    value = Figure.estimated(Decimal(str(round(b.projected_pct, 2))), "percent", FORECAST_ESTIMATOR,
                             evidence_class=EvidenceClass.PREDICTED, band=band, confidence=b.confidence_score)
    return QuotaForecast(**common, value=value,
                         projected_at_reset=ProjectedAtReset(median=Decimal(str(round(b.projected_pct, 2))), band=band),
                         verdict=verdict_for(b),
                         run_out_at=(now + timedelta(seconds=b.run_out_in_s)) if b.run_out_in_s is not None else None)


# ------------------------------------------------------------------ backtest
METHODS = ("last_value", "linear", "recent", "historical", "blend")


def _method_value(name: str, b: Blend) -> float | None:
    if name == "last_value":
        return b.actual_pct
    if name == "linear":
        return b.fallback_pct
    if name == "recent":
        return b.recent_pct
    if name == "historical":
        return b.hist_pct
    return b.projected_pct


def backtest(history: Iterable[QuotaSnapshot], kind: WindowKind, now: datetime, *, model_display: str | None = None,
             min_progress: float = 0.1) -> dict:
    """Tamamlanmis her dongude, her gozlem aninda (ilerleme >= min_progress) 'reset'teki kullanim' tahmini vs gercek.
    Yalniz o ana kadarki veri kullanilir (gelecek sizmaz)."""
    obs = observations(history, kind, model_display)
    done, _ = cycles(obs, now)
    errors: dict[str, list[float]] = {m: [] for m in METHODS}
    covered = 0
    total = 0
    for idx, cyc in enumerate(done):
        prior = done[:idx]
        actual_final = cyc.peak * 100
        for i in range(1, len(cyc.obs)):
            t = cyc.obs[i].at
            partial = Cycle(resets_at=cyc.resets_at, obs=cyc.obs[: i + 1])
            if partial.obs[-1].progress < min_progress:
                continue
            b = blend(partial, prior, t)
            if b is None:
                continue
            total += 1
            for m in METHODS:
                v = _method_value(m, b)
                if v is not None:
                    errors[m].append(abs(min(v, 100.0) - actual_final))
            if b.lower_pct - 1e-9 <= actual_final <= b.upper_pct + 1e-9:
                covered += 1
    report = {m: {"n": len(e), "mae": round(sum(e) / len(e), 2) if e else None} for m, e in errors.items()}
    best = min((m for m in METHODS if report[m]["mae"] is not None), key=lambda m: report[m]["mae"], default=None)
    return {"kind": kind, "cycles": len(done), "evaluations": total, "methods": report, "best": best,
            "blend_band_coverage": round(covered / total, 3) if total else None, "estimator": FORECAST_ESTIMATOR.model_dump()}
