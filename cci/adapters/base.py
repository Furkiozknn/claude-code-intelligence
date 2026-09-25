"""Saglayici adaptoru sozlesmesi (docs/PROVIDERS.md §2).

discover / probe_roots / capabilities / collect / normalize / health.
- `collect` SALT OKUNUR ve ham veriyi yalniz bellekte tasir (RawBatch kalici degil).
- `normalize` saf fonksiyondur (I/O yok): test edilebilir, replay edilebilir.
- Hicbir adaptor kimlik dosyasina/kaynak dosyaya yazmaz, token yenilemez.
"""

from __future__ import annotations

import abc
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping

from pydantic import model_validator

from cci.model.base import CciModel, F
from cci.model.ids import SourceInstance
from cci.model.usage import validate_ts

AccountScope = Literal["account", "local"]
HealthStatus = Literal["ok", "degraded", "down"]


class Capabilities(CciModel):
    """Bir saglayicinin gercekten NE verebildigi -- ne vaat ettigi degil.

    Her alan bir yetenegin varligini soyluyor, kalitesini degil. Ucuncu taraf
    bir adaptor yazan kisi burayi durust doldurmak zorunda: `tokens=True` deyip
    token vermeyen bir adaptor, boru hattinin asagisindaki her sayiyi sessizce
    bozar, cunku eksik veri ile sifir veri ayni sekilde gorunur.

    `schema_verified` ve `verified_at` birlikte anlamli: bir sema yalnizca
    BAKILDIGI GUN dogrulanmistir, ve saglayici semasini degistirdiginde o tarih
    iddianin ne kadar eskidigini soyler. Dogrulanmis demek ebediyen dogru
    demek degil.
    """
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
    """Adaptorun su anda calisip calismadigi, ve calismiyorsa neden.

    `detail` bilerek `internal` ve bilerek kisa: redakte edilmis bir aciklama
    tasir, asla token, kimlik bilgisi ya da transcript icerigi tasimaz. Bir
    saglik alaninin sizinti yoluna donusmesi, tam da kimsenin bakmadigi yerde
    olur.

    `status` uc degerli, iki degil: `degraded`, "calisiyor ama eksik veriyle"
    demek ve onu `ok` saymak, boru hattinin asagisinda eksik veriyi tam veri
    gibi gostermek olurdu.
    """
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
    """Bir dosyanin neresine kadar okundugu -- artimli taramanin butun hafizasi.

    Ucu birden gerekli. `bytes_consumed` tek basina yetmez: dosya kirpilip
    yeniden yazildiysa ayni ofset artik baska bir satirin ortasidir, ve
    `size` ile `mtime_ns` bunu yakalar. Dogrulayici `bytes_consumed > size`
    durumunu reddeder, cunku o noktada imlec artik bir konum degil bir tahmin
    olur.
    """
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
    """Bir toplama turunun ham ciktisi. Kalici degildir ve olmamalidir.

    `collect` bunu yalnizca bellekte tasir; sozlesme geregi hicbir adaptor ham
    veriyi diske yazmaz. Kalici olan tek sey `next_cursor`: bir sonraki turun
    nereden devam edecegi.

    `complete=False`, "bu tur her seyi getirmedi" demek ve `skipped`, bozuk ya
    da ayristirilamayan satirlarin sayisi. Ikisi de sessizce yutulmaz, cunku
    eksik bir tur ile bos bir tur ayni sayiyi uretir ve ayni sey degildir.
    """
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


ENTRY_POINT_GROUP = "cci.adapters"
"""Kurulmus bir paketin adaptorunu duyurdugu giris noktasi grubu.

`EXTENDING.md` ucuncu taraflara `cci-adapter-<x>` yazmayi teklif ediyor. Teklif
ancak bu grup varsa gercek: onsuz yazilan adaptoru cagiracak bir sey yok.
Paket su satiri koyar:

    [project.entry-points."cci.adapters"]
    my_tool = "cci_adapter_my_tool:build"

`build`, PROVIDERS.md §2 arayuzunu karsilayan bir adaptor dondurur. Kesfedildigi
anda sozlesme denetlenir; gecmezse yuklenmez ve nedeni `cci providers` ciktisinda
yazar -- bir eklenti kendini devre disi birakir, cekirdegi degil (EXTENDING §3).
"""


class LoadFailure(CciModel):
    """Yuklenemeyen bir adaptor ve nedeni.

    Sessizce atlamak, adaptorunu yeni yazmis birine "hicbir sey olmadi"
    demektir. Basarisizlik da kesfin bir sonucudur ve `cci providers` onu
    ayni tabloda gosterir.
    """
    name: str
    source: str
    error_class: str
    error: str


class Registry:
    """Kayitli adaptorler. Kayit aninda sozlesme dogrulanir.

    `register` once `assert_contract` cagirir: eksik bir yontemle gelen bir
    adaptor kayit olamaz, calisma aninda degil kayit aninda dusuruur. Ayni ad
    iki kez kayit olamaz -- sessizce ustune yazmak, hangi adaptorun kostugunu
    belirsizlestirirdi.
    """
    def __init__(self) -> None:
        self._adapters: dict[str, ProviderAdapter] = {}
        self._failures: list[LoadFailure] = []

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

    def failures(self) -> tuple["LoadFailure", ...]:
        return tuple(self._failures)

    def instances(self) -> Iterable[tuple[ProviderAdapter, SourceInstance]]:
        for adapter in self._adapters.values():
            for inst in adapter.discover():
                yield adapter, inst

    def load_installed(self, env: Mapping[str, str], home: Path,
                       *, group: str = ENTRY_POINT_GROUP) -> tuple[ProviderAdapter, ...]:
        """Kurulu paketlerin duyurdugu adaptorleri yukle.

        Her giris noktasi `(env, home)` alan bir fabrika cagirir. Bir eklentinin
        yuklenmesi neyi bozarsa bozsun -- import hatasi, sozlesme ihlali, ad
        cakismasi -- yalniz o eklenti dusuyor: hata `failures()` icinde
        sayiliyor ve digerleri yuklenmeye devam ediyor.
        """
        from importlib.metadata import entry_points

        yuklenen: list[ProviderAdapter] = []
        for ep in sorted(entry_points(group=group), key=lambda e: e.name):
            try:
                adapter = ep.load()(env=dict(env), home=home)
                self.register(adapter)
            except Exception as exc:            # noqa: BLE001 - eklenti cekirdegi dusurmez
                self._failures.append(LoadFailure(
                    name=ep.name, source=ep.value,
                    error_class=type(exc).__name__, error=str(exc)[:300]))
                continue
            yuklenen.append(adapter)
        return tuple(yuklenen)


def builtin_registry(env: Mapping[str, str], home: Path,
                     *, installed: bool = True) -> Registry:
    """Bu kurulumda gercekten ulasilabilen her adaptor.

    Once iki birinci taraf adaptor, sonra kurulu paketlerin duyurdugu her sey.
    Cagri yerleri somut sinifi adiyla ice aktarmak yerine buradan gecer, boylece
    disaridan gelen bir adaptor de ayni yoldan kosuyor -- yoksa `EXTENDING.md`
    bir sozden ibaret kalir.
    """
    from cci.adapters.claude_code.adapter import ClaudeCodeAdapter
    from cci.adapters.codex import CodexAdapter

    reg = Registry()
    reg.register(ClaudeCodeAdapter(env=env, home=home))
    reg.register(CodexAdapter(env=env, home=home))
    if installed:
        reg.load_installed(env, home)
    return reg


registry = Registry()
