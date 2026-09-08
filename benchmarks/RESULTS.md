# Benchmark sonuclari

Tarih: 2026-09-08  ·  `uv run python benchmarks/bench.py`

| Olcut | Boyut | Sonuc |
|---|---|---|
| transcript tarama+normalize+yazma | 8.1 MB / 9664 olay | 2.0 MB/s, 2,412 olay/s |
| OTLP JSON esleme | 8000 olay | 7,784 olay/s |
| SQLite yazma (idempotent) | 8000 olay | 8,379 olay/s |
| gunluk ozet (replay+dedup+fiyat) | 17,664 olay -> 2 gun | 5,001 ms (3,532 olay/s) |
| depo boyutu | 17,664 olay | 39.9 MB (2,368 B/olay) |

Hedefler: docs/ARCHITECTURE.md §11 (OTLP >= 2.000 olay/s, gunluk rapor p95 < 200 ms, transcript <= 60 s / 500 MB).
