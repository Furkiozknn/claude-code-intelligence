"""Olay zarfi (docs/EVENTS.md §1) ve tur katalogu (§2).

Zarf icerik tasimaz; `payload` allow-list'ten gecmis anahtarlarla sinirlidir
(cci.ingest). `payload_hash` idempotent yazim icindir: ayni hash ikinci kez
gelirse yazilmaz.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import computed_field, field_validator, model_validator

from cci.model.base import CciModel, F
from cci.model.evidence import EvidenceClass
from cci.model.usage import validate_ts

PrivacyTag = Literal["public", "internal", "sensitive"]

# docs/EVENTS.md §2 - olay katalogu. Bilinmeyen tur zarf duzeyinde hata degildir;
# ingest kapisi `dropped_unknown_type` sayar (sema evrimi icin).
EVENT_TYPES: frozenset[str] = frozenset({
    "usage.request", "usage.error", "usage.refusal", "usage.metric_delta",
    "quota.snapshot", "quota.reset_observed",
    "session.started", "session.ended", "session.compacted", "session.active_time",
    "prompt.submitted", "prompt.responded",
    "tool.call", "tool.decision", "permission.mode_changed", "mcp.connection",
    "code.lines", "code.commit", "code.pr",
    "statusline.tick",
    "provider.health", "provider.schema_change", "collector.health",
    "estimate.published", "alert.raised", "alert.resolved",
    "recommendation.issued", "recommendation.applied", "recommendation.reverted",
    "recommendation.evaluated",
})

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def new_ulid(now_ms: int | None = None) -> str:
    """26 karakter ULID (48 bit ms zaman + 80 bit rastgele), zaman sirali."""
    ts = int(time.time() * 1000) if now_ms is None else int(now_ms)
    value = (ts << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def payload_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


class SourceRef(CciModel):
    collector: str = F("internal", min_length=1)
    instance_id: str = F("internal", min_length=1)
    collector_version: str = F("internal", min_length=1)
    schema_version: int = F("public", ge=1)


class Envelope(CciModel):
    event_id: str = F("internal", default_factory=new_ulid, min_length=26, max_length=26)
    type: str = F("public", min_length=1)
    ts: datetime = F("internal")
    received_at: datetime = F("internal", default_factory=lambda: datetime.now(UTC))
    source: SourceRef = F("internal")
    provider: str | None = F("internal", default=None)
    account_key: str | None = F("sensitive", default=None)
    session_id: str | None = F("internal", default=None)
    privacy_class: PrivacyTag = F("public", default="internal")
    evidence_class: EvidenceClass = F("public", default=EvidenceClass.OBSERVED)
    payload: dict[str, Any] = F("internal", default_factory=dict)

    _validate_ts = field_validator("ts")(validate_ts)
    _validate_received = field_validator("received_at")(validate_ts)

    @model_validator(mode="after")
    def _type_shape(self) -> "Envelope":
        if "." not in self.type or self.type != self.type.lower():
            raise ValueError("olay turu 'alan.olay' bicimli kucuk harf olmali")
        return self

    @computed_field(json_schema_extra={"privacy": "internal"})
    @property
    def payload_hash(self) -> str:
        return payload_hash(self.payload)

    @property
    def known_type(self) -> bool:
        return self.type in EVENT_TYPES

    @property
    def lag_s(self) -> float:
        return max(0.0, (self.received_at - self.ts).total_seconds())
