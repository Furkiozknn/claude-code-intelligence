"""Stage 11 - anomali tespiti (docs/ANALYTICS.md §3; kaynak Maciek P90 = TABAN, agenttrace CostAlert oran).

Kisisel taban cizgisi (kullanim kayitlarindan, saf):
- 5 saatlik bloklar (ccusage algoritmasi: saate yuvarlanmis baslangic, >5 sa bosluk yeni blok)
  -> blok basina token; P50/P90 (>= 5 tamamlanmis blok).
- oturum maliyeti P50/P90 (>= 5 oturum, released Figure'lar).
Kurallar (her biri kanit listesiyle):
- volume.ratio: aktif blok tokeni / P50 >= 2 warning, >= 4 critical (n >= 20 kayit)
- cost.spike: oturum maliyeti / oturum P50 >= 2 / >= 4
- retry.storm: 10 dk icinde >= 5 `usage.error`
- rate_limit.burst: 10 dk icinde >= 3 429
- provider.schema_change: son 24 sa icinde olay
Tahmin degil, gozlem + turetim (derived). Esikler konfigurasyondan.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Iterable, Literal, Sequence

from cci.events.envelope import Envelope
from cci.model.alert import Evidence
from cci.model.base import CciModel, F
from cci.model.usage import UsageRecord

BLOCK_S = 5 * 3600
MIN_BLOCKS = 5
MIN_RECORDS = 20
WARN_RATIO, CRIT_RATIO = 2.0, 4.0
RETRY_STORM_N, RETRY_STORM_WINDOW_S = 5, 600
RATE_LIMIT_BURST_N = 3
SCHEMA_CHANGE_WINDOW_S = 86400

Severity = Literal["info", "warning", "critical"]


class Anomaly(CciModel):
    kind: str = F("public", min_length=1)
    severity: Severity = F("public")
    subject_kind: Literal["session", "quota_window", "provider", "collector", "model", "project"] = F("public")
    subject_id: str = F("internal", min_length=1)
    message: str = F("internal", min_length=1)
    evidence: tuple[Evidence, ...] = F("internal", default=())
    evidence_class: Literal["observed", "derived"] = F("public", default="derived")


@dataclass
class Block:
    start: datetime
    end: datetime
    tokens: int = 0
    requests: int = 0
    active: bool = False


def blocks_from_records(records: Sequence[UsageRecord], now: datetime, block_s: int = BLOCK_S) -> list[Block]:
    """ccusage `identify_session_blocks`: sirala, baslangic saate yuvarla, >5 sa bosluk yeni blok."""
    recs = sorted((r for r in records if not r.flags.synthetic), key=lambda r: r.ts)
    out: list[Block] = []
    cur: Block | None = None
    last_ts: datetime | None = None
    for r in recs:
        if cur is None or (r.ts - cur.start).total_seconds() > block_s or (last_ts and (r.ts - last_ts).total_seconds() > block_s):
            start = r.ts.replace(minute=0, second=0, microsecond=0)
            cur = Block(start=start, end=start + timedelta(seconds=block_s))
            out.append(cur)
        cur.tokens += r.tokens.billable_total
        cur.requests += 1
        last_ts = r.ts
    if out and last_ts is not None:
        last = out[-1]
        last.active = (now - last_ts).total_seconds() < block_s and now < last.end
    return out


@dataclass(frozen=True)
class Baseline:
    blocks_completed: int
    block_tokens_p50: float | None
    block_tokens_p90: float | None
    sessions: int
    session_cost_p50_nano: Decimal | None
    session_cost_p90_nano: Decimal | None
    records: int
    notes: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict:
        return {"blocks_completed": self.blocks_completed, "block_tokens_p50": self.block_tokens_p50,
                "block_tokens_p90": self.block_tokens_p90, "sessions": self.sessions,
                "session_cost_p50_nano": None if self.session_cost_p50_nano is None else str(self.session_cost_p50_nano),
                "session_cost_p90_nano": None if self.session_cost_p90_nano is None else str(self.session_cost_p90_nano),
                "records": self.records, "notes": list(self.notes)}


def _p(values: Sequence[float], q: float) -> float:
    vals = sorted(values)
    return vals[int(round(q * (len(vals) - 1)))]


def baseline(records: Sequence[UsageRecord], session_costs: Sequence[Decimal], now: datetime) -> Baseline:
    blocks = [b for b in blocks_from_records(records, now) if not b.active and b.tokens > 0]
    notes: list[str] = []
    p50 = p90 = None
    if len(blocks) >= MIN_BLOCKS:
        toks = [float(b.tokens) for b in blocks]
        p50, p90 = _p(toks, 0.5), _p(toks, 0.9)
    else:
        notes.append(f"blok tabani icin >= {MIN_BLOCKS} tamamlanmis blok gerekli ({len(blocks)})")
    c50 = c90 = None
    costs = [c for c in session_costs if c is not None]
    if len(costs) >= MIN_BLOCKS:
        c50, c90 = Decimal(str(_p([float(c) for c in costs], 0.5))), Decimal(str(_p([float(c) for c in costs], 0.9)))
    else:
        notes.append(f"oturum maliyet tabani icin >= {MIN_BLOCKS} fiyatli oturum gerekli ({len(costs)})")
    return Baseline(blocks_completed=len(blocks), block_tokens_p50=p50, block_tokens_p90=p90, sessions=len(costs),
                    session_cost_p50_nano=c50, session_cost_p90_nano=c90, records=len(records), notes=tuple(notes))


def _ratio_severity(ratio: float) -> Severity | None:
    if ratio >= CRIT_RATIO:
        return "critical"
    if ratio >= WARN_RATIO:
        return "warning"
    return None


def detect(records: Sequence[UsageRecord], events: Iterable[Envelope], now: datetime, *,
           session_costs: dict[str, Decimal] | None = None, warn_ratio: float = WARN_RATIO,
           crit_ratio: float = CRIT_RATIO) -> tuple[list[Anomaly], Baseline]:
    session_costs = session_costs or {}
    base = baseline(records, list(session_costs.values()), now)
    out: list[Anomaly] = []

    # 1) hacim orani (aktif blok vs P50)
    blocks = blocks_from_records(records, now)
    active = blocks[-1] if blocks and blocks[-1].active else None
    if active is not None and base.block_tokens_p50 and base.records >= MIN_RECORDS:
        ratio = active.tokens / base.block_tokens_p50
        sev = "critical" if ratio >= crit_ratio else "warning" if ratio >= warn_ratio else None
        if sev:
            out.append(Anomaly(kind="volume.ratio", severity=sev, subject_kind="quota_window", subject_id="session_5h",
                               message=f"aktif 5 saatlik blok tokeni tabanin {ratio:.1f} kati",
                               evidence=(Evidence(metric="block_tokens", value=Decimal(active.tokens),
                                                  baseline=Decimal(str(round(base.block_tokens_p50))), ratio=Decimal(str(round(ratio, 2))),
                                                  evidence_class="derived"),)))

    # 2) oturum maliyeti sicramasi
    if base.session_cost_p50_nano:
        for sid, cost in session_costs.items():
            if cost is None or base.session_cost_p50_nano == 0:
                continue
            ratio = float(cost / base.session_cost_p50_nano)
            sev = "critical" if ratio >= crit_ratio else "warning" if ratio >= warn_ratio else None
            if sev:
                out.append(Anomaly(kind="cost.spike", severity=sev, subject_kind="session", subject_id=sid,
                                   message=f"oturum maliyeti tipik oturumun {ratio:.1f} kati",
                                   evidence=(Evidence(metric="session_cost_nano", value=cost, baseline=base.session_cost_p50_nano,
                                                      ratio=Decimal(str(round(ratio, 2))), evidence_class="estimated"),)))

    # 3) retry firtinasi / 429 patlamasi / sema degisimi (olaylardan)
    errors: dict[str, list[datetime]] = defaultdict(list)
    rate_limits: dict[str, list[datetime]] = defaultdict(list)
    schema_changes: list[Envelope] = []
    for env in events:
        if env.type == "usage.error":
            sid = env.session_id or "unknown"
            errors[sid].append(env.ts)
            if env.payload.get("status_code") == 429:
                rate_limits[sid].append(env.ts)
        elif env.type == "provider.schema_change" and (now - env.ts).total_seconds() <= SCHEMA_CHANGE_WINDOW_S:
            schema_changes.append(env)
    window = timedelta(seconds=RETRY_STORM_WINDOW_S)
    for sid, ts_list in errors.items():
        recent = [t for t in ts_list if now - t <= window]
        if len(recent) >= RETRY_STORM_N:
            out.append(Anomaly(kind="retry.storm", severity="critical", subject_kind="session", subject_id=sid,
                               message=f"{len(recent)} API hatasi / 10 dk",
                               evidence=(Evidence(metric="errors_10m", value=Decimal(len(recent)), baseline=Decimal(RETRY_STORM_N),
                                                  evidence_class="observed"),), evidence_class="observed"))
    for sid, ts_list in rate_limits.items():
        recent = [t for t in ts_list if now - t <= window]
        if len(recent) >= RATE_LIMIT_BURST_N:
            out.append(Anomaly(kind="rate_limit.burst", severity="warning", subject_kind="provider", subject_id="anthropic",
                               message=f"{len(recent)} adet 429 / 10 dk (oturum {sid[:8]})",
                               evidence=(Evidence(metric="http_429_10m", value=Decimal(len(recent)), baseline=Decimal(RATE_LIMIT_BURST_N),
                                                  evidence_class="observed"),), evidence_class="observed"))
    if schema_changes:
        out.append(Anomaly(kind="provider.schema_change", severity="info", subject_kind="provider", subject_id="anthropic",
                           message=f"son 24 saatte {len(schema_changes)} sema degisikligi olayi",
                           evidence=(Evidence(metric="schema_change_24h", value=Decimal(len(schema_changes)), evidence_class="observed"),),
                           evidence_class="observed"))
    return out, base
