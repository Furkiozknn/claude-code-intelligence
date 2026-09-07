# Derin analiz · vscarpenter/tycho-cli

**Okunan:** `docs/SCHEMA.md` (434 satır — transcript gerçekliği), `docs/adr/0001`,
`docs/adr/0002`, `docs/superpowers/specs/2026-08-09-cost-truthfulness-design.md`.
**Okunmayan:** Rust kaynak (`src/`), `pricing/default.toml`.
Rust, MIT, 1★, 90 commit. **Kalıp değeri en yüksek repolardan biri.**

## Transcript gerçekliği (SCHEMA.md — 1 004 dosya, 549 MB, 49 810 assistant kaydı, v2.1.156–2.1.201)

- **Üç yerleşim:** `<proje>/<oturum>.jsonl` · `<proje>/<oturum>/subagents/agent-<id>.jsonl`
  · `<proje>/<oturum>/subagents/workflows/wf_<id>/agent-<id>.jsonl`. Keşif
  özyinelemeli `*.jsonl` glob olmalı. `workflows/wf_*/journal.jsonl` transcript
  değil (`{agentId,key,type}`); tür filtresi doğal olarak atlar.
- **15 kayıt türü**; yalnız `assistant` usage taşır (`user` 1 299/1 299 taşımıyor).
- **Zarf alanları:** `uuid`, `parentUuid`, `timestamp`, `sessionId` (alt-ajan
  dosyaları **ebeveyn** oturum id'sini taşır), `session_id` (bazılarında
  snake_case kopya), `requestId` (`req_…`), `cwd` (oturum içinde `cd` ile
  kayabilir), `gitBranch`, `version`, `isSidechain`, `agentId`,
  `isApiErrorMessage`, `message.id` (`msg_…`), `message.model`
  (`"<synthetic>"` olabilir), **`attributionSkill`, `attributionAgent`,
  `attributionPlugin`, `attributionMcpServer`, `attributionMcpTool`,
  `advisorModel`, `slug`** — OTel'in `skill.name`/`agent.name`/… özniteliklerinin
  transcript karşılığı; **atıf transcript'te de var.**
- `costUSD` modern kayıtlarda **sıfır** kez görüldü (eski sürüm alanı).
- **Usage:** `input_tokens`, `output_tokens`, `cache_creation_input_tokens`,
  `cache_read_input_tokens`, `cache_creation{ephemeral_5m_input_tokens,
  ephemeral_1h_input_tokens}` (her kayıtta, v2.1.156'dan beri); yok sayılan:
  `service_tier`, `speed`, `inference_geo`, `iterations`, `server_tool_use`.
- **Tekrarlar (yük taşıyan):** streaming aynı API mesajı için birden çok kayıt
  yazar — gözlenen en kötü **7 kayıt** aynı `(message.id, requestId)` için.
  Naif toplama 7× sayar. **Dedup:** kimlik `(message.id, requestId)`, yoksa
  `uuid`; **en büyük `output_tokens`** kalır, eşitlikte en yeni zaman damgası
  (ADR 0002). ccusage'ın "ilk kazanır HashSet"i reddedildi: sonraki daha tam
  kaydı seçemez.
- **Sentetik kayıtlar:** 107 dosyada `model:"<synthetic>"` +
  `isApiErrorMessage:true`, sıfır usage, çıplak UUID `message.id` — toplama
  girmez, "bilinmeyen model" uyarısı tetiklemez, `doctor` ayrı sayar.
- **Codex:** `event_msg` + `payload.type=="token_count"`; `last_token_usage`
  kullan (`total_token_usage` kümülatif → çift sayar); OpenAI tarzı
  `input_tokens` cache'li girdiyi **içerir** → uncached = input − cached;
  model `turn_context`'ten, yoksa `codex-unknown` (sıfır fiyatlı) ve dosya
  sonunda **ilk** `turn_context`'ten geri doldurma (sayaçla raporlanır).
  Dedup anahtarı `codex:{dosya}:{index}` (dosya bazlı: aynı oturumun iki
  rollout dosyası çakışmasın).
- **Pi:** üst seviye `timestamp` RFC3339, `message.timestamp` **ms epoch** —
  yanlış alan yıl 58486 üretir; sınır `[2000, 2100)`; `usage.cost.total` kendi
  maliyet alanı (Bedrock id'leri için tek doğru kaynak); dedup `pi:<oturum>:<id>`
  (8 hex id'de doğum günü çakışması → oturumla namespace).
- **Doğruluk uyarıları:** `output_tokens` akış ortası anlık görüntü olabilir
  (claude-code#27361); `cleanupPeriodDays` budaması (~7 hafta ufuk); "sıfır
  maliyet = yok say, tabloya düş" (Pi Ollama `:cloud`'a $0 yazıyor).

## ADR 0001 — İzin verici, yalnız-metadata zarf
Her satır **tüm alanları `Option`** olan tek `RawRecord`'a; **içerik alanı yok**;
bilinmeyen alan/tür atlanır ve sayılır; ikinci katı tip `UsageEvent` kodun
gördüğü tek şekil. "Gizlilik incelemesi = grep: içerik sızması için alan
eklemek gerekir, diff'te görünür." Reddedilen: `#[serde(tag="type")]` enum (her
yeni tür parse hatası olur) ve "parse edip gösterirken redakte" ("çıkış
kenarında politika bir bug uzağında sızar; tipte yokluk sızamaz").

## Maliyet dürüstlüğü (2026-08-09 spec)
- ccusage ile mutabakat: tycho tüm farklarda haklı (Codex kapsamı, dedup
  tie-break, 1 saat cache yazma fiyatı).
- **Cache TTL payı:** 1 saatlik yazma payı %65.9 (fable-5), %79.5 (opus-4-8),
  %100 (opus-5); 5 dk oranına göre prim **$232.24** = aylık varyansın 2/3'ü.
  → Cache yazma TTL'i ayrılmadan maliyet **yanlış**. Prototip ve ccusage bunu
  ayırmıyordu.
- **Gölge tahmin:** sıfır fiyatlı/fiyatsız modeller için `[shadow]` eşlemesi
  **açık konfigürasyon**, çıkarım yok; yalnız `doctor`'da; hiçbir toplamı
  değiştirmez. "Hiçbir rakam tahmin edilmez."
- "Atlamalar hata değil veridir": her düzeltme sayaçla görünür.
- Davranış değişikliği geçmiş sayıları oynatıyorsa sürüm notunda yazılır.

## §8 kısa değerlendirme
| | |
|---|---|
| Data acquisition | Sağlayıcı etiketli kökler + External sniff; XDG/env; artımlı değil ama rayon paralel |
| Data model | `UsageEvent` katı tip; 5m/1h ayrı; dedup anahtarı |
| Storage | Bellek içi harita (O(dedup kayıt)); kalıcı cache yok (toktrack'ten farklı) |
| Analytics | Günlük/aylık/oturum/proje/model, cache isabet/tasarruf/kaldıraç, 5s blok projeksiyonu, canlı 2 sn |
| Forecasting | Blok projeksiyonu |
| Privacy | **Yapısal** (ADR 0001); ağ yok; salt okunur |
| Reliability | Sınırlı zaman damgası, sentetik kayıt, kısmi satır toleransı |
| Docs | Olağanüstü: ADR'ler, spec'ler, "gerçek kazanır" kuralı |

## Platforma aktarılacaklar
1. **Zarf tipleri içerik alanı olmadan** (ADR 0001) — çekirdek ilke.
2. **Dedup: (message.id, requestId) → max output_tokens** (ADR 0002).
3. **Cache yazma 5m/1h ayrımı** fiyatlandırmada zorunlu.
4. Transcript `attribution*` alanları → atıf boyutu (skill/agent/plugin/MCP).
5. Sentetik kayıt ve `codex-unknown` sınıfları; "sıfır fiyat = yok" kuralı.
6. `doctor` benzeri "bu sayılara güvenebilir miyim" yüzeyi (MP §34 gözlemlenebilirlik).
7. Gölge tahminler açık konfigürasyonla, toplamlara karışmadan.
