"""Dedup ve kaynaklar arasi birlestirme (docs/DATA_MODEL.md §2; ccusage, tycho ADR 0002).

- Ayni `dedup_key` -> kazanan `prefer_over` (sidechain olmayan > daha buyuk toplam
  token > yeni sema); kaybedenin ek bilgisi (satici maliyeti, 5m/1h kirilimi,
  eksik kimlik/atif alanlari) kazanana BIRLESTIRILIR.
- Sidechain replay: ayni `message_key` farkli `dedup_key`; replay (isSidechain)
  dusurulur, ebeveyn kalir.
- Anlamsal kanarya (R-11): iki kaynak ayni istek icin farkli token sayisi
  bildiriyorsa `token_mismatch` sayaci artar (ilk deger tutulur, sessizce ezilmez).
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable, Literal

from cci.model.usage import Attribution, Cost, Timing, Tokens, UsageRecord

Outcome = Literal["inserted", "replaced", "merged", "sidechain_dropped"]


def _fill(primary, secondary, fields: tuple[str, ...]):
    updates = {f: getattr(secondary, f) for f in fields if getattr(primary, f) is None and getattr(secondary, f) is not None}
    return primary.model_copy(update=updates) if updates else primary


def merge_records(winner: UsageRecord, other: UsageRecord, counters: Counter[str] | None = None) -> UsageRecord:
    """Kazanan kayda kaybedenin tamamlayici bilgisini ekler; token sayilarini DEGISTIRMEZ."""
    counters = counters if counters is not None else Counter()
    w, o = winner.tokens, other.tokens
    if not other.flags.synthetic and not winner.flags.synthetic:
        if (w.input, w.output, w.cache_read, w.cache_write_total) != (o.input, o.output, o.cache_read, o.cache_write_total):
            counters["token_mismatch"] += 1
    tokens = w
    if w.cache_write_5m is None and o.cache_write_5m is not None and o.cache_write_total == w.cache_write_total:
        tokens = Tokens(input=w.input, output=w.output, cache_read=w.cache_read, cache_write_5m=o.cache_write_5m,
                        cache_write_1h=o.cache_write_1h, cache_write_total=w.cache_write_total, reasoning=w.reasoning)
        counters["ttl_split_merged"] += 1
    cost = winner.cost
    if cost.vendor_usd is None and other.cost.vendor_usd is not None:
        cost = Cost(usd=cost.usd, vendor_usd=other.cost.vendor_usd, pricing_effective_at=cost.pricing_effective_at)
        counters["vendor_cost_merged"] += 1
    attribution = _fill(winner.attribution, other.attribution,
                        ("query_source", "agent", "skill", "plugin", "mcp_server", "mcp_tool", "marketplace", "speed", "effort"))
    timing = _fill(winner.timing, other.timing, ("duration_ms", "ttft_ms"))
    updates = {"tokens": tokens, "cost": cost, "attribution": attribution, "timing": timing}
    for f in ("prompt_id", "message_id", "uuid", "workspace", "account"):
        if getattr(winner, f) is None and getattr(other, f) is not None:
            updates[f] = getattr(other, f)
    if winner.model.unknown and not other.model.unknown:
        updates["model"] = other.model
    return winner.model_copy(update=updates)


class Deduper:
    def __init__(self) -> None:
        self._by_key: dict[str, UsageRecord] = {}
        self._by_message: dict[str, str] = {}  # message_key -> dedup_key
        self.counters: Counter[str] = Counter()

    def add(self, rec: UsageRecord) -> Outcome:
        """Sonuc geliş sırasından BAĞIMSIZ olmali (ayni ms'de ULID sirasi rastgele)."""
        mk = rec.message_key
        if mk is not None and mk in self._by_message and self._by_message[mk] != rec.dedup_key:
            existing_key = self._by_message[mk]
            existing = self._by_key.get(existing_key)
            if existing is not None and existing.session.is_sidechain != rec.session.is_sidechain:
                if rec.session.is_sidechain:
                    self.counters["sidechain_replay_dropped"] += 1
                    return "sidechain_dropped"
                # mevcut replay, gelen ebeveyn: replay silinir; ebeveyn NORMAL yoldan girer
                # (ayni dedup_key altinda OTel kaydi olabilir -> birlestirilmeli, ezilmemeli)
                del self._by_key[existing_key]
                del self._by_message[mk]
                self.counters["sidechain_replay_dropped"] += 1
                outcome = self._upsert(rec)
                return "replaced" if outcome == "inserted" else outcome
        return self._upsert(rec)

    def _upsert(self, rec: UsageRecord) -> Outcome:
        existing = self._by_key.get(rec.dedup_key)
        if existing is None:
            self._insert(rec)
            self.counters["inserted"] += 1
            return "inserted"
        if rec.prefer_over(existing):
            merged = merge_records(rec, existing, self.counters)
            self.counters["replaced"] += 1
            outcome: Outcome = "replaced"
        else:
            merged = merge_records(existing, rec, self.counters)
            self.counters["merged"] += 1
            outcome = "merged"
        self._by_key[rec.dedup_key] = merged
        if merged.message_key is not None:
            self._by_message[merged.message_key] = rec.dedup_key
        return outcome

    def add_many(self, records: Iterable[UsageRecord]) -> Counter[str]:
        out: Counter[str] = Counter()
        for r in records:
            out[self.add(r)] += 1
        return out

    def _insert(self, rec: UsageRecord) -> None:
        self._by_key[rec.dedup_key] = rec
        if rec.message_key is not None:
            self._by_message[rec.message_key] = rec.dedup_key

    def records(self) -> list[UsageRecord]:
        return sorted(self._by_key.values(), key=lambda r: (r.ts, r.dedup_key))

    def __len__(self) -> int:
        return len(self._by_key)
