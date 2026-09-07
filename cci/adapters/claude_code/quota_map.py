"""`GET https://api.anthropic.com/api/oauth/usage` yaniti -> QuotaSnapshot.

Belgesiz uc (notes/02 §D). Bilinen sekil:
  five_hour / seven_day: {utilization, resets_at}
  seven_day_opus / seven_day_sonnet (eski), limits[]: {kind: session|weekly_all|weekly_scoped,
  group, percent, severity, resets_at, scope{model{display_name}}, is_active}
  spend, extra_usage, ve kod adi gurultusu (nimbus_quill, tangelo, ...).

VARSAYIM (sema kanaryasi): `utilization` ve `percent` 0-100 olcegindedir
(statusline `used_percentage` ile ayni). 100'u asan deger bozuk sayilir.
Tur -> sure: session=18000 s, weekly_*=604800 s; bilinmeyen tur `unclassified`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Mapping

from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure, usd_to_nano
from cci.model.ids import AccountRef
from cci.model.quota import (SESSION_5H_S, WEEKLY_S, QuotaSnapshot, QuotaWindow, Spend,
                             WindowScope)

KIND_DURATION: dict[str, int] = {
    "session": SESSION_5H_S, "five_hour": SESSION_5H_S,
    "weekly_all": WEEKLY_S, "weekly_scoped": WEEKLY_S, "seven_day": WEEKLY_S,
}
KNOWN_TOP_KEYS = frozenset({"five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet",
                            "limits", "spend", "extra_usage"})


class QuotaParseError(ValueError):
    pass


def _ratio(v: Any) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise QuotaParseError("utilization sayi degil")
    if v < 0 or v > 100:
        raise QuotaParseError("utilization 0-100 disi")
    return float(v) / 100.0


def _ts(v: Any) -> datetime | None:
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return datetime.fromtimestamp(float(v), UTC)
    if isinstance(v, str):
        try:
            dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        except ValueError as exc:
            raise QuotaParseError("resets_at ISO degil") from exc
        return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
    raise QuotaParseError("resets_at turu")


def _window(kind: str, row: Mapping[str, Any], *, scoped_model: str | None = None) -> QuotaWindow:
    util_key = "percent" if "percent" in row else "utilization"
    severity = row.get("severity")
    if severity not in (None, "normal", "warning", "critical"):
        severity = None
    return QuotaWindow(
        kind="unclassified", duration_s=KIND_DURATION.get(kind),
        utilization=_ratio(row.get(util_key)), resets_at=_ts(row.get("resets_at")),
        scope=WindowScope(model_display=scoped_model, group=row.get("group") if isinstance(row.get("group"), str) else None),
        severity=severity, is_active=row.get("is_active") if isinstance(row.get("is_active"), bool) else None,
    )


def parse_usage_response(body: Mapping[str, Any], *, provider: str = "anthropic",
                         account: AccountRef | None, fetched_at: datetime,
                         source: str = "usage_api", raw_bytes: bytes | None = None,
                         retry_after_s: int | None = None) -> tuple[QuotaSnapshot, list[str]]:
    """(snapshot, bilinmeyen ust seviye anahtarlar). `limits[]` varsa tek dogru kaynak;
    yoksa five_hour/seven_day(+_opus/_sonnet) alanlari."""
    if not isinstance(body, Mapping):
        raise QuotaParseError("govde nesne degil")
    windows: list[QuotaWindow] = []
    limits = body.get("limits")
    if isinstance(limits, list) and limits:
        for item in limits:
            if not isinstance(item, Mapping):
                continue
            kind = item.get("kind") if isinstance(item.get("kind"), str) else "unknown"
            scope = item.get("scope") if isinstance(item.get("scope"), Mapping) else {}
            model = scope.get("model") if isinstance(scope.get("model"), Mapping) else {}
            display = model.get("display_name") if isinstance(model.get("display_name"), str) else None
            windows.append(_window(kind, item, scoped_model=display if kind == "weekly_scoped" else None))
    else:
        for key, kind in (("five_hour", "session"), ("seven_day", "weekly_all")):
            row = body.get(key)
            if isinstance(row, Mapping):
                windows.append(_window(kind, row))
        for key, label in (("seven_day_opus", "Opus"), ("seven_day_sonnet", "Sonnet")):
            row = body.get(key)
            if isinstance(row, Mapping):
                windows.append(_window("weekly_scoped", row, scoped_model=label))

    spend = None
    sp = body.get("spend")
    if isinstance(sp, Mapping) and isinstance(sp.get("used"), (int, float)) and isinstance(sp.get("limit"), (int, float)):
        spend = Spend(used=Figure.observed(usd_to_nano(sp["used"]), "nanoUSD"),
                      limit=Figure.observed(usd_to_nano(sp["limit"]), "nanoUSD"))

    unknown = sorted(k for k in body.keys() if k not in KNOWN_TOP_KEYS)
    raw = raw_bytes if raw_bytes is not None else repr(sorted(body.items())).encode("utf-8")
    snap = QuotaSnapshot.build(
        snapshot_id=f"{provider}:{fetched_at.isoformat()}",
        provider=provider, account=account, fetched_at=fetched_at, source=source,
        raw_hash=hashlib.sha256(raw).hexdigest(), windows=windows, spend=spend,
        retry_after_s=retry_after_s, evidence_class=EvidenceClass.OBSERVED,
    )
    return snap, unknown
