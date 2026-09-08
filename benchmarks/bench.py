"""Benchmark (MP §43 Engineering): hedefler docs/ARCHITECTURE.md §11.

    uv run python benchmarks/bench.py [--events 100000] [--transcript-mb 50]

Olcer: transcript tarama hizi (MB/s), OTLP ingest (olay/s), depo yazma (olay/s),
gunluk ozet sorgusu (ms), replay (olay/s). Sonuclari benchmarks/RESULTS.md'ye yazar.
"""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from cci.adapters.claude_code import ClaudeCodeAdapter
from cci.collectors.otlp_map import OtlpLogMapper
from cci.pipeline import Pipeline
from cci.pricing import PricingTable
from cci.store import EventStore

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


def _assistant(i: int) -> dict:
    return {"type": "assistant", "uuid": f"u{i}", "timestamp": (NOW + timedelta(seconds=i)).isoformat(),
            "sessionId": f"sess-{i % 50}", "requestId": f"req_{i}", "cwd": "D:/proj",
            "message": {"id": f"msg_{i}", "model": "claude-opus-5", "role": "assistant",
                        "usage": {"input_tokens": 120, "output_tokens": 300, "cache_creation_input_tokens": 100,
                                  "cache_read_input_tokens": 5000,
                                  "cache_creation": {"ephemeral_5m_input_tokens": 60, "ephemeral_1h_input_tokens": 40}},
                        "content": [{"type": "text", "text": "x" * 400}]}}


def _otlp_doc(i: int) -> dict:
    kv = lambda k, v: {"key": k, "value": {"stringValue": v} if isinstance(v, str) else {"intValue": str(v)}}
    return {"resourceLogs": [{"resource": {"attributes": [kv("session.id", f"s{i % 50}"), kv("user.account_uuid", "acc")]},
            "scopeLogs": [{"logRecords": [{"timeUnixNano": str(int((NOW + timedelta(seconds=i)).timestamp() * 1e9)),
             "attributes": [kv("event.name", "api_request"), kv("model", "claude-opus-5"), kv("request_id", f"o{i}"),
                            kv("input_tokens", 100), kv("output_tokens", 50), kv("cost_usd_micros", 1000)]}]}]}]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", type=int, default=20000)
    ap.add_argument("--transcript-mb", type=float, default=20.0)
    args = ap.parse_args()
    tmp = Path(tempfile.mkdtemp(prefix="cci-bench-"))
    results: list[tuple[str, str, str]] = []
    try:
        # 1) transcript tarama
        root = tmp / ".claude"
        f = root / "projects" / "P" / "s.jsonl"
        f.parent.mkdir(parents=True, exist_ok=True)
        line_len = len(json.dumps(_assistant(0))) + 1
        n_lines = int(args.transcript_mb * 1024 * 1024 / line_len)
        with f.open("w", encoding="utf-8") as fh:
            for i in range(n_lines):
                fh.write(json.dumps(_assistant(i)) + "\n")
        mb = f.stat().st_size / 1024 / 1024
        store = EventStore(tmp / "events.db")
        pipe = Pipeline(store, PricingTable.load_bundled(), ZoneInfo("UTC"), cursors_path=tmp / "cursors.json")
        adapter = ClaudeCodeAdapter(env={"CLAUDE_CONFIG_DIR": str(root)}, home=tmp)
        t0 = time.perf_counter()
        rep = pipe.ingest_transcripts(adapter)
        dt = time.perf_counter() - t0
        results.append(("transcript tarama+normalize+yazma", f"{mb:.1f} MB / {rep.written} olay", f"{mb / dt:.1f} MB/s, {rep.written / dt:,.0f} olay/s"))

        # 2) OTLP esleme
        mapper = OtlpLogMapper()
        docs = [_otlp_doc(i) for i in range(min(args.events, 20000))]
        t0 = time.perf_counter()
        envs = [e for d in docs for e in mapper.map_request(d)]
        dt = time.perf_counter() - t0
        results.append(("OTLP JSON esleme", f"{len(envs)} olay", f"{len(envs) / dt:,.0f} olay/s"))

        # 3) depo yazma
        t0 = time.perf_counter()
        written, _ = store.append_many(envs)
        dt = time.perf_counter() - t0
        results.append(("SQLite yazma (idempotent)", f"{written} olay", f"{written / dt:,.0f} olay/s"))

        # 4) gunluk ozet (dedup + fiyat + ozet)
        t0 = time.perf_counter()
        days = pipe.daily()
        dt = time.perf_counter() - t0
        total = store.count()
        results.append(("gunluk ozet (replay+dedup+fiyat)", f"{total:,} olay -> {len(days)} gun", f"{dt * 1000:,.0f} ms ({total / dt:,.0f} olay/s)"))

        # 5) depo boyutu
        size = (tmp / "events.db").stat().st_size
        results.append(("depo boyutu", f"{total:,} olay", f"{size / 1024 / 1024:.1f} MB ({size / max(total, 1):,.0f} B/olay)"))
        store.close()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    out = ["# Benchmark sonuclari", "", f"Tarih: {datetime.now(UTC).date().isoformat()}  ·  `uv run python benchmarks/bench.py`", "",
           "| Olcut | Boyut | Sonuc |", "|---|---|---|"]
    out += [f"| {a} | {b} | {c} |" for a, b, c in results]
    out += ["", "Hedefler: docs/ARCHITECTURE.md §11 (OTLP >= 2.000 olay/s, gunluk rapor p95 < 200 ms, transcript <= 60 s / 500 MB)."]
    Path(__file__).with_name("RESULTS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print("\n".join(f"{a}: {c}  ({b})" for a, b, c in results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
