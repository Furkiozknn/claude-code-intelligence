"""Uyari motoru: kural -> Alert; cooldown/dedupe (depodaki `alert.raised` olaylarindan turetilir),
firtina siniri (dakikada <= N), sessiz saatler, kanallar (snapshot listesi, CLI, loopback webhook).

Metin kurali: ne oldu · kanit · ne yapilabilir (tek cumle). Predicted kanita dayanan uyari "probable".
"""

from __future__ import annotations

import json
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from cci.analytics.anomaly import Anomaly
from cci.analytics.diagnostics import SessionDiagnostics
from cci.config import AlertConfig
from cci.events.envelope import Envelope, SourceRef, new_ulid
from cci.model.alert import Alert, Evidence, Subject
from cci.model.estimate import QuotaForecast
from cci.model.evidence import EvidenceClass
from cci.model.quota import QuotaSnapshot
from cci.quota.pace import compute_pace

SEVERITY_RANK = {"info": 0, "warning": 1, "critical": 2}


@dataclass
class AlertInputs:
    quota: QuotaSnapshot | None = None
    forecasts: Mapping[str, QuotaForecast] = field(default_factory=dict)
    diagnostics: Sequence[SessionDiagnostics] = ()
    anomalies: Sequence[Anomaly] = ()
    collector_health: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # ad -> {status, down_since_s?}


def _alert(rule: str, severity: str, subject: Subject, message: str, evidence: Iterable[Evidence], now: datetime,
           basis: str = "certain", cooldown_s: int = 1800) -> Alert:
    return Alert(alert_id=new_ulid(), rule_id=rule, severity=severity, basis=basis, raised_at=now, subject=subject,
                 evidence=tuple(evidence), dedupe_key=f"{rule}|{subject.kind}|{subject.id}",
                 cooldown_until=now + timedelta(seconds=cooldown_s), message=message)


def evaluate_rules(inp: AlertInputs, now: datetime, cfg: AlertConfig) -> list[Alert]:
    """Saf: girdiler -> aday uyarilar (cooldown/firtina uygulanmamis)."""
    out: list[Alert] = []
    cd = cfg.cooldown_s
    if inp.quota is not None:
        for w in inp.quota.windows:
            if w.utilization is None:
                continue
            pct = w.utilization * 100
            subj = Subject(kind="quota_window", id=w.kind + (f":{w.scope.model_display}" if w.scope.model_display else ""))
            sev = "critical" if pct >= cfg.quota_critical_pct else "warning" if pct >= cfg.quota_warning_pct else None
            if sev:
                reset = w.resets_at.strftime("%H:%M") + "Z" if w.resets_at else "?"
                out.append(_alert("quota.threshold", sev, subj, f"{subj.id} %{pct:.0f} kullanildi; reset {reset} — is bol ya da bekle",
                                  [Evidence(metric="utilization_pct", value=Decimal(str(round(pct, 1))), evidence_class="observed")], now, cooldown_s=cd))
            pace = compute_pace(w, now, allow_post_reset_grace=True)
            if pace is not None and pace.stage == "far_ahead" and pace.remaining_s > 3600:
                out.append(_alert("quota.pace", "warning", subj, f"{subj.id} beklenenden %{pace.delta_pct:.0f} onde; bu hizla reset'ten once tukenebilir — yavasla",
                                  [Evidence(metric="pace_delta_pct", value=Decimal(str(round(pace.delta_pct, 1))), evidence_class="derived")], now, cooldown_s=cd))
            f = inp.forecasts.get(w.kind)
            if f is not None and f.verdict == "at_risk" and f.confidence in ("medium", "high"):
                med = float(f.projected_at_reset.median) if f.projected_at_reset else 100.0
                out.append(_alert("quota.forecast", "warning", subj, f"{subj.id} reset'te ~%{med:.0f} (olasi); ucuz modele gec ya da isi ertele",
                                  [Evidence(metric="projected_at_reset_pct", value=Decimal(str(round(med, 1))), evidence_class="predicted")],
                                  now, basis="probable", cooldown_s=cd))
    for d in inp.diagnostics:
        subj = Subject(kind="session", id=d.session_id)
        if d.loops:
            lp = d.loops[0]
            out.append(_alert("session.loop", "warning", subj, f"oturum {d.session_id[:8]}: {lp.tool_name} ×{lp.count} ayni cagri — dongu; durdur ve baglami degistir",
                              [Evidence(metric="loop_count", value=Decimal(lp.count), evidence_class="observed")], now, cooldown_s=cd))
        if d.context is not None and d.context.risk == "critical":
            out.append(_alert("session.context", "warning", subj, f"oturum {d.session_id[:8]}: context %{d.context.used_pct:.0f} — compaction oncesi ozetle / yeni oturum",
                              [Evidence(metric="context_used_pct", value=Decimal(str(round(d.context.used_pct, 1))), evidence_class="observed")], now, cooldown_s=cd))
        if d.cost is not None and d.cost.released and d.cost.value is not None and d.cost.value >= Decimal(cfg.cost_attention_usd) * 1_000_000_000:
            out.append(_alert("session.cost", "info", subj, f"oturum {d.session_id[:8]}: maliyet {d.cost.render()} — bilgi",
                              [Evidence(metric="session_cost_nano", value=d.cost.value, evidence_class=d.cost.evidence_class.value)], now, cooldown_s=cd * 4))
    for a in inp.anomalies:
        subj = Subject(kind=a.subject_kind, id=a.subject_id)
        rule = {"retry.storm": "session.retry_storm", "cost.spike": "cost.spike", "volume.ratio": "volume.ratio",
                "rate_limit.burst": "provider.rate_limit", "provider.schema_change": "provider.schema_change"}.get(a.kind, a.kind)
        out.append(_alert(rule, a.severity, subj, a.message, a.evidence, now, cooldown_s=cd if a.severity != "info" else cd * 8))
    for name, h in inp.collector_health.items():
        if h.get("status") == "down" and float(h.get("down_since_s") or 0) >= 300:
            out.append(_alert("collector.down", "warning", Subject(kind="collector", id=name),
                              f"toplayici {name} {int(float(h.get('down_since_s') or 0) // 60)} dk'dir kapali ({h.get('error_class') or '?'}) — cci doctor",
                              [Evidence(metric="down_since_s", value=Decimal(str(int(float(h.get("down_since_s") or 0)))), evidence_class="observed")], now, cooldown_s=cd))
    return out


def in_quiet_hours(now_local: datetime, quiet: tuple[int, int] | None) -> bool:
    if quiet is None:
        return False
    start, end = quiet
    h = now_local.hour
    return (start <= h < end) if start <= end else (h >= start or h < end)


class AlertEngine:
    """Durumu depodaki olaylardan turetir (replay edilebilir): son `alert.raised` ts'leri cooldown'dur."""

    def __init__(self, cfg: AlertConfig, *, source: SourceRef | None = None) -> None:
        self.cfg = cfg
        self.source = source or SourceRef(collector="alerts", instance_id="engine", collector_version="0.0.1", schema_version=1)
        self.last_raised: dict[str, datetime] = {}        # dedupe_key -> raised_at
        self.active: dict[str, Alert] = {}
        self.suppressed: list[tuple[str, str]] = []       # (dedupe_key, sebep)

    def load_state(self, events: Iterable[Envelope]) -> None:
        """Depodaki alert olaylarindan cooldown ve aktif uyarilari yeniden kur (replay)."""
        for env in sorted(events, key=lambda e: (e.ts, e.event_id)):
            p = env.payload
            key = str(p.get("dedupe_key") or "")
            if not key:
                continue
            if env.type == "alert.raised":
                self.last_raised[key] = env.ts
                try:
                    subj = Subject.model_validate(p.get("subject") or {})
                    self.active[key] = Alert(alert_id=str(p.get("alert_id") or new_ulid()), rule_id=str(p.get("rule_id")),
                                             severity=str(p.get("severity")), basis=str(p.get("basis") or "certain"),
                                             raised_at=env.ts, subject=subj,
                                             evidence=tuple(Evidence.model_validate(e) for e in (p.get("evidence") or [])),
                                             dedupe_key=key, cooldown_until=env.ts + timedelta(seconds=self.cfg.cooldown_s),
                                             message=str(p.get("message") or "-"))
                except Exception:
                    continue
            elif env.type == "alert.resolved":
                self.active.pop(key, None)

    def run(self, inp: AlertInputs, now: datetime, *, now_local: datetime | None = None) -> tuple[list[Alert], list[Envelope]]:
        """(yeni uyarilar, yazilacak olaylar). Cooldown, sessiz saat ve firtina siniri burada."""
        self.suppressed = []
        candidates = evaluate_rules(inp, now, self.cfg)
        raised: list[Alert] = []
        envelopes: list[Envelope] = []
        quiet = in_quiet_hours(now_local or now, self.cfg.quiet_hours)
        candidates.sort(key=lambda a: -SEVERITY_RANK.get(a.severity, 0))
        non_critical = 0  # firtina siniri yalniz critical olmayanlari sayar (critical her zaman gecer)
        for a in candidates:
            last = self.last_raised.get(a.dedupe_key)
            prev = self.active.get(a.dedupe_key)
            escalated = prev is not None and SEVERITY_RANK[a.severity] > SEVERITY_RANK[prev.severity]
            if last is not None and (now - last).total_seconds() < self.cfg.cooldown_s and not escalated:
                self.suppressed.append((a.dedupe_key, "cooldown"))
                continue
            if quiet and a.severity != "critical":
                self.suppressed.append((a.dedupe_key, "quiet_hours"))
                continue
            if a.severity != "critical":
                if non_critical >= self.cfg.storm_limit_per_minute:
                    self.suppressed.append((a.dedupe_key, "storm_limit"))
                    continue
                non_critical += 1
            raised.append(a)
            self.last_raised[a.dedupe_key] = now
            self.active[a.dedupe_key] = a
            envelopes.append(Envelope(type="alert.raised", ts=now, source=self.source, provider=None,
                                      session_id=a.subject.id if a.subject.kind == "session" else None,
                                      privacy_class="internal", evidence_class=EvidenceClass.DERIVED,
                                      payload={"alert_id": a.alert_id, "rule_id": a.rule_id, "severity": a.severity, "basis": a.basis,
                                               "evidence": [e.model_dump(mode="json") for e in a.evidence],
                                               "subject": a.subject.model_dump(mode="json"), "dedupe_key": a.dedupe_key,
                                               "message": a.message}))
        # cozulme: aktif olup bu turda aday olmayanlar
        current_keys = {a.dedupe_key for a in candidates}
        for key in list(self.active):
            if key not in current_keys:
                old = self.active.pop(key)
                envelopes.append(Envelope(type="alert.resolved", ts=now, source=self.source, privacy_class="internal",
                                          evidence_class=EvidenceClass.DERIVED,
                                          payload={"alert_id": old.alert_id, "rule_id": old.rule_id, "resolved_at": now.isoformat(),
                                                   "dedupe_key": key}))
        return raised, envelopes

    def snapshot_alerts(self) -> list[dict[str, Any]]:
        return [{"alert_id": a.alert_id, "rule_id": a.rule_id, "severity": a.severity, "basis": a.basis,
                 "message": a.message, "raised_at": a.raised_at.isoformat(), "subject": a.subject.model_dump(mode="json")}
                for a in sorted(self.active.values(), key=lambda a: -SEVERITY_RANK.get(a.severity, 0))]


def send_webhook(url: str, alerts: Sequence[Alert], *, timeout_s: float = 3.0) -> bool:
    """Yalniz loopback URL; icerik yok (kural, severity, mesaj, kanit)."""
    if not (url.startswith("http://127.0.0.1") or url.startswith("http://localhost")):
        return False
    body = json.dumps([{"rule_id": a.rule_id, "severity": a.severity, "basis": a.basis, "message": a.message,
                        "raised_at": a.raised_at.isoformat(), "subject": a.subject.model_dump(mode="json")} for a in alerts]).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST", headers={"Content-Type": "application/json", "User-Agent": "cci-alerts"})
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:  # noqa: S310 (loopback)
            return 200 <= resp.status < 300
    except Exception:
        return False
