"""Snapshot dosyasi `state/latest.json` (docs/PRODUCT.md §2, ARCHITECTURE §3, PRIVACY §5 R-10).

- Atomik yazim (pid'li temp + replace), 0600.
- Yuzeyler hesap yapmaz: pace, ozet, kota burada hazir gelir.
- `sensitive` alanlar hash'li/kisaltilmis: proje anahtari zaten hash, hesap
  kimligi ilk 8 karakter; ham yol yok.
- `generated_at`, `next_display_change_at` (yuzeyler yalniz gorunen deger
  degisince yeniler), `schema_version`.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Mapping

from cci.analytics.summaries import DailySummary
from cci.model.figure import Figure
from cci.model.quota import QuotaSnapshot
from cci.quota.pace import Pace, compute_pace

SNAPSHOT_SCHEMA_VERSION = 1
DEFAULT_REFRESH_S = 60


def _figure(f: Figure) -> dict[str, Any]:
    return {"text": f.render(), "released": f.released, "evidence": f.evidence_class.value,
            "released_as": f.released_as, "projected": f.projected,
            "value": str(f.value) if (f.released and f.value is not None) else None,
            "withheld_because": f.withheld_because or None}


def _badge(evidence: str) -> str:
    return {"observed": "●", "derived": "◐", "vendor_estimated": "≈", "estimated": "≈",
            "predicted": "~", "inferred": "?"}.get(evidence, "?")


def build_snapshot(*, now: datetime, quota: QuotaSnapshot | None, today: DailySummary | None,
                   health: Mapping[str, Any] | None = None, attention: str = "ok",
                   alerts: list[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    windows: list[dict[str, Any]] = []
    next_change = now + timedelta(seconds=DEFAULT_REFRESH_S)
    account_short: str | None = None
    quota_age_s: float | None = None
    if quota is not None:
        quota_age_s = max(0.0, (now - quota.fetched_at).total_seconds())
        account_short = quota.account.account_key[:8] if quota.account else None
        for w in quota.windows:
            pace: Pace | None = compute_pace(w, now, allow_post_reset_grace=True)
            item: dict[str, Any] = {
                "kind": w.kind, "model": w.scope.model_display, "utilization_pct": None if w.utilization is None else round(w.utilization * 100, 1),
                "badge": _badge("observed"), "resets_at": w.resets_at.isoformat() if w.resets_at else None,
                "severity": w.severity, "authoritative": quota.authoritative, "stale": quota_age_s > 900,
                "pace": None,
            }
            if pace is not None:
                item["pace"] = {"stage": pace.stage, "delta_pct": round(pace.delta_pct, 1), "badge": _badge("derived"),
                                "eta_s": None if pace.eta_s is None else round(pace.eta_s), "eta_badge": _badge("predicted"),
                                "will_last_to_reset": pace.will_last_to_reset, "estimator": pace.estimator.model_dump()}
                if pace.eta_s is not None:
                    next_change = min(next_change, now + timedelta(seconds=max(30, min(pace.eta_s, DEFAULT_REFRESH_S))))
            if w.resets_at is not None and now < w.resets_at:
                next_change = min(next_change, w.resets_at)
            windows.append(item)
    today_block = None
    if today is not None:
        t = today.totals
        today_block = {"day": today.day.isoformat(), "tz": today.tz, "requests": t.requests,
                       "tokens": {"input": t.tokens.input, "output": t.tokens.output, "cache_read": t.tokens.cache_read,
                                  "cache_write": t.tokens.cache_write_total, "input_total": t.tokens.input_total},
                       "cost": _figure(t.cost), "vendor_cost": _figure(t.vendor_cost),
                       "models": [{"model": m.model_id, "display": m.display, "requests": m.totals.requests,
                                   "cost": _figure(m.totals.cost)} for m in today.models],
                       "conservation_ok": today.conservation.ok, "summary_version": today.summary_version,
                       "pricing_version": today.pricing_version}
    return {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": now.isoformat(),
        "next_display_change_at": next_change.isoformat(),
        "account_key_short": account_short,
        "quota": {"source": quota.source if quota else None, "fetched_at": quota.fetched_at.isoformat() if quota else None,
                  "age_s": quota_age_s, "authoritative": quota.authoritative if quota else None, "windows": windows,
                  "placeholder": None if quota else "--"},
        "attention": attention,
        "today": today_block,
        "alerts": list(alerts or []),
        "health": dict(health or {}),
    }


def write_snapshot(path: Path, snapshot: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding="utf-8")
    if os.name != "nt":
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def read_snapshot(path: Path) -> dict[str, Any] | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
