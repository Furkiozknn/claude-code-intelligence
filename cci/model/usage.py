"""UsageRecord: normalize edilmis tek API cagrisi (docs/DATA_MODEL.md §2)."""

from __future__ import annotations

import hashlib
from datetime import UTC, date, datetime
from typing import Literal

from pydantic import computed_field, field_validator, model_validator

from .base import CciModel, F
from .evidence import EvidenceClass
from .figure import Figure
from .ids import AccountRef, SessionRef, SourceInstance

TS_MIN = datetime(2000, 1, 1, tzinfo=UTC)
TS_MAX = datetime(2100, 1, 1, tzinfo=UTC)

QuerySource = Literal["main", "subagent", "auxiliary"]
Speed = Literal["standard", "fast"]


def validate_ts(v: datetime) -> datetime:
    """tz-aware, UTC'ye cevrilmis, [2000, 2100) icinde (tycho SCHEMA.md)."""
    if v.tzinfo is None:
        raise ValueError("zaman damgasi tz-aware olmali")
    v = v.astimezone(UTC)
    if not (TS_MIN <= v < TS_MAX):
        raise ValueError(f"zaman damgasi sinir disi: {v.isoformat()}")
    return v


class Tokens(CciModel):
    """`input` cache HARIC girdi (Anthropic anlami); `input_total` cache dahil
    (OTel GenAI semconv anlami) - notes/03."""

    input: int = F("internal", ge=0)
    output: int = F("internal", ge=0)
    cache_read: int = F("internal", default=0, ge=0)
    cache_write_5m: int | None = F("internal", default=None, ge=0)
    cache_write_1h: int | None = F("internal", default=None, ge=0)
    cache_write_total: int = F("internal", default=0, ge=0)
    reasoning: int | None = F("internal", default=None, ge=0)

    @model_validator(mode="after")
    def _cache_split(self) -> "Tokens":
        if self.cache_write_5m is not None and self.cache_write_1h is not None:
            if self.cache_write_5m + self.cache_write_1h != self.cache_write_total:
                raise ValueError("cache_write_5m + cache_write_1h != cache_write_total")
        for part in (self.cache_write_5m, self.cache_write_1h):
            if part is not None and part > self.cache_write_total:
                raise ValueError("cache yazma parcasi toplamdan buyuk")
        return self

    @computed_field(json_schema_extra={"privacy": "internal", "evidence": "derived"})
    @property
    def input_total(self) -> int:
        return self.input + self.cache_read + self.cache_write_total

    @computed_field(json_schema_extra={"privacy": "internal", "evidence": "derived"})
    @property
    def billable_total(self) -> int:
        return self.input_total + self.output


class ModelRef(CciModel):
    id: str = F("internal", min_length=1)
    display: str = F("internal", min_length=1)
    family: str | None = F("internal", default=None)
    unknown: bool = F("public", default=False)


class Attribution(CciModel):
    query_source: QuerySource | None = F("internal", default=None)
    agent: str | None = F("internal", default=None)
    skill: str | None = F("internal", default=None)
    plugin: str | None = F("internal", default=None)
    mcp_server: str | None = F("internal", default=None)
    mcp_tool: str | None = F("internal", default=None)
    marketplace: str | None = F("internal", default=None)
    speed: Speed | None = F("internal", default=None)
    effort: str | None = F("internal", default=None)


class Flags(CciModel):
    synthetic: bool = F("public", default=False)
    api_error: bool = F("public", default=False)
    advisor: bool = F("public", default=False)
    iteration_index: int | None = F("public", default=None, ge=0)
    sidechain_replay_dropped: int = F("public", default=0, ge=0)
    stream_partial_suspected: bool = F("public", default=False)


class Workspace(CciModel):
    project_key: str = F("sensitive", min_length=1)
    cwd_hash: str | None = F("sensitive", default=None)
    git_branch: str | None = F("sensitive", default=None)


class Timing(CciModel):
    duration_ms: int | None = F("internal", default=None, ge=0)
    ttft_ms: int | None = F("internal", default=None, ge=0)


class Cost(CciModel):
    usd: Figure = F("internal")
    vendor_usd: Figure | None = F("internal", default=None)
    pricing_effective_at: date | None = F("public", default=None)

    @model_validator(mode="after")
    def _units(self) -> "Cost":
        if self.usd.unit != "nanoUSD":
            raise ValueError("cost.usd birimi nanoUSD olmali")
        if self.vendor_usd is not None:
            if self.vendor_usd.unit != "nanoUSD":
                raise ValueError("cost.vendor_usd birimi nanoUSD olmali")
            if self.vendor_usd.evidence_class != EvidenceClass.VENDOR_ESTIMATED:
                raise ValueError("vendor_usd kanit sinifi vendor_estimated olmali")
        return self


class CollectorRef(CciModel):
    name: str = F("internal", min_length=1)
    version: str = F("internal", min_length=1)
    schema_version: int = F("public", ge=1)


class UsageRecord(CciModel):
    provider: str = F("internal", min_length=1)
    source: SourceInstance = F("internal")
    account: AccountRef | None = F("sensitive", default=None)
    session: SessionRef = F("internal")
    prompt_id: str | None = F("internal", default=None)
    message_id: str | None = F("internal", default=None)
    request_id: str | None = F("internal", default=None)
    uuid: str | None = F("internal", default=None)  # transcript kayit uuid'si (dedup yedegi)
    ts: datetime = F("internal")
    model: ModelRef = F("internal")
    tokens: Tokens = F("internal")
    cost: Cost = F("internal")
    timing: Timing = F("internal", default_factory=Timing)
    attribution: Attribution = F("internal", default_factory=Attribution)
    flags: Flags = F("public", default_factory=Flags)
    workspace: Workspace | None = F("sensitive", default=None)
    evidence_class: EvidenceClass = F("public", default=EvidenceClass.OBSERVED)
    collector: CollectorRef = F("internal")

    _validate_ts = field_validator("ts")(validate_ts)

    @model_validator(mode="after")
    def _ids(self) -> "UsageRecord":
        if self.request_id is None and self.message_id is None and self.uuid is None:
            raise ValueError("request_id, message_id veya uuid gerekli (dedup anahtari icin)")
        if self.flags.synthetic and self.tokens.billable_total != 0:
            raise ValueError("sentetik kayit token tasiyamaz")
        return self

    @computed_field(json_schema_extra={"privacy": "internal"})
    @property
    def dedup_key(self) -> str:
        """Kaynaklar arasi mutabakat anahtari.
        - `request_id` varsa `<provider>:req:<request_id>` (OTel `api_request` ve
          transcript `requestId` ayni API istek kimligidir -> iki kaynak birlesir);
        - yoksa `<provider>:msg:<message_id>:<session_id>` (ccusage: gateway ayni
          message id'yi farkli oturumda yeniden kullanabilir);
        - o da yoksa `<provider>:uuid:<uuid>:<session_id>` (tycho ADR 0002).
        Sidechain replay (ayni message_id, farkli requestId) bu anahtarla YAKALANMAZ;
        normalizer `message_key` ikincil indeksiyle eler."""
        sid = self.session.session_id
        if self.request_id:
            return f"{self.provider}:req:{self.request_id}"
        if self.message_id is not None:
            return f"{self.provider}:msg:{self.message_id}:{sid}"
        return f"{self.provider}:uuid:{self.uuid}:{sid}"

    @property
    def message_key(self) -> str | None:
        """Sidechain replay tespiti icin ikincil anahtar (message_id + oturum)."""
        if self.message_id is None:
            return None
        return f"{self.provider}:msg:{self.message_id}:{self.session.session_id}"

    @computed_field(json_schema_extra={"privacy": "internal"})
    @property
    def record_id(self) -> str:
        return hashlib.sha256(self.dedup_key.encode("utf-8")).hexdigest()[:32]

    def prefer_over(self, other: "UsageRecord") -> bool:
        """Ayni dedup anahtarinda kazanan kurali (ccusage): sidechain olmayan
        kazanir; sonra daha buyuk toplam token; esitlikte `speed` alani olan
        (yeni sema)."""
        if self.session.is_sidechain != other.session.is_sidechain:
            return other.session.is_sidechain
        mine, theirs = self.tokens.billable_total, other.tokens.billable_total
        if mine != theirs:
            return mine > theirs
        return self.attribution.speed is not None and other.attribution.speed is None
