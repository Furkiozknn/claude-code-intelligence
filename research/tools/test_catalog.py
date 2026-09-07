"""catalog.py icin testler.

Her test yasanmis veya yasanabilecek bir hataya karsilik gelir.
Calistirma:  python -m unittest research/tools/test_catalog.py -v
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import catalog  # noqa: E402


class _TempCatalog(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._orig = catalog.CATALOG
        catalog.CATALOG = Path(self._tmp.name) / "catalog.jsonl"

    def tearDown(self):
        catalog.CATALOG = self._orig
        self._tmp.cleanup()

    def _ingest(self, entries):
        p = Path(self._tmp.name) / "in.json"
        p.write_text(json.dumps({"entries": entries}), encoding="utf-8")
        catalog.cmd_ingest(str(p))
        return catalog.load()


class TestDerinlikVePuan(_TempCatalog):
    """7 Eylul hatasi: mevcut kayit fetched, gelen kayitta depth yok,
    scores var -> puan yanlislikla dusuruluyordu."""

    def test_fetched_kayda_depth_siz_puan_eklenir(self):
        self._ingest([{"url": "https://github.com/a/b", "depth": "fetched",
                       "summary": "x"}])
        entries = self._ingest([{"url": "https://github.com/a/b",
                                 "scores": {"analytics": 8}}])
        e = entries[catalog.norm_url("https://github.com/a/b")]
        self.assertEqual(e["depth"], "fetched")
        self.assertEqual(e["scores"], {"analytics": 8})
        self.assertIn("total", e)

    def test_shallow_kayda_puan_reddedilir(self):
        entries = self._ingest([{"url": "https://github.com/a/c",
                                 "scores": {"analytics": 8}}])
        e = entries[catalog.norm_url("https://github.com/a/c")]
        self.assertEqual(e["depth"], "shallow")
        self.assertNotIn("scores", e)
        self.assertNotIn("total", e)

    def test_derinlik_asla_dusmez(self):
        self._ingest([{"url": "https://github.com/a/d", "depth": "deep"}])
        entries = self._ingest([{"url": "https://github.com/a/d", "depth": "shallow"}])
        self.assertEqual(entries[catalog.norm_url("https://github.com/a/d")]["depth"], "deep")


class TestBirlestirme(_TempCatalog):
    def test_url_normalizasyonu_tekillestirir(self):
        self._ingest([{"url": "https://github.com/A/B"}])
        entries = self._ingest([{"url": "https://github.com/a/b/"}])
        self.assertEqual(len(entries), 1)

    def test_listeler_birlesir(self):
        self._ingest([{"url": "https://github.com/a/e", "categories": ["cost"]}])
        entries = self._ingest([{"url": "https://github.com/a/e", "categories": ["quota"]}])
        self.assertEqual(entries[catalog.norm_url("https://github.com/a/e")]["categories"],
                         ["cost", "quota"])

    def test_github_disi_atlanir(self):
        entries = self._ingest([{"url": "https://pypi.org/project/x"}])
        self.assertEqual(len(entries), 0)


class TestPuanlama(unittest.TestCase):
    def test_agirliklar_100(self):
        self.assertEqual(sum(catalog.WEIGHTS.values()), 100)

    def test_toplam_eksik_kriterle_hesaplanir(self):
        t = catalog.total({"data_collection": 10})
        self.assertEqual(t, 15.0)
        self.assertEqual(catalog.scored_weight({"data_collection": 10}), 15)

    def test_puan_0_10_araligina_kirpilir(self):
        self.assertEqual(catalog.total({"data_collection": 15}), 15.0)
        self.assertEqual(catalog.total({"data_collection": -3}), 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
