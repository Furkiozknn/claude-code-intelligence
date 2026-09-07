# Derin analiz · xiufengsun/TokenTracker

**Okunan:** `src/lib/context-health.js`, `src/lib/account-usage-dedup.js`,
`src/lib/source-metadata.js`, `src/lib/usage-limits.js` (baş), `src/lib/telemetry.js`
(grep), `src/commands/sync.js` (grep), `package.json`. Node CLI (`tokentracker-cli`
0.96.1) + macOS (Swift) / Windows (.NET) / Linux (Tauri) yerel uygulamalar +
bulut senkron/leaderboard. "36 araç" desteği, masaüstü evcil hayvan, başarımlar.

## Kaynak taksonomisi
- `ACCOUNT_LEVEL_SOURCES = {cursor, trae-cn}` → `source_scope: account | local`.
  Hesap seviyesi kaynaklar cihaz başına **aynı** veriyi görür; `usage_scope=
  personal` bunları dışarıda tutar ve **neden dışlandığı** (`reason:
  account_level_source`) listelenir.
- **Çapraz cihaz dedup (LWW):** Cursor'da kararlı oturum kimliği yok → saat
  bazında (hour, source, model) satır MAX; TRAE-CN **düzeltilebilir snapshot**
  (toplam aşağı revize, model değişimi, yarım saat kovası taşınması) → kanonik
  gerçek **oturum seviyesinde** `(user_id, source, session_id)`, cihaz kimliği
  kimlik değil; strict-LWW (`>`) ile yeniden teslim idempotent; **"yokluk =
  silme" kanıtlanmadığı için hiçbir satır silinmez**; sağlayıcı tarafı sıra
  sinyali yok → istemci mantıksal zaman damgası (belgeli artık risk).
  Doğrulama kaydı: "repeated-fetch stability VERIFIED, cross-device NOT
  DIRECTLY VERIFIED" — kanıt durumu kodda yazılı.
- JS modülü, SQL göçlerinin **çalıştırılabilir spesifikasyonu**; testler ikisini
  birlikte sabitliyor.

## Context sağlığı (`context-health.js`)
Sabit bağlam tahmini = talimat dosyaları (`~/.claude/CLAUDE.md`, `AGENTS.md`,
proje eşdeğerleri) + tüm `SKILL.md`'ler + MCP sunucuları × (varsayılan 5 araç ×
400 token). Token ≈ CJK karakter + diğer/4. Eşik: ≥50k high, ≥20k medium.
İçerik döndürülmez (yalnız boyut). 5 dk cache.

## Kota/limitler (`usage-limits.js`)
2 dk bellek içi cache, **en yakın pencere sıfırlanmasında erken sona erer**
(5 sn taban: "şimdi sıfırlanıyor" diyen sağlayıcı her poll'u tam tura
çevirmesin); 15 sn sağlayıcı zaman aşımı; Codex token yenileme + kalıcılaştırma
(kendi yeniliyor — riskli), Cursor/Grok/Qoder/Ark/… limit alıcıları.

## Telemetri ve senkron
- Heartbeat: sha256(namespace + machine id), sürüm, platform, kabuk — 4 alan;
  `TOKENTRACKER_NO_TELEMETRY=1` ve `DO_NOT_TRACK` ile kapanır; namespace
  sürümlü (döndürülebilir anonim id).
- Bulut senkron/leaderboard `publishAccount` ile; anti-cheat iş akışları var —
  kullanım verisinin **paylaşımı** ürünün parçası (platform için karşıt örnek:
  local-first çekirdek, paylaşım ayrı rıza).

## Platforma aktarılacaklar
1. `source_scope` (account/local) ve **dışlama gerekçesi** çıktıda.
2. Hesap seviyesi kaynaklar için LWW + "yokluk silme değildir" kuralı;
   doğrulama durumunu kodda belgeleme (SCHEMA_VERIFIED'ın kardeşi).
3. Kota cache'inin **reset anında erken sona ermesi**.
4. Sabit bağlam maliyeti (talimat + skill + MCP şeması) tahmini — "context
   intelligence" için ucuz ve içeriksiz.
