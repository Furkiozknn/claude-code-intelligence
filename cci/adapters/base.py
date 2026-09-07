"""Saglayici adaptoru sozlesmesi (docs/PROVIDERS.md §2).

discover / probe_roots / capabilities / collect / normalize / health.
- `collect` SALT OKUNUR ve ham veriyi yalniz bellekte tasir (RawBatch kalici degil).
- `normalize` saf fonksiyondur (I/O yok): test edilebilir, replay edilebilir.
- Hicbir adaptor kimlik dosyasina/kaynak dosyaya yazmaz, token yenilemez.
"""

from __future__ import annotations

import abc
from datetime import date, datetime
from typing import Any, Iterable, Literal

from pydantic import model_validator

from cci.model.base import CciModel, F
from cci.model.ids import SourceInstance
from cci.model.usage import validate_ts

AccountScope = Literal["account", "local"]
HealthStatus = Literal["ok", "degraded", "down"]


class Capabilities(CciModel):
    tokens: bool = F("public", default=False)
    cost_vendor: bool = F("public", default=False)
    quota: bool = F("public", default=False)
    sessions: bool = F("public", default=False)
    tools: bool = F("public", default=False)
    attribution: bool = F("public", default=False)
    realtime: bool = F("public", default=False)
    history_days: int | None = F("public", default=None, ge=0)
    account_scope: AccountScope = F("public", default="local")
    schema_verified: bool = F("public", default=False)
    verified_at: date | None = F("public", default=None)
    retroactive_reconciliation: bool = F("public", default=False)

    @model_validator(mode="after")
    def _verified_needs_date(self) -> "Capabilities":
        if self.schema_verified and self.verified_at is None:
            raise ValueError("schema_verified=True icin verified_at zorunlu (tarihli dogrulama)")
        return self


class ProbeRoot(CciModel):
    """`cci doctor` icin: adaptor nereye bakti, orada bir sey var mi."""

    path: str = F("sensitive", min_length=1)
    label: str = F("internal", min_length=1)
    exists: bool = F("public")


class Health(CciModel):
    status: HealthStatus = F("public")
    last_success_at: datetime | None = F("internal", default=None)
    lag_s: float | None = F("internal", default=None, ge=0)
    error_class: str | None = F("public", default=None)
    retry_after_s: int | None = F("public", default=None, ge=0)
    detail: str = F("internal", default="")  # redakte edilmis kisa aciklama; asla token/icerik

    @model_validator(mode="after")
    def _ts(self) -> "Health":
        if self.last_success_at is not None:
            validate_ts(self.last_success_at)
        return self


class FileCursor(CciModel):
    size: int = F("internal", ge=0)
    mtime_ns: int = F("internal", ge=0)
    bytes_consumed: int = F("internal", ge=0)

    @model_validator(mode="after")
    def _consumed(self) -> "FileCursor":
        if self.bytes_consumed > self.size:
            raise ValueError("bytes_consumed > size")
        return self


class Cursor(CciModel):
    """Artimli toplama imleci (VibeBill manifest kalibi). Bozuksa adaptor
    sessizce tam yeniden baslar."""

    files: dict[str, FileCursor] = F("sensitive", default_factory=dict)
    since: datetime | None = F("internal", default=None)
    etag: str | None = F("internal", default=None)

    @model_validator(mode="after")
    def _ts(self) -> "Cursor":
        if self.since is not None:
            validate_ts(self.since)
        return self


class RawItem(CciModel):
    """Ham kayit - YALNIZ bellekte. `payload` normalize'a girer, hicbir yere
    yazilmaz; `ref` (dosya:satir gibi) hata ayiklama icindir."""

    kind: str = F("internal", min_length=1)
    ref: str = F("sensitive", min_length=1)
    payload: dict[str, Any] = F("internal", default_factory=dict)


class RawBatch(CciModel):
    instance: SourceInstance = F("internal")
    items: tuple[RawItem, ...] = F("internal", default=())
    complete: bool = F("public", default=True)
    next_cursor: Cursor = F("internal", default_factory=Cursor)
    skipped: int = F("public", default=0, ge=0)  # atlanan bozuk satir/dosya sayaci


class ProviderAdapter(abc.ABC):
    """Her saglayici bu sozlesmeyi uygular; `assert_contract` ile dogrulanir."""

    name: str = ""       # ornek: "claude_code"
    provider: str = ""   # ornek: "anthropic"

    @abc.abstractmethod
    def discover(self) -> tuple[SourceInstance, ...]: ...

    @abc.abstractmethod
    def probe_roots(self) -> tuple[ProbeRoot, ...]: ...

    @abc.abstractmethod
    def capabilities(self) -> Capabilities: ...

    @abc.abstractmethod
    def collect(self, instance: SourceInstance, cursor: Cursor) -> RawBatch: ...

    @abc.abstractmethod
    def normalize(self, batch: RawBatch) -> tuple[Any, ...]:
        """RawBatch -> Envelope/UsageRecord demeti. Saf; I/O yok."""

    @abc.abstractmethod
    def health(self) -> Health: ...

    def describe(self) -> dict[str, Any]:
        caps = self.capabilities()
        return {"name": self.name, "provider": self.provider,
                "capabilities": caps.model_dump(mode="json"),
                "instances": [i.model_dump(mode="json") for i in self.discover()]}


def assert_contract(adapter: ProviderAdapter) -> None:
    """Sozlesme denetimi: tipler, zorunlu alanlar, `schema_verified` tutarliligi."""
    if not adapter.name or not adapter.provider:
        raise AssertionError("adaptor name/provider bos")
    caps = adapter.capabilities()
    if not isinstance(caps, Capabilities):
        raise AssertionError("capabilities() Capabilities dondurmeli")
    instances = adapter.discover()
    if not isinstance(instances, tuple) or not all(isinstance(i, SourceInstance) for i in instances):
        raise AssertionError("discover() tuple[SourceInstance] dondurmeli")
    ids = [i.instance_id for i in instances]
    if len(ids) != len(set(ids)):
        raise AssertionError("instance_id tekrarli")
    for inst in instances:
        if inst.provider != adapter.provider:
            raise AssertionError("SourceInstance.provider adaptorle uyusmuyor")
        if inst.schema_verified != caps.schema_verified:
            raise AssertionError("SourceInstance.schema_verified capabilities ile uyusmali")
    roots = adapter.probe_roots()
    if not isinstance(roots, tuple) or not all(isinstance(r, ProbeRoot) for r in roots):
        raise AssertionError("probe_roots() tuple[ProbeRoot] dondurmeli")
    health = adapter.health()
    if not isinstance(health, Health):
        raise AssertionError("health() Health dondurmeli")


class Registry:
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}

    def register(self, adapter: ProviderAdapter) -> ProviderAdapter:
        assert_contract(adapter)
        if adapter.name in self._adapters:
            raise ValueError(f"adaptor zaten kayitli: {adapter.name}")
        self._adapters[adapter.name] = adapter
        return adapter

    def get(self, name: str) -> ProviderAdapter:
        return self._adapters[name]

    def all(self) -> tuple[ProviderAdapter, ...]:
        return tuple(self._adapters.values())

    def names(self) -> tuple[str, ...]:
        return tuple(self._adapters)

    def instances(self) -> Iterable[tuple[ProviderAdapter, SourceInstance]]:
        for adapter in self._adapters.values():
            for inst in adapter.discover():
                yield adapter, inst


registry = Registry()
