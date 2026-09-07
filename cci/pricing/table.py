"""PricingTable: model -> 5 bilesenli fiyat (+200k kademesi) ve `cost()` -> Figure.

Kurallar:
- Gomulu snapshot `data/anthropic.json` (LiteLLM'den suzulmus, tarihli, sha256'li).
  Yenileme YALNIZ acik komutla (`cci pricing refresh`) - otomatik ag cagrisi yok.
- Bilinmeyen model -> Figure.withheld("bilinmeyen model fiyati").
- Cache tokeni var ama fiyat bileseni yok -> withheld.
- 5m/1h kirilimi yoksa toplam 5 dk oraniyla fiyatlanir ve Figure `draft` olur
  (varsayim altinda fiyat; tycho: 1 saatlik prim ayrilmadan maliyet yanlis).
- input_total > 200k -> uzun baglam kademesi (varsa) tum bilesenlere uygulanir.
- Para nanoUSD Decimal, tam sayiya yuvarlanir.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Mapping

from cci.model.evidence import EvidenceClass
from cci.model.figure import NANO, EstimatorRef, Figure
from cci.model.usage import Tokens

LONG_CONTEXT_THRESHOLD = 200_000
DATA_PATH = Path(__file__).with_name("data") / "anthropic.json"
_DATE_SUFFIX = re.compile(r"-(\d{8})$")


def normalize_for_pricing(model_id: str) -> list[str]:
    """Denenecek anahtarlar, sirali: oldugu gibi, saglayici/bolge oneki atilmis,
    bedrock `-v1:0` atilmis, tarih son eki atilmis."""
    cands: list[str] = []
    m = model_id.strip()
    cands.append(m)
    idx = m.find("claude-")
    if idx > 0:
        m = m[idx:]
        cands.append(m)
    m2 = re.sub(r"-v\d+:\d+$", "", m)
    if m2 != m:
        cands.append(m2)
    m3 = _DATE_SUFFIX.sub("", m2)
    if m3 != m2:
        cands.append(m3)
    m4 = m3.replace("@", "-")
    if m4 != m3:
        cands.append(m4)
    seen: set[str] = set()
    return [c for c in cands if not (c in seen or seen.add(c))]


def _dec(v: Any) -> Decimal | None:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float, str)):
        return Decimal(str(v))
    return None


@dataclass(frozen=True)
class Price:
    model: str
    input: Decimal
    output: Decimal
    cache_read: Decimal | None = None
    cache_write_5m: Decimal | None = None
    cache_write_1h: Decimal | None = None
    input_above_200k: Decimal | None = None
    output_above_200k: Decimal | None = None
    cache_read_above_200k: Decimal | None = None
    cache_write_5m_above_200k: Decimal | None = None
    cache_write_1h_above_200k: Decimal | None = None
    max_input_tokens: int | None = None
    deprecation_date: date | None = None

    @classmethod
    def from_litellm(cls, model: str, row: Mapping[str, Any]) -> "Price | None":
        inp, out = _dec(row.get("input_cost_per_token")), _dec(row.get("output_cost_per_token"))
        if inp is None or out is None:
            return None
        dep = row.get("deprecation_date")
        try:
            dep_date = date.fromisoformat(dep) if isinstance(dep, str) else None
        except ValueError:
            dep_date = None
        return cls(
            model=model, input=inp, output=out,
            cache_read=_dec(row.get("cache_read_input_token_cost")),
            cache_write_5m=_dec(row.get("cache_creation_input_token_cost")),
            cache_write_1h=_dec(row.get("cache_creation_input_token_cost_above_1hr")),
            input_above_200k=_dec(row.get("input_cost_per_token_above_200k_tokens")),
            output_above_200k=_dec(row.get("output_cost_per_token_above_200k_tokens")),
            cache_read_above_200k=_dec(row.get("cache_read_input_token_cost_above_200k_tokens")),
            cache_write_5m_above_200k=_dec(row.get("cache_creation_input_token_cost_above_200k_tokens")),
            cache_write_1h_above_200k=_dec(row.get("cache_creation_input_token_cost_above_1hr_above_200k_tokens")),
            max_input_tokens=row.get("max_input_tokens") if isinstance(row.get("max_input_tokens"), int) else None,
            deprecation_date=dep_date,
        )

    def tier(self, long_context: bool) -> tuple[Decimal, Decimal, Decimal | None, Decimal | None, Decimal | None]:
        if long_context and self.input_above_200k is not None and self.output_above_200k is not None:
            return (self.input_above_200k, self.output_above_200k,
                    self.cache_read_above_200k if self.cache_read_above_200k is not None else self.cache_read,
                    self.cache_write_5m_above_200k if self.cache_write_5m_above_200k is not None else self.cache_write_5m,
                    self.cache_write_1h_above_200k if self.cache_write_1h_above_200k is not None else self.cache_write_1h)
        return self.input, self.output, self.cache_read, self.cache_write_5m, self.cache_write_1h


class PricingTable:
    def __init__(self, prices: Mapping[str, Price], *, version: str, fetched_at: date, source: str = "") -> None:
        self._prices = dict(prices)
        self.version = version
        self.fetched_at = fetched_at
        self.source = source

    @property
    def estimator(self) -> EstimatorRef:
        return EstimatorRef(id="pricing.litellm", version=self.version)

    def __len__(self) -> int:
        return len(self._prices)

    def models(self) -> tuple[str, ...]:
        return tuple(sorted(self._prices))

    @classmethod
    def from_snapshot(cls, doc: Mapping[str, Any]) -> "PricingTable":
        models = doc.get("models") or {}
        prices: dict[str, Price] = {}
        for k, row in models.items():
            if isinstance(row, Mapping):
                p = Price.from_litellm(k, row)
                if p is not None:
                    prices[k] = p
        fetched = date.fromisoformat(str(doc.get("fetched_at")))
        sha = str(doc.get("sha256", ""))[:8]
        return cls(prices, version=f"{fetched.isoformat()}-{sha or 'nohash'}", fetched_at=fetched,
                   source=str(doc.get("source", "")))

    @classmethod
    def from_litellm(cls, doc: Mapping[str, Any], *, fetched_at: date, sha256: str = "", provider: str = "anthropic") -> "PricingTable":
        models = {k: v for k, v in doc.items() if isinstance(v, Mapping) and v.get("litellm_provider") == provider
                  and k.startswith("claude-")}
        return cls.from_snapshot({"models": models, "fetched_at": fetched_at.isoformat(), "sha256": sha256})

    @classmethod
    def load_bundled(cls, path: Path = DATA_PATH) -> "PricingTable":
        return cls.from_snapshot(json.loads(path.read_text(encoding="utf-8")))

    def lookup(self, model_id: str) -> Price | None:
        for cand in normalize_for_pricing(model_id):
            p = self._prices.get(cand)
            if p is not None:
                return p
        return None

    def cost(self, tokens: Tokens, model_id: str) -> Figure:
        price = self.lookup(model_id)
        if price is None:
            return Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, f"bilinmeyen model fiyati: {model_id}")
        inp, out, cr, cw5, cw1 = price.tier(tokens.input_total > LONG_CONTEXT_THRESHOLD)
        usd = Decimal(tokens.input) * inp + Decimal(tokens.output) * out
        draft = False
        if tokens.cache_read:
            if cr is None:
                return Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "cache okuma fiyati yok")
            usd += Decimal(tokens.cache_read) * cr
        if tokens.cache_write_total:
            if cw5 is None:
                return Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "cache yazma fiyati yok")
            if tokens.cache_write_5m is not None and tokens.cache_write_1h is not None:
                if tokens.cache_write_1h and cw1 is None:
                    return Figure.withheld("nanoUSD", EvidenceClass.ESTIMATED, "1 saatlik cache yazma fiyati yok")
                usd += Decimal(tokens.cache_write_5m) * cw5 + Decimal(tokens.cache_write_1h) * (cw1 or Decimal(0))
            else:
                usd += Decimal(tokens.cache_write_total) * cw5
                draft = True  # TTL kirilimi bilinmiyor: 5 dk varsayimi
        nano = (usd * NANO).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        return Figure.estimated(nano, "nanoUSD", self.estimator, released_as="draft" if draft else "reconciled")
