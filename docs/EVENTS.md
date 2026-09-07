# EVENTS — olay zarfı, türler, akış

Durum: Faz 7 taslağı. Karar: **olay güdümlü ama tek süreç** (in-process bus;
dış broker yok — MP §12 "gereksiz karmaşıklık yok"). Olaylar append-only
`events` tablosuna yazılır; tüm türetilmiş tablolar olaylardan yeniden
üretilebilir (reproducible analytics, MP §30).

## 1. Zarf (her olayda)
```
Envelope {
  event_id: ulid
  type: str                       # aşağıdaki katalog
  ts: datetime (UTC)              # olayın kendi zamanı
  received_at: datetime           # bizim aldığımız zaman (gecikme ölçümü)
  source: { collector: str, instance_id: str, collector_version: str, schema_version: int }
  provider: str | null
  account_key: str | null
  session_id: str | null
  privacy_class: "public"|"internal"|"sensitive"   # zarfın en yüksek alan sınıfı
  evidence_class: EvidenceClass
  payload: <türe özgü, allow-list şeması>
  payload_hash: str               # idempotent yazım / dedup
}
```
Kurallar: bilinmeyen `type` → `dropped_unknown_type` sayacı (hata değil);
`payload` allow-list dışı anahtar → olay **reddedilir** ve `rejected_forbidden_key`
sayacı artar, anahtar adı loga **yazılmaz** (cacheeconomics); zarf 64 KB üstü
reddedilir.

## 2. Olay kataloğu
| Tür | Üretici | Payload (özet) | Kanıt |
|---|---|---|---|
| `usage.request` | OTLP log `api_request`, transcript, proxy (research) | `UsageRecord` alanları | observed |
| `usage.error` | OTLP `api_error`, transcript sentetik kayıt | model, status_code, attempt, duration_ms, error_class | observed |
| `usage.refusal` | OTLP `api_refusal` | model, attempt, category? | observed |
| `quota.snapshot` | kota poller, statusline tap, header yakalama | `QuotaSnapshot` | observed |
| `quota.reset_observed` | türetici | window_kind, previous_resets_at, new_resets_at | derived |
| `session.started` / `session.ended` | hook SessionStart/End, OTLP `session.count`, transcript ilk/son kayıt | start_type, entrypoint, version | observed |
| `session.compacted` | hook PreCompact/PostCompact, transcript, semconv `conversation.compacted` | trigger, tokens_before?, tokens_after? | observed |
| `prompt.submitted` | hook UserPromptSubmit, OTLP `user_prompt` | prompt_id, prompt_length, command_name? (**metin yok**) | observed |
| `tool.call` | OTLP `tool_result`, hook PostToolUse | tool_name, tool_use_id, success, duration_ms, error_type, input_size_bytes, result_size_bytes, mcp_server_scope, decision_source | observed |
| `tool.decision` | OTLP `tool_decision` | tool_name, decision, tool_source, source | observed |
| `permission.mode_changed` | OTLP | from_mode, to_mode, trigger | observed |
| `mcp.connection` | OTLP `mcp_server_connection` | server_name, status, transport, duration_ms, error_code | observed |
| `code.lines` / `code.commit` / `code.pr` | OTLP metrikleri | added/removed, count | observed |
| `statusline.tick` | statusline tap | context_window{…}, prompt_cache{…}, cost.total_cost_usd, model, effort, fast_mode | observed (+vendor_estimated) |
| `provider.health` | her toplayıcı | status, last_success_at, lag_s, error_class, retry_after | derived |
| `provider.schema_change` | adaptör | field_added/removed, sample_hash, unclassified_windows | derived |
| `collector.health` | çekirdek | queue_depth, dropped, rejected, parse_errors | derived |
| `estimate.published` | estimator | estimator{id,version}, target, value/band/confidence | predicted/estimated |
| `alert.raised` / `alert.resolved` | alert engine | rule_id, severity, evidence | derived |
| `recommendation.issued` / `.applied` / `.reverted` / `.evaluated` | advisor/act | rec_id, plan_hash, realized | derived |

## 3. Kaynak → olay eşlemesi (Claude Code)
- **OTLP logs** (`/v1/logs`): `claude_code.api_request` → `usage.request`;
  `api_error` → `usage.error`; `tool_result` → `tool.call`; `user_prompt` →
  `prompt.submitted`; `assistant_response` → yalnız `response_length`
  (`prompt.responded`); `api_request_body/response_body` → **yalnız Research
  Mode**, ayrı depo, asla `events`.
- **OTLP metrics** (`/v1/metrics`): `token.usage`/`cost.usage` kümülatif sayaç
  → delta hesaplanıp `usage.metric_delta` (çapraz doğrulama için; birincil
  değil), `lines_of_code.count` → `code.lines`, `session.count` → `session.started`,
  `active_time.total` → `session.active_time`.
- **OTLP traces** (`/v1/traces`, beta): **Core dışı** (R-2). Stage 3'te
  opsiyonel bayrakla kabul edilip yalnız `tool.call` süresi doğrulaması için
  kullanılır; `OTEL_LOG_TOOL_CONTENT` **asla açılmaz**.
- **Transcript** (`~/.claude/projects/**/*.jsonl`): `assistant` kayıtları →
  `usage.request` (dedup `DATA_MODEL.md` §2); dosya ilk/son satırı →
  `session.*`; `isCompactSummary`/özet kayıtları → `session.compacted`.
- **Statusline** (opsiyonel betik): stdin JSON → `statusline.tick` +
  `rate_limits` varsa `quota.snapshot{source=statusline}` (hesap kimliği
  yoksa saklanmaz, yalnız canlı gösterilir).
- **Hooks** (opsiyonel, `async:true`): SessionStart/End, UserPromptSubmit,
  PostToolUse, PreCompact/PostCompact → yalnız kimlik/zaman/araç adı.
- **Kota poller**: `/api/oauth/usage` → `quota.snapshot{source=usage_api}`.

## 4. Sıralama, idempotentlik, gecikme
- İdempotentlik anahtarı (Stage 4): `sha256(type | ts | source.instance_id |
  payload_hash)` — yalnız `payload_hash` yetmez (aynı payload'lı iki gerçek
  olay, ör. iki `session.started`, farklı zamanlarda meşru). Aynı anahtar
  ikinci kez gelirse yazılmaz (at-least-once kaynaklar).
- `received_at − ts` = kaynak gecikmesi; `collector.health.lag_s` buradan.
- Olaylar `ts`'ye göre değil `received_at`'e göre append edilir; türetim
  sorguları `ts`'ye göre; geç gelen olay etkilenen gün/oturum özetini
  **kirli** işaretler (yeniden hesap kuyruğu).

## 5. Yeniden üretim (replay)
`cci replay --from <ts>`: türetilmiş tablolar silinir, `events` baştan
işlenir; `summary_version`/`estimator.version` değişimlerinde otomatik.
Determinizm: türeticiler saf fonksiyon (events, config, now enjekte).
**Sınır (R-12):** `events` 30 gün saklanır ve özet kararlılaştıktan sonra
payload budanır (zarf + hash kalır); replay 30 günle sınırlıdır, daha eski
dönem `usage_records`/`quota_snapshots` (365 gün) ve özetlerden (süresiz)
yeniden üretilir. Transcript 30 gün mevcut olduğu için pencere örtüşür.

## 6. Bus API (in-process)
Uygulama **basit** (R-4): SQLite `events` tablosu + süreç içi pub/sub
(liste + async görevler); mesaj kuyruğu/çerçeve yok.
```
bus.publish(Envelope)            # şema doğrulama → allow-list → yaz → abonelere
bus.subscribe(type_glob, handler, ordered=True)
```
Aboneler: normalizer, dedup, summaries, estimators, alert engine, snapshot
writer, WS yayıncısı. Abone hatası olayı **düşürmez** (yazım önce), hata
`collector.health`'e sayılır.
