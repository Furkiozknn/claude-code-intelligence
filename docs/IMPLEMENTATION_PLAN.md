# IMPLEMENTATION_PLAN — MP §42 Stage 1–16

Sıra MP'nin verdiği sıradır; her aşamanın **kabul ölçütü** ve testi var
(SELF_CRITIQUE R-1: bunlar yoksa proje "yeniden adlandırma"dır). Aşama etiketi
= sentez/ARCHITECTURE §8 (Core/Adv/Intel/Eco). Teknoloji (D10): Python 3.12,
`uv`, `pydantic` v2 (`extra="forbid"`, JSON şema üretimi), SQLite (stdlib),
`opentelemetry-proto` (protobuf çözümü), `pytest`. Bağımlılık ekleme gerekçe ister.

| Stage | İçerik | Teslimat | Kabul ölçütü / test | Aşama |
|---|---|---|---|---|
| 1 | Core data model | `cci/model`: EvidenceClass, Figure, PrivacyClass, AccountRef, SourceInstance, UsageRecord, QuotaSnapshot, Estimate, Alert, Recommendation; JSON şemaları; `tests/schema` | Şemada `secret` yok; her alan sınıf etiketli; `Figure` toplama kuralları testli (withheld/draft/projected miras); `Figure.render()` released değilse sayı vermez | Core |
| 2 | Provider abstraction | `cci/adapters/base.py` (PROVIDERS §2 arayüzü), `SourceInstance`, `capabilities`, `probe_roots`, registry; `claude_code` adaptörü iskeleti | Arayüz tip-denetimli; sahte adaptörle sözleşme testi; `schema_verified` alanı zorunlu | Core |
| 3 | Collectors | OTLP HTTP alıcı (json + protobuf; gRPC opsiyonel), transcript izleyici (özyinelemeli, manifest), kota poller (P4 kuralları), ingest kapısı (allow-list, boyut, sınıf); `cci setup --otlp` | Fixture OTLP gövdeleri → olay; yasak anahtar reddi; 429 → retry_after; alıcı-kapalı deneyi (U2) günlüğü; boşta CPU < %1 | Core |
| 4 | Raw storage | `events` (append-only, ulid, payload_hash idempotent), 30 gün saklama + payload budama (R-12), WAL, 0600 | 100 k olay yazma ≥ 2 k/sn; aynı hash iki kez yazılmaz; izin testi | Core |
| 5 | Normalization | UsageRecord üretimi; dedup (message.id+requestId+session, max toplam); sidechain replay; advisor iterations; sentetik; `input`/`input_total`; model eşleme; QuotaSnapshot sınıflandırma + authoritative | tycho/ccusage kurallarının fixture testleri (7 kopya → 1; sidechain; advisor); bilinmeyen model sayacı | Core |
| 6 | Usage analytics | Günlük/oturum özetleri (sürümlü cache), koruma yasası, `Figure` maliyet (LiteLLM bundled, tarihli), `cci today/daily/weekly/monthly`, `cci doctor` sayaçları + anlamsal kanaryalar (R-11), `cci replay` | Golden raporlar bit-eşit; `--strict` çıkış 3 ihlalde; rozetler golden'da (R-8); 10 M sentetik olay benchmark'ı | Core |
| 7 | Quota engine | Pace v1, reset toleransı, hesap kimliği kuralı (R-9), `cci quota`, snapshot dosyası (`state/latest.json`, `next_display_change_at`), statusline betiği | Pace kenar durum testleri; kimlik yoksa snapshot'ta kota yok; statusline ≤ 50 ms | Core |
| 8 | Session/project/model analytics | Teşhis modeli (döngü, retry, p95, context), dikkat merdiveni, proje/atıf (transcript+OTel öznitelikleri), model karışımı, cache ekonomisi, `cci session/project/model/cache` | Merdiven deterministik testleri; koruma yasası atıfta | Adv |
| 9 | Dashboard | Loopback HTTP+WS API (token), web sayfaları (PRODUCT §3), tray (ikon/tooltip), TUI iskeleti | Yüzey hesap yapmaz (snapshot/API); CSP; dashboard kapalıyken toplama sürer (test) | Adv |
| 10 | Forecasting | Harman v2, estimator registry/sürüm, backtest protokolü, `cci quota --backtest`, `learning` kapısı (R-7) | Kaydedilmiş snapshot fixture'larında MAE raporu; sürüm değişince eski tahminler korunur | Intel |
| 11 | Anomaly detection | Kişisel taban (P50/P90), oran uyarıları, döngü/retry fırtınası, sağlayıcı anomalileri | Sentetik seride tespit/yanlış-pozitif testleri | Intel |
| 12 | Alerts | Kural motoru, cooldown/dedupe, kanallar (snapshot, tray, CLI, webhook), sessiz saatler | Fırtına testi: dakikada ≤ 3 | Intel |
| 13 | Research mode | Ayrı komut/dizin, proxy (başlık temizleme), kota birimi estimator'ı, deney günlüğü, şema keşfi | Çekirdek DB'ye yazmadığı testi; başlık sızıntısı testi; bant çıktısı | Intel |
| 14 | Recommendation engine | Advisor merdiveni, kanıt, `Figure` beklenti, act günlüğü (yedek→hash→uygula→geri al), realized-vs-estimated, guard (opsiyonel hook) | Geri alma bit-eşit; fail-open hook testi; realized doldurma | Intel |
| 15 | Cross-provider support | Codex (rollout + app-server), Gemini CLI, Copilot (SQLite), aider adaptörleri; JSON-RPC/stdio taşıması (R-5); account/local kapsam | Her adaptör tarihli fixture + `schema_verified`; kapsam dışlama gerekçesi | Eco |
| 16 | CLI/TUI/Desktop surfaces | TUI tam, widget, tray menüsü, paketleme (PyInstaller), kurulum belgeleri | 80×24 TUI; widget ≤ 120×40; kontrast testi; kurulum sıfırdan 5 dk | Eco |

## Stage 1 ayrıntı (ilk kod)
```
cci/model/evidence.py    EvidenceClass, PrivacyClass (Enum)
cci/model/figure.py      Figure (+ sum(), render(), miras kuralları)
cci/model/ids.py         AccountRef, SourceInstance, SessionRef
cci/model/usage.py       UsageRecord (+ dedup_key(), tokens türetimleri)
cci/model/quota.py       QuotaSnapshot, QuotaWindow (+ classify(duration_s))
cci/model/estimate.py    Estimate, QuotaForecast
cci/model/alert.py       Alert, Recommendation
cci/model/schema.py      JSON şema dışa aktarımı; alan etiketleri (privacy) meta
tests/test_figure.py     toplama/miras/render
tests/test_privacy_schema.py  'secret' yok, etiket zorunlu, extra forbid
tests/test_quota_classify.py  300/10080/28–31 gün, unclassified, authoritative
tests/test_usage_dedup_key.py
```
Tanım tamamlandı sayılır: `uv run pytest` yeşil; `python -m cci.model.schema`
JSON şemaları `docs/schema/` altına yazar; README "Durum" güncellenir.

## Benchmark (MP §43 Engineering)
`benchmarks/`: transcript tarama (500 MB), OTLP ingest (olay/sn), sorgu p95,
replay (1 M / 10 M sentetik), bellek/CPU boşta. Sonuçlar `benchmarks/RESULTS.md`
tarihli; hedefler ARCHITECTURE §11.
