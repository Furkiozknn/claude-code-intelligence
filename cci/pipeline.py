"""Boru hatti: toplayicilar -> ingest kapisi -> olay deposu -> normalize -> dedup/birlestir
-> fiyat -> ozetler. Tek yerden, saf adimlarla (docs/ARCHITECTURE.md §4).

`ingest_transcripts` artimli (imlec dosyasi); OTLP alicisi `sink` ile ayni depoya yazar.
`records()` her cagrida depodaki `usage.request` olaylarindan yeniden turetir
(replay ilkesi: turetilmis tablolar olaylardan uretilebilir).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, tzinfo
from pathlib import Path
from typing import Iterable

from cci.adapters.base import Cursor
from cci.adapters.claude_code.adapter import ClaudeCodeAdapter
from cci.analytics.diagnostics import SessionDiagnostics, diagnose_session, worst_attention
from cci.analytics.summaries import DailySummary, SessionSummary, price_records, summarize_daily, summarize_sessions
from cci.model.estimate import QuotaForecast
from cci.model.figure import Figure
from cci.model.quota import QuotaSnapshot
from cci.quota.forecast import forecast
from cci.collectors.transcript import COLLECTOR_NAME, COLLECTOR_VERSION, SCHEMA_VERSION, TranscriptCollector
from cci.events.envelope import Envelope, SourceRef
from cci.ingest.allowlist import IngestGate
from cci.model.evidence import EvidenceClass
from cci.model.ids import AccountRef
from cci.model.usage import UsageRecord
from cci.normalize.dedup import Deduper
from cci.normalize.transcript import normalize_transcript_batch
from cci.pricing.table import PricingTable
from cci.store.cursors import load_cursors, save_cursors
from cci.store.sqlite import EventStore


@dataclass
class IngestReport:
    instances: int = 0
    raw_items: int = 0
    records: int = 0
    written: int = 0
    duplicates: int = 0
    rejected: int = 0
    skipped_lines: int = 0
    counters: Counter = field(default_factory=Counter)


def record_envelope(rec: UsageRecord) -> Envelope:
    return Envelope(type="usage.request", ts=rec.ts, source=SourceRef(
        collector=rec.collector.name, instance_id=rec.source.instance_id,
        collector_version=rec.collector.version, schema_version=rec.collector.schema_version),
        provider=rec.provider, account_key=rec.account.account_key if rec.account else None,
        session_id=rec.session.session_id, privacy_class="sensitive" if rec.workspace else "internal",
        evidence_class=EvidenceClass.OBSERVED, payload=rec.model_dump(mode="json"))


class Pipeline:
    def __init__(self, store: EventStore, table: PricingTable, tz: tzinfo, *, cursors_path: Path | None = None,
                 account: AccountRef | None = None, gate: IngestGate | None = None) -> None:
        self.store = store
        self.table = table
        self.tz = tz
        self.cursors_path = cursors_path
        self.account = account
        self.gate = gate or IngestGate()
        self.dedup_counters: Counter = Counter()

    # --- giris ------------------------------------------------------------
    def sink(self, env: Envelope) -> bool:
        """OTLP alicisi ve diger toplayicilar icin ortak yazma noktasi (kapidan gecmis zarf)."""
        return self.store.append(env)

    def ingest_transcripts(self, adapter: ClaudeCodeAdapter, collector: TranscriptCollector | None = None) -> IngestReport:
        collector = collector or TranscriptCollector()
        cursors = load_cursors(self.cursors_path) if self.cursors_path else {}
        report = IngestReport()
        for instance in adapter.discover():
            report.instances += 1
            batch = collector.collect(instance, cursors.get(instance.instance_id, Cursor()))
            report.raw_items += len(batch.items)
            report.skipped_lines += batch.skipped
            records, counters = normalize_transcript_batch(batch, self.account)
            report.counters.update(counters)
            report.records += len(records)
            envelopes = []
            for rec in records:
                env = record_envelope(rec)
                decision = self.gate.check(env)
                if decision.accepted:
                    envelopes.append(env)
                else:
                    report.rejected += 1
                    report.counters[decision.reason] += 1
            written, dup = self.store.append_many(envelopes)
            report.written += written
            report.duplicates += dup
            cursors[instance.instance_id] = batch.next_cursor
        if self.cursors_path:
            save_cursors(self.cursors_path, cursors)
        return report

    # --- turetim -------------------------------------------------------------
    def records(self, *, since: datetime | None = None, until: datetime | None = None) -> list[UsageRecord]:
        deduper = Deduper()
        for env in self.store.query(types=["usage.request"], since=since, until=until):
            try:
                rec = UsageRecord.from_payload(env.payload)
            except Exception:
                self.dedup_counters["invalid_payload"] += 1
                continue
            deduper.add(rec)
        self.dedup_counters.update(deduper.counters)
        return price_records(deduper.records(), self.table)

    def daily(self, *, since: datetime | None = None, until: datetime | None = None, strict: bool = False) -> list[DailySummary]:
        return summarize_daily(self.records(since=since, until=until), self.tz, pricing_version=self.table.version, strict=strict)

    def sessions(self, *, since: datetime | None = None, until: datetime | None = None, strict: bool = False) -> list[SessionSummary]:
        return summarize_sessions(self.records(since=since, until=until), strict=strict)

    # --- kota gecmisi (Stage 10) ----------------------------------------------
    def quota_history(self, *, since: datetime | None = None) -> list[QuotaSnapshot]:
        out: list[QuotaSnapshot] = []
        for env in self.store.query(types=["quota.snapshot"], since=since):
            try:
                out.append(QuotaSnapshot.from_payload(env.payload))
            except Exception:
                self.dedup_counters["invalid_quota_payload"] += 1
        return out

    def forecasts(self, now: datetime, kinds: tuple[str, ...] = ("session_5h", "weekly_all")) -> dict[str, QuotaForecast]:
        hist = self.quota_history()
        out: dict[str, QuotaForecast] = {}
        for kind in kinds:
            f = forecast(hist, kind, now)  # type: ignore[arg-type]
            if f is not None:
                out[kind] = f
        return out

    # --- teshis (Stage 8) ------------------------------------------------------
    DIAG_TYPES = ("tool.call", "usage.error", "session.compacted", "usage.request", "statusline.tick")

    def diagnose(self, session_id: str, *, cost: Figure | None = None, summaries: list[SessionSummary] | None = None) -> SessionDiagnostics:
        if cost is None:
            for s in (summaries if summaries is not None else self.sessions()):
                if s.session_id == session_id:
                    cost = s.totals.cost
                    break
        events = self.store.query(types=self.DIAG_TYPES, session_id=session_id)
        return diagnose_session(session_id, events, cost=cost)

    def attention(self, now: datetime, *, active_window_s: int = 1800) -> tuple[str, list[SessionDiagnostics]]:
        """Aktif oturumlarin (son `active_window_s` icinde) en kotu dikkat seviyesi."""
        summaries = self.sessions()
        active = [s for s in summaries if (now - s.last_at).total_seconds() <= active_window_s]
        diags = [self.diagnose(s.session_id, cost=s.totals.cost) for s in active]
        return worst_attention(d.attention for d in diags), diags
