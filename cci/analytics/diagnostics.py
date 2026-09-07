"""Stage 8 - oturum teshisi (docs/ANALYTICS.md §1.1; kaynak agenttrace diagnostics + inspect_reason).

Girdi: oturumun olaylari (`tool.call`, `usage.error`, `session.compacted`, `usage.request`,
opsiyonel `statusline.tick`) + (varsa) fiyatlanmis maliyet. Cikti deterministik:
- arac gecikmeleri (avg/p95/max, timeout, is_slow)
- dongu parmak izi: ardisik ayni (arac, girdi boyutu, hata turu) >= 3
- retry/hata orani, compaction sayisi, context riski (statusline varsa)
- saglik skoru 0-100 ve DIKKAT MERDIVENI (critical > failures > context > loops > cost > latency > warning > ok)
Hicbir icerik okunmaz; yalniz sayilar ve arac adlari.
"""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Iterable, Literal

from cci.events.envelope import Envelope
from cci.model.base import CciModel, F
from cci.model.evidence import EvidenceClass
from cci.model.figure import EstimatorRef, Figure

DIAG_ESTIMATOR = EstimatorRef(id="diagnostics_v1", version="1.0")
SLOW_TOOL_P95_MS = 30_000
LATENCY_ATTENTION_P95_MS = 60_000
LOOP_MIN_RUN = 3
COST_ATTENTION_NANO = 1_000_000_000  # $1
CONTEXT_WARN_PCT = 70.0
CONTEXT_CRITICAL_PCT = 85.0

Attention = Literal["critical", "failures", "context", "loops", "cost", "latency", "warning", "ok"]
Risk = Literal["ok", "warn", "critical"]


class ToolLatency(CciModel):
    tool_name: str = F("internal", min_length=1)
    calls: int = F("public", ge=0)
    failures: int = F("public", ge=0)
    timeouts: int = F("public", ge=0)
    avg_ms: float | None = F("internal", default=None, ge=0)
    p95_ms: float | None = F("internal", default=None, ge=0)
    max_ms: float | None = F("internal", default=None, ge=0)
    is_slow: bool = F("public", default=False)


class LoopFingerprint(CciModel):
    tool_name: str = F("internal", min_length=1)
    fingerprint: str = F("internal", min_length=1)   # "<arac>|<girdi boyutu>|<hata turu>" - icerik yok
    count: int = F("public", ge=LOOP_MIN_RUN)
    first_index: int = F("public", ge=0)
    last_index: int = F("public", ge=0)
    severity: Literal["medium", "high"] = F("public")


class ContextUtilization(CciModel):
    used_pct: float = F("internal", ge=0, le=100)
    risk: Risk = F("public")
    source: Literal["statusline"] = F("public", default="statusline")


class SessionDiagnostics(CciModel):
    session_id: str = F("internal", min_length=1)
    requests: int = F("public", ge=0)
    errors: int = F("public", ge=0)
    retry_events: int = F("public", ge=0)
    error_rate: float = F("internal", ge=0, le=1)
    tool_calls: int = F("public", ge=0)
    tool_failures: int = F("public", ge=0)
    tool_timeouts: int = F("public", ge=0)
    tools: tuple[ToolLatency, ...] = F("internal", default=())
    loops: tuple[LoopFingerprint, ...] = F("internal", default=())
    compactions: int = F("public", ge=0)
    context: ContextUtilization | None = F("internal", default=None)
    cost: Figure | None = F("internal", default=None)
    health: int = F("public", ge=0, le=100)
    attention: Attention = F("public")
    reasons: tuple[str, ...] = F("public", default=())
    evidence_class: EvidenceClass = F("public", default=EvidenceClass.DERIVED)
    estimator: EstimatorRef = F("internal", default=DIAG_ESTIMATOR)


def _p95(values: list[float]) -> float:
    vals = sorted(values)
    return vals[int(round(0.95 * (len(vals) - 1)))]


def _tool_latencies(calls: list[dict]) -> tuple[ToolLatency, ...]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for c in calls:
        groups[str(c.get("tool_name") or "unknown")].append(c)
    out: list[ToolLatency] = []
    for name, items in sorted(groups.items()):
        durations = [float(c["duration_ms"]) for c in items if isinstance(c.get("duration_ms"), (int, float))]
        failures = sum(1 for c in items if c.get("success") is False)
        timeouts = sum(1 for c in items if str(c.get("error_type") or "").lower() in ("timeout", "timed_out"))
        p95 = _p95(durations) if durations else None
        out.append(ToolLatency(tool_name=name, calls=len(items), failures=failures, timeouts=timeouts,
                               avg_ms=(sum(durations) / len(durations)) if durations else None, p95_ms=p95,
                               max_ms=max(durations) if durations else None,
                               is_slow=bool(p95 is not None and p95 >= SLOW_TOOL_P95_MS)))
    return tuple(out)


def _loops(calls: list[dict]) -> tuple[LoopFingerprint, ...]:
    out: list[LoopFingerprint] = []
    run_start = 0
    prev: str | None = None
    fps: list[str] = []
    for c in calls:
        # icerik yok: arac adi + girdi/cikti boyutu + hata turu (agenttrace'in tool+result hash'inin icerik-siz esdegeri)
        fps.append(f"{c.get('tool_name') or 'unknown'}|{c.get('input_size_bytes') or 0}"
                   f"|{c.get('result_size_bytes') or 0}|{c.get('error_type') or ''}")
    for i, fp in enumerate(fps + [None]):  # type: ignore[list-item]
        if fp == prev:
            continue
        run_len = i - run_start
        if prev is not None and run_len >= LOOP_MIN_RUN:
            tool, _, _, err = prev.split("|", 3)
            out.append(LoopFingerprint(tool_name=tool, fingerprint=prev, count=run_len, first_index=run_start,
                                       last_index=i - 1, severity="high" if err else "medium"))
        run_start = i
        prev = fp
    return tuple(out)


def health_score(*, error_rate: float, loops: int, timeout_rate: float, context_risk: Risk | None,
                 compactions: int) -> int:
    risk = {"ok": 0.0, "warn": 0.5, "critical": 1.0}.get(context_risk or "ok", 0.0)
    penalty = error_rate * 30 + min(1.0, loops / 2) * 25 + timeout_rate * 20 + risk * 15 + min(1.0, compactions / 2) * 10
    return int(max(0, min(100, round(100 - penalty))))


def attention_for(*, health: int, tool_failures: int, context_risk: Risk | None, loops: int,
                  cost: Figure | None, max_p95_ms: float | None) -> tuple[Attention, tuple[str, ...]]:
    reasons: list[str] = []
    if health < 50:
        reasons.append(f"saglik {health} < 50")
    if tool_failures > 0:
        reasons.append(f"{tool_failures} arac hatasi")
    if context_risk in ("warn", "critical"):
        reasons.append(f"context riski {context_risk}")
    if loops > 0:
        reasons.append(f"{loops} dongu parmak izi")
    if cost is not None and cost.released and cost.value is not None and cost.value >= COST_ATTENTION_NANO:
        reasons.append(f"maliyet {cost.render()} >= $1")
    if max_p95_ms is not None and max_p95_ms >= LATENCY_ATTENTION_P95_MS:
        reasons.append(f"arac p95 {max_p95_ms / 1000:.0f} sn")
    if health < 80:
        reasons.append(f"saglik {health} < 80")
    if health < 50:
        return "critical", tuple(reasons)
    if tool_failures > 0:
        return "failures", tuple(reasons)
    if context_risk in ("warn", "critical"):
        return "context", tuple(reasons)
    if loops > 0:
        return "loops", tuple(reasons)
    if cost is not None and cost.released and cost.value is not None and cost.value >= COST_ATTENTION_NANO:
        return "cost", tuple(reasons)
    if max_p95_ms is not None and max_p95_ms >= LATENCY_ATTENTION_P95_MS:
        return "latency", tuple(reasons)
    if health < 80:
        return "warning", tuple(reasons)
    return "ok", ()


ATTENTION_RANK: dict[str, int] = {a: i for i, a in enumerate(("critical", "failures", "context", "loops", "cost", "latency", "warning", "ok"))}


def worst_attention(items: Iterable[str]) -> str:
    best = "ok"
    for a in items:
        if ATTENTION_RANK.get(a, 99) < ATTENTION_RANK[best]:
            best = a
    return best


def diagnose_session(session_id: str, events: Iterable[Envelope], *, cost: Figure | None = None) -> SessionDiagnostics:
    calls: list[dict] = []
    requests = errors = retry_events = compactions = 0
    context: ContextUtilization | None = None
    for env in sorted(events, key=lambda e: (e.ts, e.event_id)):
        if env.session_id is not None and env.session_id != session_id:
            continue
        p = env.payload
        if env.type == "tool.call":
            calls.append(p)
        elif env.type == "usage.request":
            requests += 1
        elif env.type == "usage.error":
            errors += 1
            if isinstance(p.get("attempt"), (int, float)) and p["attempt"] > 1:
                retry_events += 1
        elif env.type == "session.compacted":
            compactions += 1
        elif env.type == "statusline.tick":
            cw = p.get("context_window")
            used = cw.get("used_percentage") if isinstance(cw, dict) else None
            if isinstance(used, (int, float)):
                pct = float(min(max(used, 0), 100))
                context = ContextUtilization(used_pct=pct, risk="critical" if pct >= CONTEXT_CRITICAL_PCT else
                                             "warn" if pct >= CONTEXT_WARN_PCT else "ok")
    tools = _tool_latencies(calls)
    loops = _loops(calls)
    tool_failures = sum(t.failures for t in tools)
    tool_timeouts = sum(t.timeouts for t in tools)
    error_rate = errors / (requests + errors) if (requests + errors) else 0.0
    timeout_rate = tool_timeouts / len(calls) if calls else 0.0
    health = health_score(error_rate=error_rate, loops=len(loops), timeout_rate=timeout_rate,
                          context_risk=context.risk if context else None, compactions=compactions)
    p95s = [t.p95_ms for t in tools if t.p95_ms is not None]
    attention, reasons = attention_for(health=health, tool_failures=tool_failures,
                                       context_risk=context.risk if context else None, loops=len(loops), cost=cost,
                                       max_p95_ms=max(p95s) if p95s else None)
    return SessionDiagnostics(session_id=session_id, requests=requests, errors=errors, retry_events=retry_events,
                              error_rate=error_rate, tool_calls=len(calls), tool_failures=tool_failures,
                              tool_timeouts=tool_timeouts, tools=tools, loops=loops, compactions=compactions,
                              context=context, cost=cost, health=health, attention=attention, reasons=reasons)
