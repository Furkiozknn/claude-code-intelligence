# Derin analiz · ccusage/ccusage (eski ryoppippi/ccusage)

**Okunan:** `rust/adapters/claude/src/README.md`, `daily.rs` (dedup), `lib.rs`
(dedup kazanan kuralı, advisor), `rust/crates/ccusage/src/blocks.rs`,
`docs/guide/cost-modes.md`, `apps/ccusage/src/cli.js`. 18.4k★ — kategorinin
en çok kullanılan aracı. **Bulgu: proje Rust'a yeniden yazılmış** (149 `.rs`;
`rust/crates/{ccusage, ccusage-core, ccusage-cli, ccusage-cli-parser,
ccusage-config, ccusage-terminal, ccusage-adapter-all, ccusage-test-support}`
+ `rust/adapters/{amp, antigravity, claude, codebuff, codex, copilot, droid,
gemini, goose, grok, hermes, kilo, kimi, openclaw, opencode, pi, qwen, zcode,
common}`); npm paketi yalnız platforma göre yerel ikiliyi (`@ccusage/ccusage-
darwin-arm64` vb.) çalıştıran ince sarmalayıcı. Katalogdaki "TypeScript"
etiketi ve önceki "ilk kazanır HashSet dedup" eleştirisi (tycho ADR 0002) **güncel
main için geçersiz** — aşağıdaki kurallar geçerli.

## Claude adaptörü — doğrulanmış kurallar
- Veri dizinleri: `~/.config/claude/projects/`, `~/.claude/projects/`;
  `CLAUDE_CONFIG_DIR` virgülle çok yol; `projects/` **özyinelemeli** tarama
  (iç içe oturum dizinleri + düz eski dosyalar).
- **Dedup anahtarı:** `(message.id, requestId, etkin sessionId)`; `requestId`
  yoksa `message.id + sessionId` (günlük özet için + zaman damgası). Gateway
  yanıtlarında aynı `message.id` farklı oturumda **ayrı** sayılır.
- **Kazanan:** aynı anahtarda **daha büyük toplam token** (input + output +
  cache_creation + cache_read) kalır; eşitlikte `usage.speed` alanı olan
  (daha yeni şema) kazanır → tycho'nun "max output_tokens" kuralıyla aynı ruh,
  toplam üzerinden.
- **Sidechain replay (#913):** `/btw` yan soruları `subagents/` altında
  **ebeveyn mesajlarını aynı `message.id`, farklı `requestId` ile yeniden
  yazabiliyor** (ebeveyn cache-read'i dahil) → en az bir kopya
  `isSidechain: true` ise **ebeveyn kalır**, replay atılır; kendi
  `message.id`'si olan gerçek sidechain yanıtları sayılır. Yeni bir çift
  sayma sınıfı — tycho/VibeBill notlarında yok.
- **Advisor iterasyonları:** `message.usage.iterations[]` içindeki
  `type: advisor_message` kayıtları **kendi modeli altında ayrı** sayılır
  (`<message.id>:advisor:<i>` anahtarı), üst seviye usage yalnız ana modelde
  kalır, diğer iterasyon türleri eklenmez; advisor'da `costUSD` yok → auto/
  calculate fiyatlar, display sıfır gösterir. (VibeBill'in "üst seviye = son
  iterasyon" kuralına ek boyut: **advisorModel** transcript alanı ile uyumlu.)
- "Session" iki anlamlı: rapor gruplaması proje dizini; iç içe dosyalarda
  oturum kimliği dizin adından; kayıt içi `sessionId` de var.
- Bozuk JSONL satırları atlanır.

## 5 saatlik blok algoritması (`blocks.rs`)
```
sırala(ts); blok_başı = floor_to_hour(ilk ts)
her kayıt: since_start = ts − blok_başı; since_last = ts − son_ts
  since_start > 5h  veya since_last > 5h → bloğu kapat
     since_last > 5h ise ayrıca GAP bloğu (son_ts → ts)
     yeni blok_başı = floor_to_hour(ts)
is_active = (now − son_ts < 5h) ve (now < blok_başı + 5h)
burn: tokens_per_minute, cost_per_hour; projection: total_tokens, total_cost, remaining_minutes
```
Blok başlangıcı **saate yuvarlanmış ilk istek** — Anthropic'in gerçek pencere
başlangıcı değil (heuristik; resmi `resets_at` ile çelişebilir → Estimated).

## Maliyet modları
`auto` (varsayılan: `costUSD` varsa onu, yoksa fiyat tablosundan hesap),
`calculate` (her zaman token × fiyat; LiteLLM + models.dev + yerleşik tarihsel
tarifeler, **olay zaman damgasına göre**), `display` (yalnız `costUSD`;
modern transcript'te alan yok → sıfır). Statusline'da `cc` modu = Claude
Code'un kendi hesabına güven. **Fiyat tarihi**: zaman damgasına göre tarife
seçimi — VibeBill/toktrack'te olmayan doğru ayrıntı.

## §8 değerlendirme
| | |
|---|---|
| Data acquisition | 19 adaptör crate; özyinelemeli keşif; çok `CLAUDE_CONFIG_DIR` |
| Data model | Adaptör başına `LoadedEntry`; `speed`, advisor, sidechain bayrakları |
| Accuracy | Dedup + sidechain + advisor kuralları doğrulanmış; tarihli fiyat |
| Analytics | Günlük/aylık/haftalık/oturum/blok; canlı blok izleme; statusline |
| Performance | Rust; snapshot testleri (45 `.snap`) |
| Privacy | Yerel; içerik yok |
| Docs | `docs/guide` 38 sayfa; adaptör README'leri kural düzeyinde |

## Platforma aktarılacaklar
1. Dedup: anahtar `(message.id, requestId, sessionId)` + **sidechain replay**
   istisnası + kazanan = max toplam token (tie: yeni şema).
2. Advisor iterasyonlarını ayrı model satırı olarak sayma.
3. Tarihe göre fiyat tarifesi (`pricing_effective_at`).
4. Blok = Estimated; resmi `resets_at` varsa onu **Observed** olarak öne al.
5. Ekosistem sinyali: lider araç Rust + adaptör crate'lerine geçti → adaptör
   arayüzünü dil bağımsız (JSON şema) tanımlamak platform için doğru karar.
