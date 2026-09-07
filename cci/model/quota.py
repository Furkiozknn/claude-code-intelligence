"""QuotaSnapshot: hesap seviyesi kota gozlemi (docs/DATA_MODEL.md §3).

Pencereler SUREYE gore siniflandirilir (codexU); eslesme sayisi != 1 veya
siniflanamayan pencere varsa snapshot `authoritative=False`.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Iterable, Literal

from pydantic import field_validator

from .base import CciModel, F
from .evidence import EvidenceClass
from .figure import Figure
from .ids import AccountRef
from .usage import validate_ts

WindowKind = Literal["session_5h", "weekly_all", "weekly_scoped", "monthly", "unclassified"]
SnapshotSource = Literal["usage_api", "statusline", "rate_limit_headers", "provider_ipc"]
Severity = Literal["normal", "warning", "critical"]

SESSION_5H_S = 5 * 3600
WEEKLY_S = 7 * 86400
MONTH_MIN_S = 28 * 86400
MONTH_MAX_S = 31 * 86400


def classify_duration(duration_s: int | None, *, scoped: bool = False) -> WindowKind:
    if duration_s is None:
        return "unclassified"
    if duration_s == SESSION_5H_S:
        return "session_5h"
    if duration_s == WEEKLY_S:
        return "weekly_scoped" if scoped else "weekly_all"
    if MONTH_MIN_S <= duration_s <= MONTH_MAX_S:
        return "monthly"
    return "unclassified"


class WindowScope(CciModel):
    model_display: str | None = F("internal", default=None)
    group: str | None = F("internal", default=None)


class QuotaWindow(CciModel):
    kind: WindowKind = F("public")
    duration_s: int | None = F("public", default=None, ge=1)
    utilization: float | None = F("internal", default=None, ge=0.0, le=1.0)
    resets_at: datetime | None = F("internal", default=None)
    scope: WindowScope = F("internal", default_factory=WindowScope)
    severity: Severity | None = F("public", default=None)
    is_active: bool | None = F("public", default=None)

    @field_validator("resets_at")
    @classmethod
    def _resets(cls, v: datetime | None) -> datetime | None:
        return None if v is None else validate_ts(v)


def normalize_windows(windows: Iterable[QuotaWindow]) -> tuple[tuple[QuotaWindow, ...], bool]:
    """Sure biliniyorsa tur sureden gelir (isim degil). Yetkili (authoritative)
    = siniflanamayan yok ve her (tur, kapsam) en fazla bir kez."""
    out: list[QuotaWindow] = []
    counts: Counter[tuple[str, str | None]] = Counter()
    authoritative = True
    for w in windows:
        scoped = w.scope.model_display is not None
        kind: WindowKind = w.kind
        if w.duration_s is not None:
            kind = classify_duration(w.duration_s, scoped=scoped)
        elif w.kind == "weekly_all" and scoped:
            kind = "weekly_scoped"
        if kind == "unclassified":
            authoritative = False
        counts[(kind, w.scope.model_display if kind == "weekly_scoped" else None)] += 1
        out.append(w if kind == w.kind else w.model_copy(update={"kind": kind}))
    if any(c > 1 for c in counts.values()):
        authoritative = False
    return tuple(out), authoritative


class Spend(CciModel):
    used: Figure = F("internal")
    limit: Figure = F("internal")


class QuotaSnapshot(CciModel):
    snapshot_id: str = F("internal", min_length=1)
    provider: str = F("internal", min_length=1)
    # None -> depo REDDEDER (hesap kimligi olmadan hesap seviyesi veri saklanmaz);
    # yalniz canli gosterim icin gecici nesne olabilir.
    account: AccountRef | None = F("sensitive", default=None)
    fetched_at: datetime = F("internal")
    source: SnapshotSource = F("public")
    authoritative: bool = F("public")
    windows: tuple[QuotaWindow, ...] = F("internal")
    spend: Spend | None = F("internal", default=None)
    retry_after_s: int | None = F("public", default=None, ge=0)
    raw_hash: str = F("internal", min_length=16)
    evidence_class: EvidenceClass = F("public", default=EvidenceClass.OBSERVED)

    _validate_fetched = field_validator("fetched_at")(validate_ts)

    @classmethod
    def build(cls, *, windows: Iterable[QuotaWindow], **kwargs) -> "QuotaSnapshot":
        norm, ok = normalize_windows(windows)
        return cls(windows=norm, authoritative=ok, **kwargs)

    @property
    def storable(self) -> bool:
        return self.account is not None

    def window(self, kind: WindowKind, model_display: str | None = None) -> QuotaWindow | None:
        for w in self.windows:
            if w.kind == kind and (kind != "weekly_scoped" or w.scope.model_display == model_display):
                return w
        return None
