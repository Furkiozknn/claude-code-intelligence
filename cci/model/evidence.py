"""Kanit ve gizlilik siniflari (docs/DATA_MODEL.md §1.1, §1.3)."""

from __future__ import annotations

from enum import Enum
from typing import Iterable


class EvidenceClass(str, Enum):
    OBSERVED = "observed"                  # saglayici/istemci dogrudan raporladi
    DERIVED = "derived"                    # gozlemlerden deterministik hesap
    VENDOR_ESTIMATED = "vendor_estimated"  # saticinin kendi tahmini (Claude Code cost_usd)
    ESTIMATED = "estimated"                # bizim model + fiyat tablosu
    PREDICTED = "predicted"                # gelecek; bant ve guvenle
    INFERRED = "inferred"                  # dolayli kanit, dusuk guven

    @property
    def rank(self) -> int:
        """Buyuk deger = daha zayif kanit."""
        return _RANK[self]

    @classmethod
    def weakest(cls, items: Iterable["EvidenceClass"]) -> "EvidenceClass":
        items = list(items)
        if not items:
            raise ValueError("bos kanit listesi")
        return max(items, key=lambda e: e.rank)


_RANK = {
    EvidenceClass.OBSERVED: 0,
    EvidenceClass.DERIVED: 1,
    EvidenceClass.VENDOR_ESTIMATED: 2,
    EvidenceClass.ESTIMATED: 3,
    EvidenceClass.PREDICTED: 4,
    EvidenceClass.INFERRED: 5,
}


class PrivacyClass(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    SENSITIVE = "sensitive"
    SECRET = "secret"  # yalniz siniflandirma sozlugu icin; alan etiketi olarak yasak
