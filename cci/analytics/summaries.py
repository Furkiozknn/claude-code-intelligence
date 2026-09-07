"""Ozetler (docs/DATA_MODEL.md §4-5, ANALYTICS.md §1, §6).

- `price_records`: her kayda fiyat tablosundan `cost.usd` (Figure) yazar.
- `summarize_daily`: yerel gune gore (tz kaydiyla) saglayici/kaynak/model/proje kovalari.
- `summarize_sessions`: oturum basina temel ozet (teshis Stage 8).
- Koruma yasasi: toplam = Σ kova; tutmazsa `ConservationError` (`--strict`) veya
  `conservation.ok=False`. Tum turetimler saf: (kayitlar, tz) -> ozet.
- `SUMMARY_VERSION`: mantik degisince artar; cache'te uyusmazsa yeniden hesap.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, tzinfo
from decimal import Decimal
from typing import Iterable, Sequence

from cci.model.base import CciModel, F
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure, sum_figures
from cci.model.usage import Cost, Tokens, UsageRecord
from cci.pricing.table import PricingTable

SUMMARY_VERSION = 1


class ConservationError(AssertionError):
    pass


def sum_tokens(items: Iterable[Tokens]) -> Tokens:
    inp = out = cr = cwt = 0
    c5 = c1 = 0
    split_known = True
    reasoning = 0
    reasoning_known = False
    for t in items:
        inp += t.input; out += t.output; cr += t.cache_read; cwt += t.cache_write_total
        if t.cache_write_5m is None or t.cache_write_1h is None:
            split_known = False
        else:
            c5 += t.cache_write_5m; c1 += t.cache_write_1h
        if t.reasoning is not None:
            reasoning += t.reasoning; reasoning_known = True
    return Tokens(input=inp, output=out, cache_read=cr, cache_write_total=cwt,
                  cache_write_5m=c5 if split_known else None, cache_write_1h=c1 if split_known else None,
                  reasoning=reasoning if reasoning_known else None)


def price_records(records: Iterable[UsageRecord], table: PricingTable) -> list[UsageRecord]:
    out: list[UsageRecord] = []
    for r in records:
        if r.flags.synthetic:
            usd = Figure.observed(0, "nanoUSD")  # sentetik hata kaydi: maliyet yok (gozlem)
        else:
            usd = table.cost(r.tokens, r.model.id)
        out.append(r.model_copy(update={"cost": Cost(usd=usd, vendor_usd=r.cost.vendor_usd,
                                                     pricing_effective_at=table.fetched_at)}))
    return out


def _vendor_sum(records: Sequence[UsageRecord]) -> Figure:
    parts = [r.cost.vendor_usd for r in records if r.cost.vendor_usd is not None]
    if not parts:
        return Figure.withheld("nanoUSD", EvidenceClass.VENDOR_ESTIMATED, "satici maliyeti yok")
    total = sum_figures(parts)
    if len(parts) != len(records):
        return Figure.withheld("nanoUSD", EvidenceClass.VENDOR_ESTIMATED,
                               f"satici maliyeti {len(records) - len(parts)} kayitta eksik", value=total.value)
    return total


class Totals(CciModel):
    requests: int = F("public", ge=0)
    tokens: Tokens = F("internal")
    cost: Figure = F("internal")
    vendor_cost: Figure = F("internal")
    synthetic: int = F("public", default=0, ge=0)
    advisor: int = F("public", default=0, ge=0)


def _totals(records: Sequence[UsageRecord]) -> Totals:
    real = [r for r in records if not r.flags.synthetic]
    return Totals(requests=len(real), tokens=sum_tokens(r.tokens for r in real),
                  # gercek istek yoksa maliyet gozlenmis sifir (withheld degil): koruma yasasi toplami dogal calisir
                  cost=sum_figures([r.cost.usd for r in real], unit="nanoUSD") if real else Figure.observed(0, "nanoUSD"),
                  vendor_cost=_vendor_sum(real) if real else Figure.withheld("nanoUSD", EvidenceClass.VENDOR_ESTIMATED, "kayit yok"),
                  synthetic=sum(1 for r in records if r.flags.synthetic),
                  advisor=sum(1 for r in records if r.flags.advisor))


class ModelBucket(CciModel):
    model_id: str = F("internal", min_length=1)
    display: str = F("internal", min_length=1)
    totals: Totals = F("internal")


class ProjectBucket(CciModel):
    project_key: str = F("sensitive", min_length=1)
    totals: Totals = F("internal")


class Conservation(CciModel):
    ok: bool = F("public")
    total_tokens: int = F("internal", ge=0)
    model_tokens: int = F("internal", ge=0)
    project_tokens: int = F("internal", ge=0)
    detail: str = F("public", default="")


class DailySummary(CciModel):
    day: date = F("internal")
    tz: str = F("public", min_length=1)
    provider: str = F("internal", min_length=1)
    instance_id: str = F("internal", min_length=1)
    totals: Totals = F("internal")
    models: tuple[ModelBucket, ...] = F("internal")
    projects: tuple[ProjectBucket, ...] = F("internal")
    conservation: Conservation = F("public")
    summary_version: int = F("public", ge=1)
    pricing_version: str | None = F("public", default=None)


class SessionSummary(CciModel):
    session_id: str = F("internal", min_length=1)
    provider: str = F("internal", min_length=1)
    project_key: str | None = F("sensitive", default=None)
    started_at: datetime = F("internal")
    last_at: datetime = F("internal")
    totals: Totals = F("internal")
    models: tuple[ModelBucket, ...] = F("internal")
    subagent_requests: int = F("public", ge=0)
    sidechain_requests: int = F("public", ge=0)
    conservation: Conservation = F("public")
    summary_version: int = F("public", ge=1)


def _model_buckets(records: Sequence[UsageRecord]) -> tuple[ModelBucket, ...]:
    groups: dict[str, list[UsageRecord]] = defaultdict(list)
    for r in records:
        groups[r.model.id].append(r)
    return tuple(ModelBucket(model_id=k, display=v[0].model.display, totals=_totals(v))
                 for k, v in sorted(groups.items()))


def _project_buckets(records: Sequence[UsageRecord]) -> tuple[ProjectBucket, ...]:
    groups: dict[str, list[UsageRecord]] = defaultdict(list)
    for r in records:
        groups[r.workspace.project_key if r.workspace else "unknown"].append(r)
    return tuple(ProjectBucket(project_key=k, totals=_totals(v)) for k, v in sorted(groups.items()))


def check_conservation(totals: Totals, models: Sequence[ModelBucket], projects: Sequence[ProjectBucket],
                       *, strict: bool = False) -> Conservation:
    t = totals.tokens.billable_total
    m = sum(b.totals.tokens.billable_total for b in models)
    p = sum(b.totals.tokens.billable_total for b in projects)
    cost_ok = True
    if totals.cost.released:
        model_cost = sum((b.totals.cost.value for b in models if b.totals.cost.released), Decimal(0))
        cost_ok = model_cost == totals.cost.value
    ok = (t == m == p) and totals.requests == sum(b.totals.requests for b in models) and cost_ok
    detail = "" if ok else f"toplam={t} model={m} proje={p} cost_ok={cost_ok}"
    if strict and not ok:
        raise ConservationError(detail)
    return Conservation(ok=ok, total_tokens=t, model_tokens=m, project_tokens=p, detail=detail)


def summarize_daily(records: Iterable[UsageRecord], tz: tzinfo, *, pricing_version: str | None = None,
                    strict: bool = False) -> list[DailySummary]:
    groups: dict[tuple[date, str, str], list[UsageRecord]] = defaultdict(list)
    for r in records:
        groups[(r.ts.astimezone(tz).date(), r.provider, r.source.instance_id)].append(r)
    out: list[DailySummary] = []
    tzname = getattr(tz, "key", None) or str(tz)
    for (day, provider, instance_id), recs in sorted(groups.items()):
        totals = _totals(recs)
        models = _model_buckets(recs)
        projects = _project_buckets(recs)
        out.append(DailySummary(day=day, tz=tzname, provider=provider, instance_id=instance_id, totals=totals,
                                models=models, projects=projects,
                                conservation=check_conservation(totals, models, projects, strict=strict),
                                summary_version=SUMMARY_VERSION, pricing_version=pricing_version))
    return out


def summarize_sessions(records: Iterable[UsageRecord], *, strict: bool = False) -> list[SessionSummary]:
    groups: dict[tuple[str, str], list[UsageRecord]] = defaultdict(list)
    for r in records:
        groups[(r.provider, r.session.session_id)].append(r)
    out: list[SessionSummary] = []
    for (provider, sid), recs in sorted(groups.items()):
        recs.sort(key=lambda r: r.ts)
        totals = _totals(recs)
        models = _model_buckets(recs)
        projects = _project_buckets(recs)
        keys = {r.workspace.project_key for r in recs if r.workspace}
        out.append(SessionSummary(
            session_id=sid, provider=provider, project_key=next(iter(keys)) if len(keys) == 1 else None,
            started_at=recs[0].ts, last_at=recs[-1].ts, totals=totals, models=models,
            subagent_requests=sum(1 for r in recs if r.session.agent_id or r.attribution.query_source == "subagent"),
            sidechain_requests=sum(1 for r in recs if r.session.is_sidechain),
            conservation=check_conservation(totals, models, projects, strict=strict),
            summary_version=SUMMARY_VERSION))
    return out
