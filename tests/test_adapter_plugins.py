"""Disaridan kurulmus bir adaptor gercekten cagriliyor mu.

`docs/EXTENDING.md` ucuncu taraflara `cci-adapter-<x>` yazmayi teklif ediyor ve
`docs/PROVIDERS.md §2` arayuzu veriyor. Sozlesme testi bunu ispat edemez: onun
gordugu tek adaptorler ayni dosyada, ayni elden yazilmis olanlar. Buradaki
testler adaptoru paket sinirinin DISINA koyuyor -- gecici bir dizine, kendi
`.dist-info` meta verisiyle, `pip install`in urettiginin aynisi -- ve urunun
ona ulasip ulasmadigini soruyor.

Sahte yok: `importlib.metadata.entry_points()` gercekten okunuyor.
"""
from __future__ import annotations

import json
import sys
import textwrap
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from cci.adapters import ENTRY_POINT_GROUP, Registry, builtin_registry
from cci.cli import main

ADAPTER_SRC = '''
from datetime import UTC, date, datetime
from pathlib import Path

from cci.adapters import Capabilities, Cursor, Health, ProbeRoot, ProviderAdapter, RawBatch, RawItem
from cci.model import SourceInstance
from cci.model.evidence import EvidenceClass
from cci.model.figure import Figure
from cci.model.ids import SessionRef
from cci.model.usage import (Attribution, CollectorRef, Cost, Flags, ModelRef, Tokens,
                             UsageRecord)

VERIFIED = date(2026, 9, 22)
COLLECTOR = CollectorRef(name="demo-jsonl", version="0.1.0", schema_version=1)


class DemoAdapter(ProviderAdapter):
    """Uydurma bir aracin JSONL'ini okuyan, depo disindan gelen adaptor."""

    name = "demo"
    provider = "demoprov"

    def __init__(self, env=None, home=None):
        self._home = Path(home) if home else Path.home()

    def root(self):
        return self._home / ".demo"

    def _inst(self):
        return SourceInstance(provider="demoprov", instance_id="demo-1", label="Demo",
                              kind="cli", schema_verified=True, verified_at=VERIFIED)

    def discover(self):
        return (self._inst(),) if self.root().is_dir() else ()

    def probe_roots(self):
        return (ProbeRoot(path=str(self.root()), label="demo", exists=self.root().is_dir()),)

    def capabilities(self):
        return Capabilities(tokens=True, schema_verified=True, verified_at=VERIFIED)

    def collect(self, instance, cursor):
        items = []
        import json as _json
        for path in sorted(self.root().glob("*.jsonl")):
            for i, raw in enumerate(path.read_text(encoding="utf-8").splitlines()):
                if raw.strip():
                    items.append(RawItem(kind="usage", ref=f"{path.name}:{i}",
                                         payload={"i": i, **_json.loads(raw)}))
        return RawBatch(instance=instance, items=tuple(items))

    def normalize(self, batch):
        out = []
        for item in batch.items:
            p = item.payload
            out.append(UsageRecord(
                provider="demoprov", source=batch.instance,
                session=SessionRef(session_id=p["session"]),
                uuid=f"demo:{p['session']}:{p['i']}",
                ts=datetime.fromisoformat(p["ts"]).replace(tzinfo=UTC),
                model=ModelRef(id=p["model"], display=p["model"]),
                tokens=Tokens(input=p["in"], output=p["out"]),
                cost=Cost(usd=Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "demo")),
                attribution=Attribution(), flags=Flags(), collector=COLLECTOR))
        return tuple(out)

    def health(self):
        return Health(status="ok" if self.root().is_dir() else "down",
                      last_success_at=datetime.now(UTC))


def build(env=None, home=None):
    return DemoAdapter(env=env, home=home)
'''


def install(tmp_path: Path, *, module: str, src: str, entry: str, dist: str = "cci-adapter-demo") -> Path:
    """Bir paketi `pip install` gibi diske koy: modul + .dist-info meta verisi.

    Ag yok, derleme yok; `importlib.metadata`nin gercekten okudugu dosyalarin
    ta kendisi yaziliyor.
    """
    site = tmp_path / "site"
    site.mkdir(exist_ok=True)
    (site / f"{module}.py").write_text(textwrap.dedent(src), encoding="utf-8")
    info = site / f"{dist.replace('-', '_')}-0.1.0.dist-info"
    info.mkdir(exist_ok=True)
    (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {dist}\nVersion: 0.1.0\n",
                                   encoding="utf-8")
    (info / "entry_points.txt").write_text(f"[{ENTRY_POINT_GROUP}]\n{entry}\n", encoding="utf-8")
    return site


@pytest.fixture
def on_path(monkeypatch):
    def _add(site: Path):
        monkeypatch.syspath_prepend(str(site))
        import importlib
        importlib.invalidate_caches()
    return _add


def test_an_adapter_installed_outside_the_package_is_loaded(tmp_path, on_path):
    site = install(tmp_path, module="cci_adapter_demo", src=ADAPTER_SRC,
                   entry="demo = cci_adapter_demo:build")
    on_path(site)
    (tmp_path / ".demo").mkdir()

    reg = builtin_registry({}, tmp_path)
    assert "demo" in reg.names(), reg.failures()
    assert reg.get("demo").provider == "demoprov"
    assert reg.failures() == ()


def test_without_the_entry_point_nothing_finds_it(tmp_path, on_path):
    # Negatif kontrol: yukaridaki testin gecmesi giris noktasi sayesinde mi,
    # yoksa modul sys.path'te oldugu icin mi? Meta veri olmadan hicbir sey.
    site = install(tmp_path, module="cci_adapter_demo", src=ADAPTER_SRC,
                   entry="demo = cci_adapter_demo:build")
    (site / "cci_adapter_demo-0.1.0.dist-info").rename(site / "not_a_dist_info")
    on_path(site)
    assert "demo" not in builtin_registry({}, tmp_path).names()


def test_a_broken_plugin_disables_itself_not_the_core(tmp_path, on_path):
    site = install(tmp_path, module="cci_adapter_kirik",
                   src="raise RuntimeError('eklenti import sirasinda patladi')",
                   entry="kirik = cci_adapter_kirik:build", dist="cci-adapter-kirik")
    on_path(site)

    reg = builtin_registry({}, tmp_path)
    # Kume esitligi degil kapsama: bu ortamda mesru bir ucuncu taraf adaptoru
    # kurulu olabilir (CI tam da bunu yapiyor). Iddia "cekirdek ayakta ve
    # kirik olan iceride degil"; "baska hicbir sey yok" bambaska bir iddia.
    assert {"claude_code", "codex"} <= set(reg.names())
    assert "kirik" not in reg.names()
    (fail,) = [f for f in reg.failures() if f.name == "kirik"]
    assert fail.error_class == "RuntimeError" and "patladi" in fail.error


def test_a_plugin_that_breaks_the_contract_is_refused(tmp_path, on_path):
    site = install(tmp_path, module="cci_adapter_sozlesmesiz", src='''
        class Yarim:
            name = "yarim"
            provider = "yarimprov"

        def build(env=None, home=None):
            return Yarim()
        ''', entry="yarim = cci_adapter_sozlesmesiz:build", dist="cci-adapter-yarim")
    on_path(site)

    reg = builtin_registry({}, tmp_path)
    assert "yarim" not in reg.names()
    assert "yarim" in [f.name for f in reg.failures()]


def test_a_name_collision_does_not_silently_replace_a_builtin(tmp_path, on_path):
    # Ustune yazmak, hangi adaptorun kostugunu belirsizlestirirdi.
    site = install(tmp_path, module="cci_adapter_carpisan",
                   src=ADAPTER_SRC.replace('name = "demo"', 'name = "codex"'),
                   entry="codex = cci_adapter_carpisan:build", dist="cci-adapter-carpisan")
    on_path(site)

    reg = builtin_registry({}, tmp_path)
    assert reg.get("codex").__class__.__module__ == "cci.adapters.codex"
    assert "codex" in [f.name for f in reg.failures()]


def test_builtin_registry_can_be_asked_for_first_party_only(tmp_path, on_path):
    site = install(tmp_path, module="cci_adapter_demo", src=ADAPTER_SRC,
                   entry="demo = cci_adapter_demo:build")
    on_path(site)
    (tmp_path / ".demo").mkdir()
    assert "demo" not in builtin_registry({}, tmp_path, installed=False).names()


def test_providers_lists_an_external_adapter_and_its_failures(tmp_path, on_path, capsys):
    site = install(tmp_path, module="cci_adapter_demo", src=ADAPTER_SRC,
                   entry="demo = cci_adapter_demo:build")
    install(tmp_path, module="cci_adapter_kirik", src="raise RuntimeError('yok')",
            entry="kirik = cci_adapter_kirik:build", dist="cci-adapter-kirik")
    on_path(site)
    (tmp_path / ".demo").mkdir()

    rc = main(["--data-dir", str(tmp_path / "veri"), "--json", "providers"],
              env={}, home=tmp_path)
    data = json.loads(capsys.readouterr().out)
    names = {a["name"]: a for a in data["adapters"]}
    assert rc == 0
    assert names["demo"]["builtin"] is False and names["claude_code"]["builtin"] is True
    assert names["demo"]["instances"] == ["demo-1"]
    assert "kirik" in [f["name"] for f in data["failures"]]


def test_providers_strict_exits_three_when_a_plugin_failed(tmp_path, on_path, capsys):
    site = install(tmp_path, module="cci_adapter_kirik", src="raise RuntimeError('yok')",
                   entry="kirik = cci_adapter_kirik:build", dist="cci-adapter-kirik")
    on_path(site)
    assert main(["--data-dir", str(tmp_path / "veri"), "--json", "providers", "--strict"],
                env={}, home=tmp_path) == 3
    capsys.readouterr()


def test_scan_ingests_from_an_externally_installed_adapter(tmp_path, on_path, capsys):
    """Ucundan uca: kurulan adaptorun kaydi gercekten olay deposuna giriyor."""
    site = install(tmp_path, module="cci_adapter_demo", src=ADAPTER_SRC,
                   entry="demo = cci_adapter_demo:build")
    on_path(site)
    demo = tmp_path / ".demo"
    demo.mkdir()
    (demo / "a.jsonl").write_text(json.dumps(
        {"session": "s1", "ts": "2026-09-22T10:00:00", "model": "demo-1", "in": 120, "out": 34}
    ) + "\n", encoding="utf-8")

    data_dir = tmp_path / "veri"
    assert main(["--data-dir", str(data_dir), "--json", "scan"], env={}, home=tmp_path) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["providers"]["demo"]["written"] == 1

    # Ve ayni kayit ikinci taramada tekrar yazilmiyor (dedup).
    assert main(["--data-dir", str(data_dir), "--json", "scan"], env={}, home=tmp_path) == 0
    again = json.loads(capsys.readouterr().out)
    assert again["providers"]["demo"]["written"] == 0


def test_the_entry_point_group_is_the_one_the_docs_name():
    # Belgeye yazilan grup adi ile kodun okudugu grup ayni olmazsa, talimati
    # harfiyen izleyen biri hicbir sey goremez.
    assert ENTRY_POINT_GROUP == "cci.adapters"
    docs = Path(__file__).resolve().parents[1] / "docs" / "EXTENDING.md"
    assert '[project.entry-points."cci.adapters"]' in docs.read_text(encoding="utf-8")


def test_registry_load_failures_start_empty():
    assert Registry().failures() == ()
