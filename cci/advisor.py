"""Stage 14 - "Su anda ne yapmaliyim?" merdiveni (docs/ANALYTICS.md §5). Saf, deterministik, kanitli.

Etki ('expected') olculmedikce withheld: rakam uydurulmaz.
ponytail: realized-vs-estimated (act report) yok; oneri uygulandiktan >=3 gun sonra
ozetlerle karsilastirma eklenince `realized` doldurulur.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Sequence

from cci.analytics.anomaly import Anomaly
from cci.analytics.diagnostics import SessionDiagnostics
from cci.events.envelope import new_ulid
from cci.model.alert import Action, Evidence, Recommendation
from cci.model.estimate import QuotaForecast
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure
from cci.model.quota import QuotaSnapshot
from cci.quota.pace import compute_pace

UNMEASURED = lambda: Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "etki henuz olculmedi")


def _rec(kind: str, title: str, why: Sequence[Evidence], action: Action, now: datetime) -> Recommendation:
    return Recommendation(rec_id=new_ulid(), kind=kind, title=title, why=tuple(why), action=action,
                          expected=UNMEASURED(), issued_at=now)


def advise(*, now: datetime, quota: QuotaSnapshot | None, forecasts: dict[str, QuotaForecast],
           diagnostics: Sequence[SessionDiagnostics], anomalies: Sequence[Anomaly], telemetry_enabled: bool) -> list[Recommendation]:
    out: list[Recommendation] = []
    hint = lambda s: Action(type="session_hint", reversible=True, summary=s)
    if quota is not None:
        w = quota.window("session_5h")
        pace = compute_pace(w, now, allow_post_reset_grace=True) if w else None
        f = forecasts.get("session_5h")
        at_risk = (f is not None and f.verdict == "at_risk") or (pace is not None and pace.eta_s is not None)
        if at_risk and pace is not None:
            ev = [Evidence(metric="pace_delta_pct", value=Decimal(str(round(pace.delta_pct, 1))), evidence_class="derived")]
            if f is not None and f.projected_at_reset is not None:
                ev.append(Evidence(metric="projected_at_reset_pct", value=f.projected_at_reset.median, evidence_class="predicted"))
            if pace.remaining_s < 3600:
                out.append(_rec("wait_for_reset", f"5 saatlik pencere {int(pace.remaining_s // 60)} dk sonra sifirlanacak: buyuk isi reset sonrasina birak",
                                ev, Action(type="wait", reversible=True, summary="reset'i bekle / isi bol"), now))
            else:
                out.append(_rec("reduce_spend", "Kota bu hizla reset'ten once tukenir: daha ucuz model / dusuk effort / kucuk adimlar",
                                ev, hint("ucuz modele gec, effort dusur"), now))
    for d in diagnostics:
        if d.loops or d.attention in ("failures", "critical"):
            out.append(_rec("stop_loop", f"Oturum {d.session_id[:8]}: dongu/hata ({d.attention}) — durdur, baglami degistir, adimi kucult",
                            [Evidence(metric="health", value=Decimal(d.health), evidence_class="derived")] +
                            [Evidence(metric="loop_count", value=Decimal(lp.count), evidence_class="observed") for lp in d.loops[:1]],
                            hint("oturumu durdur"), now))
        if d.context is not None and d.context.risk == "critical":
            out.append(_rec("compact_context", f"Oturum {d.session_id[:8]}: context %{d.context.used_pct:.0f} — ozetle ya da yeni oturum ac",
                            [Evidence(metric="context_used_pct", value=Decimal(str(round(d.context.used_pct, 1))), evidence_class="observed")],
                            hint("ozetle / yeni oturum"), now))
    for a in anomalies:
        if a.kind in ("retry.storm", "rate_limit.burst"):
            out.append(_rec("back_off", f"{a.message}: bekle, paralel oturumlari azalt", a.evidence, hint("geri cekil"), now))
    if not telemetry_enabled:
        out.append(_rec("enable_otlp", "OTLP kapali: `cci setup otlp --write` ile gercek zamanli olaylar + hesap kimligi (kota snapshot saklama) gelir",
                        [Evidence(metric="telemetry_enabled", value=Decimal(0), evidence_class="observed")],
                        Action(type="settings_change", reversible=True, plan_hash="setup-otlp", summary="settings.json env blogu (yedekli, act ile geri alinir)"), now))
    if not out:
        out.append(_rec("ok", "Yolunda: kota, oturumlar ve toplayicilar normal", [Evidence(metric="attention", value=Decimal(0), evidence_class="derived")],
                        Action(type="none", reversible=True, summary="bir sey yapma"), now))
    return out
