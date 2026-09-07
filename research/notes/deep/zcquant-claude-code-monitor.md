# Derin analiz · zcquant/claude-code-monitor

**Okunan:** `otlp-receiver.js`, `otel-config.js`, `setup-claude-telemetry.sh`;
dosya listesi (`grpc-receiver.js`, `monitor.js`, `report.js`, `web-dashboard.js`).
Node/Express, 12★. Kategori: **yerleşik OTLP alıcı** — Top-20'de bu yaklaşımın
tek küçük örneği; değeri "ne kadar az kodla olur" ölçütü.

## Ne yapıyor
- HTTP/JSON OTLP alıcı `:4318` (`/v1/metrics`), ayrıca gRPC alıcı (`:4317`,
  `grpc-receiver.js`). `/v1/traces` ve `/v1/logs` **kabul edilip atılıyor**.
- Protobuf gövde **işlenmiyor** (yalnız "200 OK") — `OTEL_EXPORTER_OTLP_PROTOCOL=
  http/json` dışında veri kaybı. gRPC alıcı ayrı dosyada.
- `claude_code.token.usage` → `type` özniteliğine göre input/output/cacheRead/
  cacheCreation toplamı; `claude_code.cost.usage` → `model` başına maliyet.
  Diğer metrikler yalnız konsola yazılıyor. **`session.id`, `user.*`,
  `query_source` gibi öznitelikler atılıyor** → oturum/proje kırılımı yok.
- Kurulum betiği kabuk rc dosyasına env ekliyor (yedek alarak), export aralığı
  10 sn.
- Kendi metriklerini Prometheus `:9464`'ten yeniden yayınlıyor (OTel SDK).

## §8 değerlendirme
| | |
|---|---|
| Data acquisition | OTLP alıcı (JSON + gRPC); protobuf yok; logs/traces yok |
| Data model | Toplam sayaçlar; öznitelik kaybı |
| Storage | `daily-usage.json` |
| Reliability | Alıcı kapalıyken davranış ele alınmamış |
| Privacy | Hook/prompt içeriği yok (metrik-only) |

## Platforma aktarılacaklar
1. OTLP alıcının **asgari yüzeyi** (JSON + gRPC + protobuf üçü de) ve tüm
   veri noktası özniteliklerinin korunması; `api_request` **log olayları**
   (cost_usd_micros, request_id, prompt.id) asıl zenginlik — atılmamalı.
2. `setup` komutu: env'i kabuk rc'ye değil `~/.claude/settings.json` `env`
   bloğuna yazmalı (belgeli, taşınabilir; notes/02 §G).
3. Anti-örnek: içerik türü kontrolü olmadan "200 OK" dönmek sessiz veri kaybı.
