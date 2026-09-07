# PROVIDERS — toplayıcı ve sağlayıcı adaptörü sözleşmesi

Durum: Faz 7 taslağı. Kararlar: sentez D1, D8; kanıt: codeburn `Provider`,
toktrack `CLIParser`/`SourceInstance`, ccusage adaptör crate'leri, VibeBill
`SCHEMA_VERIFIED`, codexU normalizer, TokenTracker kaynak kapsamı.

## 1. İki kavram
- **Toplayıcı (collector):** veri **kanalı** — OTLP alıcı, transcript
  izleyici, kota poller, statusline tap, hook alıcı, (research) proxy.
- **Sağlayıcı adaptörü (provider adapter):** bir ürünün/CLI'nin verisini
  birleşik modele çeviren modül — anthropic/claude-code, openai/codex,
  google/gemini-cli, github/copilot, cursor, aider…

Bir adaptör birden çok toplayıcıdan beslenebilir (Claude Code: OTLP +
transcript + statusline + poller). Her adaptör **kaynak örneği** üretir
(`SourceInstance`: aynı sağlayıcı, farklı `CLAUDE_CONFIG_DIR`, Desktop vs CLI,
uzak makine).

## 2. Adaptör arayüzü (dil bağımsız; JSON-RPC 2.0 over stdio veya in-process)
```
discover()        → [SourceInstance]            # nerede veri var; probe_roots ile birlikte
probe_roots()     → [{path|url, label, exists}] # doctor: "araç yok mu, yol mu yanlış"
capabilities()    → { tokens, cost_vendor, quota, sessions, tools, attribution,
                      realtime, history_days, account_scope: "account"|"local",
                      schema_verified: bool, verified_at: date, retroactive_reconciliation: bool }
collect(instance, cursor) → { raw_batch, next_cursor, complete: bool }
normalize(raw_batch)      → [Envelope]          # DATA_MODEL/EVENTS şemasında
health()          → { status: ok|degraded|down, last_success_at, lag_s, error_class, retry_after_s }
```
- `cursor`: dosya kaynaklarında `{path: {size, mtime, bytes_consumed}}` manifesti
  (VibeBill); ağ kaynaklarında `since`/etag. Bozuk cursor → sessiz tam yeniden.
- `collect` **salt okunur**; hiçbir adaptör kaynak dosyaya/kimlik dosyasına yazmaz.
- `normalize` saf fonksiyon (I/O yok) → test edilebilir, replay edilebilir.
- Hata: dosya bazında atla + say; tek bozuk dosya tümü düşürmez.

## 3. Kimlik ve ağ kuralları (tüm adaptörler)
1. Kimlik dosyası okuma: symlink reddi, düzenli dosya, boyut ≤64 KB, mod
   bitleri (POSIX) kontrolü, aç-öncesi/sonrası stat; yalnız bellekte; log'a
   asla; hata metni redakte (Bearer/sk-*/ya29/gh*/JWT).
2. **Token yenileme yok, token rotasyonu yok.** Süresi dolmuşsa dosyayı
   yeniden oku; hâlâ aynıysa `health=degraded(expired)`.
3. Poll aralığı ≥180 sn; 429 → `retry_after` (gövde veya başlık, min 60 sn,
   varsayılan 300 sn) ve üstel geri çekilme ≤900 sn; 401 → bir kez yeniden
   oku; 4xx diğer → `terminal`; 5xx/ağ → `transient`.
4. Kendi `User-Agent`: `cci/<sürüm> (+repo url)`; taklit yok.
5. Ağ envanteri `ARCHITECTURE.md` §7'de listelenir; listede olmayan host'a
   çıkış **yok** (fiyat yenileme dahil: tek ağ çağrısı, kullanıcı tetikler).

## 4. Claude Code adaptörü (referans uygulama)
| Kanal | Ne verir | Notlar |
|---|---|---|
| OTLP logs/metrics/traces | `usage.request` (+cost vendor), `tool.call`, `session.*`, `prompt.submitted`, `permission.*`, `mcp.connection` | `settings.json` `env` bloğuna yazılır (`cci setup`), kabuk rc değil; alıcı loopback |
| Transcript JSONL | `usage.request` tam geçmiş (30 gün), `attribution*`, `ephemeral_5m/1h` | özyinelemeli glob; dedup §DATA_MODEL; sidechain/advisor kuralları; `cleanupPeriodDays` farkındalığı |
| Statusline | `statusline.tick`, kota (canlı) | iptal edilebilir betik, ≤50 ms, temp dosya yok |
| Hooks | `session.*`, `session.compacted`, `tool.call` (yedek) | `async:true`, her zaman exit 0 |
| `/api/oauth/usage` | `quota.snapshot` (`five_hour`, `seven_day`, `limits[]`, `spend`) | belgesiz; şema değişimi → `provider.schema_change` |
| Rate-limit başlıkları | `quota.snapshot{source=headers}` | yalnız Research Mode proxy'de |
| Claude Desktop token cache | kimlik (opt-in) | OSCrypt/DPAPI, salt okunur, asla diske; ayrı bayrak |

`capabilities()`: tokens ✓, cost_vendor ✓ (vendor_estimated), quota ✓
(usage_api), sessions ✓, tools ✓, attribution ✓, realtime ✓ (OTLP),
history_days 30 (transcript) / ∞ (özet), account_scope local, schema_verified
true (2026-09-07, `notes/02`).

## 5. Diğer adaptörler — doğrulanmış format gerçekleri (Faz 5)
| Adaptör | Kaynak | Kurallar |
|---|---|---|
| OpenAI Codex | `~/.codex/sessions/**/rollout-*.jsonl`; app-server JSON-RPC `account/rateLimits/read` | `event_msg.token_count.last_token_usage` (kümülatif değil); `input_tokens` cache **dahil** → `input = input_total − cached`; model `turn_context`'ten, yoksa `codex-unknown` + dosya sonunda ilk `turn_context`'ten geri doldurma (sayaç); `session_meta.thread_source=="subagent"` → sidechain; dedup `codex:<dosya>:<index>`; kota pencereleri süreye göre |
| Google Gemini CLI | `~/.gemini/tmp/<slug>/chats/*.jsonl` (+eski JSON); `.project_root` işareti | `$set.messages` geçmişi değiştirir; `$rewindTo` yok sayılır (token yakıldı); `tokens{input(cached dahil), output, cached, thoughts(çıktı), tool, total}` |
| GitHub Copilot CLI | `session-store.db` (SQLite) | crash-only satırlar; `initiator=compaction` ayrı; kümülatif kapanış rollup'ı geçmiş günleri **geri yazar** → `retroactive_reconciliation=true`; `total_nano_aiu` faturalama |
| Cursor | `state.vscdb` (SQLite) + hesap API | **account** kapsamı; oturum kimliği yok → saat bazında MAX dedup |
| aider | `.aider.chat.history.md` | yerel saat, ~2 anlamlı basamak → `inferred` |
| Pi | JSONL | `message.timestamp` ms epoch (üst seviye RFC3339); `usage.cost.total` kendi maliyeti |
| OpenCode | `opencode.db` + JSON | SQLite |
| Antigravity | SQLite + protobuf blob | `gen_metadata` çözümü |
| Grok | `updates.jsonl` `costUsdTicks` | tick yoksa maliyet `None` |

Her adaptör `schema_verified` + `verified_at` taşır; doğrulanmamış adaptör
çıktısı **`inferred`** sınıfıyla etiketlenir ve UI'da işaretlenir.

## 6. Sağlayıcı değişim tespiti (MP §28)
- Bilinmeyen alan/tür sayaçları (`unknown_field`, `unknown_record_type`).
- Kota yanıtında sınıflanamayan pencere → `provider.schema_change`.
- `usage_api` yanıt anahtar kümesinin hash'i; değişince olay + `doctor` uyarısı.
- LiteLLM `deprecation_date` → model emekliliği uyarısı.
- Her adaptörün `fixtures/` altında gerçek (redakte) örnekleri; CI'da şema
  testi.

## 7. Uzak kaynaklar (Eco)
`SourceInstance.kind = "remote"`: başka makinenin **özet** snapshot'ı
(codeburn share / toktrack `codex@devbox` fikri). Ham veri taşınmaz; LAN
eşleştirme PIN'i; ayrı rıza. Aşama 4.
