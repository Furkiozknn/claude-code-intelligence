"""Kota birimi estimator'i (docs/RESEARCH_MODE.md §3; kaynak claude-meter estimator v0, genisletilmis).

Girdi: ayni pencere icin kota snapshot'lari (utilization) + hesap genelinde UsageRecord'lar.
1. Aralik: ardisik snapshot'larda utilization degismediyse birikir; degistiginde kapanir:
   d_util ve aralikta (t0, t1] gerceklesen kullanim vektoru.
2. Aday sayaclar: raw, no_cache_read, io_only, weighted (tur agirliklari), price_equivalent (fiyat tablosu).
3. implied_cap = usage / d_util ; araliklar arasinda degisim katsayisi (CV) en dusuk aday "en tutarli".
4. Yayin: aday basina p10/p50/p90; < 3 aralik -> yalniz min/median/max ve learning.
Cekirdege yalniz {candidate, cap_band, n_intervals, version} gecer.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Sequence

from cci.model.quota import QuotaSnapshot, WindowKind
from cci.model.usage import Tokens, UsageRecord
from cci.pricing.table import PricingTable

ESTIMATOR_VERSION = "unit_v1"
MIN_INTERVALS = 3
WEIGHTS = {"input": 1.0, "output": 5.0, "cache_read": 0.1, "cache_write": 1.25}

Meter = Callable[[UsageRecord, PricingTable | None], float]


def _raw(r: UsageRecord, _t: PricingTable | None) -> float:
    return float(r.tokens.input_total + r.tokens.output)


def _no_cache_read(r: UsageRecord, _t: PricingTable | None) -> float:
    return float(r.tokens.input + r.tokens.cache_write_total + r.tokens.output)


def _io_only(r: UsageRecord, _t: PricingTable | None) -> float:
    return float(r.tokens.input + r.tokens.output)


def _weighted(r: UsageRecord, _t: PricingTable | None) -> float:
    t = r.tokens
    return t.input * WEIGHTS["input"] + t.output * WEIGHTS["output"] + t.cache_read * WEIGHTS["cache_read"] + t.cache_write_total * WEIGHTS["cache_write"]


def _price_equivalent(r: UsageRecord, table: PricingTable | None) -> float:
    if table is None:
        return 0.0
    f = table.cost(r.tokens, r.model.id)
    return float(f.value) / 1e9 if f.released and f.value is not None else 0.0  # USD


CANDIDATES: dict[str, Meter] = {"raw": _raw, "no_cache_read": _no_cache_read, "io_only": _io_only,
                                "weighted": _weighted, "price_equivalent": _price_equivalent}


@dataclass(frozen=True)
class Interval:
    start: datetime
    end: datetime
    d_util: float
    usage: dict[str, float]      # aday -> aralikta kullanim
    records: int


def intervals_from(snapshots: Sequence[QuotaSnapshot], records: Sequence[UsageRecord], kind: WindowKind,
                   table: PricingTable | None = None, model_display: str | None = None) -> list[Interval]:
    obs: list[tuple[datetime, float, datetime | None]] = []
    for s in sorted(snapshots, key=lambda s: s.fetched_at):
        w = s.window(kind, model_display)
        if w is not None and w.utilization is not None:
            obs.append((s.fetched_at, w.utilization, w.resets_at))
    recs = sorted((r for r in records if not r.flags.synthetic), key=lambda r: r.ts)
    out: list[Interval] = []
    if len(obs) < 2:
        return out
    anchor_t, anchor_u, anchor_reset = obs[0]
    for t, u, reset in obs[1:]:
        if reset != anchor_reset and anchor_reset is not None and reset is not None:
            anchor_t, anchor_u, anchor_reset = t, u, reset  # pencere sifirlandi: yeni cipa
            continue
        if u == anchor_u:
            continue
        if u < anchor_u:
            anchor_t, anchor_u = t, u  # dusus (reset/duzeltme): cipayi tasi, aralik uretme
            continue
        span = [r for r in recs if anchor_t < r.ts <= t]
        usage = {name: sum(m(r, table) for r in span) for name, m in CANDIDATES.items()}
        out.append(Interval(start=anchor_t, end=t, d_util=u - anchor_u, usage=usage, records=len(span)))
        anchor_t, anchor_u = t, u
    return out


def _band(values: Sequence[float]) -> dict[str, float | None]:
    if not values:
        return {"min": None, "median": None, "max": None, "p10": None, "p50": None, "p90": None}
    vals = sorted(values)
    q = lambda p: vals[int(round(p * (len(vals) - 1)))]
    return {"min": vals[0], "median": statistics.median(vals), "max": vals[-1],
            "p10": q(0.1) if len(vals) >= MIN_INTERVALS else None, "p50": q(0.5) if len(vals) >= MIN_INTERVALS else None,
            "p90": q(0.9) if len(vals) >= MIN_INTERVALS else None}


def estimate_unit(snapshots: Sequence[QuotaSnapshot], records: Sequence[UsageRecord], kind: WindowKind = "session_5h",
                  table: PricingTable | None = None, model_display: str | None = None) -> dict:
    ivs = [iv for iv in intervals_from(snapshots, records, kind, table, model_display) if iv.d_util > 0 and iv.records > 0]
    result: dict = {"version": ESTIMATOR_VERSION, "kind": kind, "n_intervals": len(ivs),
                    "learning": len(ivs) < MIN_INTERVALS, "candidates": {}, "most_consistent": None,
                    "note": "implied_cap = aralik kullanimi / d_util; nokta tahmin yok, yalniz bant"}
    best: tuple[float, str] | None = None
    for name in CANDIDATES:
        caps = [iv.usage[name] / iv.d_util for iv in ivs if iv.usage[name] > 0]
        band = _band(caps)
        cv = (statistics.pstdev(caps) / statistics.mean(caps)) if len(caps) >= 2 and statistics.mean(caps) > 0 else None
        result["candidates"][name] = {"n": len(caps), "implied_cap": band, "cv": None if cv is None else round(cv, 4)}
        if cv is not None and len(caps) >= MIN_INTERVALS and (best is None or cv < best[0]):
            best = (cv, name)
    if best is not None:
        result["most_consistent"] = best[1]
        band = result["candidates"][best[1]]["implied_cap"]
        result["core_params"] = {"version": ESTIMATOR_VERSION, "candidate": best[1], "kind": kind,
                                 "cap_band": {"p10": band["p10"], "p50": band["p50"], "p90": band["p90"]},
                                 "n_intervals": len(ivs)}
    return result
