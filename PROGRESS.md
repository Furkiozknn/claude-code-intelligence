# İlerleme Günlüğü — Claude Code Intelligence Platform

Bu dosya otonom çalışmanın hafızası. Her turda: (1) burayı oku, (2) aktif
fazın sıradaki parçasını yap, (3) bulguları gerekçelendirerek kaydet,
(4) commit at. Faz sırasını atlama; **araştırma bitmeden platform kodu
yazma** (araştırma araçları serbest).

**Kapsam:** `D:\Repolar\claude-code-intelligence`.
**Sınır:** GitHub'a yayınlama yok (`raporlar/ONAY-BEKLEYENLER.md`).
**Dil:** Türkçe. Kaynak kod yorumları ASCII olabilir; kullanıcıya görünen
metin düzgün Türkçe.
**Kullanıcı durumu:** 7 Eylül işte; "durma, onay isteme, döndüğümde her
şeyi aktar" dedi. Özet rapor: `D:\Claude Projeleri\raporlar\2026-09-07-
claude-code-intelligence-ilerleme.md` (her büyük adımda güncelle).
**Araç notu:** Bash heredoc ile Windows yolu (`\`) + backtick içeren metin
yazma — parse patlıyor; böyle dosyalar için Write. Python konsolunda her
çağrıda `export PYTHONIOENCODING=utf-8`.

---

## Faz haritası (MASTER_PROMPT bölümlerine eşlenmiş)

| Faz | İçerik | MP § | Durum |
|---|---|---|---|
| 0 | Kurulum | — | ✅ |
| 1 | **Keşif** — ≥100 repo (hedef 150–300) | 2–4 | ✅ 232 repo |
| 2 | **Puanlama** — 13 kriter/100, gerekçeli | 5 | ✅ 55 puanlı |
| 3 | **Veri toplama analizi** | 6 | ✅ v1 + resmî doküman doğrulaması |
| 4 | **Top 20** | 7 | ✅ `research/reports/top20.md` |
| 5 | **Derin analiz** — Top 20 kaynak kod + 2 referans repo | 8–9 | ✅ 20 not + `notes/03` semconv + batch-06 puan revizyonu |
| 6 | **Sentez** — pattern / anti-pattern / çözülmemiş / rekabet | 38 | ✅ `research/reports/sentez.md` (58 kalıp, 14 anti-kalıp, 10 açık problem, matris, §38 tablosu, D1–D10) |
| 7 | **Mimari** | 10–36, 39–40 | ✅ 8 belge (`docs/`) + README + CONTRIBUTING; Faz 9 eleştirisiyle revize edilecek |
| 8 | **Ürün spesifikasyonu** | 22–23 | ✅ `docs/PRODUCT.md` (ürün, UX, dashboard, CLI, TUI, uyarı, tray/statusline) |
| 9 | **Öz-eleştiri** (18 soru) | 41 | ✅ `docs/SELF_CRITIQUE.md`; 12 revizyon (R-1…R-12) belgelere işlendi |
| 10 | **İmplementasyon** Stage 1–16 | 42 | 🔄 Stage 1 ✅ model · 2 ✅ adaptör sözleşmesi · 3 ✅ toplayıcılar (zarf+ingest kapısı, transcript, kota poller, OTLP JSON alıcı+metrik) · 4 ✅ SQLite olay deposu · 5 ✅ normalizasyon+dedup/birleştirme · 6 🔄 fiyat tablosu + günlük/oturum özetleri (koruma yasası) · 7 🔄 pace v1 |
| 11 | **Benchmark → eleştiri → iyileştirme** | 43 | ⬜ |

---

## Araştırma katalog protokolü
- `research/inbox/batch-NN.json` → `python research/tools/catalog.py ingest …`
- `depth`: shallow → fetched (README) → deep (kaynak). Puan yalnız fetched+.
- `gaps` / `top N` / `report`. Konsol: `PYTHONIOENCODING=utf-8`.
- Testler: `python -m unittest research/tools/test_catalog.py` (9 test).
- Derin notlar: `research/notes/deep/<owner-repo>.md` (20 adet).
- Puan revizyonu: `score_notes` içinde `rev:` öneki = kaynak okuması sonrası.

---

## Sıradaki işler (öncelik sırası)

1. **Faz 6 sentez** — `research/reports/sentez.md`: (a) kalıp kataloğu
   (20 nottaki "Platforma aktarılacaklar" birleştirilmiş, kaynağıyla),
   (b) anti-kalıplar, (c) çözülmemiş problemler (kota birimi, alıcı kapalı
   davranışı, hesap kimliği, sidechain/advisor çift sayımı, TTL karışımı),
   (d) MP §38 rekabet tablosu (özellik × bizim / en iyi mevcut / neden daha
   iyi / nerede onlar daha iyi / ne alınacak), (e) Top-20 karşılaştırma
   matrisi (§8 boyutları × repo).
2. **Faz 7 mimari** — `docs/ARCHITECTURE.md` + `DATA_MODEL.md` + `EVENTS.md`
   + `COLLECTORS.md` + `PRIVACY.md` + `PLUGINS.md`; MP §10–36. Girdi:
   `notes/03` eşleme tablosu, tycho zarf ilkesi, cacheeconomics Figure tipi,
   codeburn sağlayıcı arayüzü, VibeBill koruma yasası, vibe-bar forecast.
3. **Faz 8 ürün/UX** — yüzeyler (CLI/TUI/Web/tray/statusline), "Şu anda ne
   yapmalıyım?" motoru spesifikasyonu, uyarı motoru.
4. **Faz 9 öz-eleştiri** (18 soru) → mimariyi düzelt.
5. **Doğrulama deneyleri (Aşama 1'de, kendi alıcımızla):** OTLP alıcı
   kapalıyken davranış (`[3P telemetry]` debug satırları); `/api/oauth/usage`
   429 başlığı (nazik); `modelPricing` şeması (statusline sayfası).
6. Stage 1 implementasyon (Faz 10).

---

## Günlük

### 7 Eylül 2026 — Faz 0 · Kurulum ✅
Depo, katalog aracı (13 kriter/100), prototip dersleri (`notes/00`), seed 41.

### 7 Eylül 2026 — Faz 1 · Keşif ✅
batch-01 (49, 12 kategori) · batch-02 (36, fetch ile doğrulanmış büyük
projeler + hooks/OTLP/sqlite) · batch-03 (104, GitHub topic sayfaları).
**232 repo**, 14 kategori ≥3, 11 yaklaşım ≥2. Topic sayfaları arama
motorundan 5–10× verimli.

### 7 Eylül 2026 — Faz 2 · Puanlama ✅
- Tur 1 (batch-04): 39 repo. Tur 2 (batch-05): 16 repo. **Toplam 55.**
- **Araç hatası bulundu ve düzeltildi:** gelen kayıtta `depth` yoksa
  `shallow` varsayılıp mevcut `fetched` kaydın puanları sessizce
  düşüyordu (25 kayıt). Etkin derinlik = mevcut ∨ gelen; 9 testli
  `test_catalog.py` eklendi. (Kullanıcının ilkesi: hatayı düzeltme,
  sınıfını yok et.)

### 7 Eylül 2026 — Faz 3 · Veri toplama analizi ✅ (v1)
`notes/01`: 11 yaklaşım × 8 boyut, özet matris, ön karar. Resmî
dokümanlarla doğrulandı (`notes/02`):
- **OTel:** `claude_code.cost.usage` istemci tarafı fiyat tablosu ("satıcı
  tahmini"); `query_source`/`agent.name`/`skill.name`/`mcp_tool.name`
  öznitelikleri → atıf bedava; `api_request` olayı `cost_usd_micros` +
  `request_id`; `prompt.id`/`message.uuid`/`client_request_id`
  korelasyonu; prompt/yanıt varsayılan redakte; alıcı kapalıyken davranış
  belgelenmemiş; `rate_limits` yok.
- **Hooks:** 30+ olay; stdin'de token yok; `async:true` bloke etmez ve
  zaman aşımsız; çıkış 2 bloke eder; `prompt_id` OTel ile aynı anahtar;
  `PreCompact/PostCompact` gözlenmiş sıkıştırma sinyali.
- **Statusline:** `rate_limits.five_hour.used_percentage`/`resets_at`
  (epoch sn), yalnız Pro/Max ve ilk yanıttan sonra, pencere sıfırlanınca
  alan düşer; `cost.total_cost_usd` istemci tarafı, **`modelPricing`
  yalnız managed kapsamda**; `context_window.used_percentage` yalnız girdi.
- **Settings:** `env` bloğu OTel değişkenlerini taşıyabilir (kullanıcı
  seviyesi her projede).
- **Rate-limit header'ları kaynak koddan kesinleşti** (`anthropic-
  ratelimit-unified-{5h,7d}-{utilization,reset,status,surpassed-threshold}`,
  `-status`, `-representative-claim`, `-fallback-percentage`, `-overage-*`).

### 7 Eylül 2026 — Faz 4 · Top 20 ✅
`research/reports/top20.md`: 20 repo, 12 kategori kapsaması, her seçim için
"neden bu / neden daha yüksek puanlı X değil", runner-up'lar, anti-pattern
vaka listesi, repo başına derin analiz planı.

### 7 Eylül 2026 — Faz 5 · Derin analiz ✅ (20/20 not + puan revizyonu)
Klonlar scratchpad'de (16 repo + semconv-genai); codeburn/ccusage/zcquant
ilk klonlarda Windows checkout hatası → `core.longpaths` ile taze sığ klon;
ccusage için ilk URL bir fork'a gitti (`cosmosality`), doğrusu
`ryoppippi/ccusage`. ActivityWatch/openllmetry/litellm web + veri dosyasıyla
incelendi. **En değerli bulgular:**
- **tycho `SCHEMA.md`:** 49 810 kayıt üzerinden transcript gerçekliği —
  aynı mesaj **7 kez** yazılabiliyor (dedup şart), `attribution*` alanları
  transcript'te var, `cache_creation.ephemeral_5m/1h` her kayıtta, 1 saatlik
  cache primi aylık varyansın 2/3'ü; ADR 0001 "içerik alanı olmayan zarf".
- **ccusage Rust'a yeniden yazılmış** (19 adaptör crate); dedup kazanan =
  max toplam token; **sidechain replay (#913)** ve **advisor iterasyonu**
  yeni çift sayma sınıfları; tarihe göre fiyat tarifesi.
- **VibeBill:** atıf skoru 0.6/0.25/0.15, güven katmanları, **koruma yasası**
  (`toplam = atıflı + waste + overhead + out-of-scope`, `--strict` çıkış 3).
- **vibe-bar:** üç adaylı harman tahmin (0.52/0.34/0.14 × güvenilirlik),
  4 bileşenli güven skoru, belirsizlik bandı, uyarlanabilir hedef — ML yok.
- **cacheeconomics:** `Figure{released, withheld_because, DRAFT|RECONCILED}`
  — mutabakat kapısını geçmeyen rakam **basılmaz**; toplam en zayıf parçayı
  miras alır; ölçülmüş TTL (5 dk: 300–420 sn; 1 sa: 56 dk).
- **codeburn:** 46 sağlayıcı arayüzü (`SessionSource`, `probeRoots`),
  **guard** hook'ları (fail-open, JSON karar), **act** günlüğü (yedek → hash
  → uygula → geri al), realized-vs-estimated raporu, rıza parmak izi.
  Eksi: `userMessage` yerel cache'te, UA taklidi.
- **claude-pace:** hesap kimliği olmadan kota cache'lenemez → `--`.
- **codexU:** pencereleri **süreye** göre sınıflandır, `authoritative` bayrağı.
- **agenttrace:** teşhis modeli + deterministik "önce buna bak" merdiveni.
- **toktrack:** `CACHE_VERSION` + geçmişi koruyarak yeniden hesap;
  `retroactive_reconciliation` (Copilot geçmişi geri yazıyor).
- **TokenTracker:** account/local kaynak kapsamı, LWW "yokluk ≠ silme".
- **OTel GenAI semconv (`notes/03`):** `gen_ai.usage.cache_read/cache_write.
  input_tokens`; `input_tokens` **cache dahil** (Anthropic'te hariç);
  `token.type` yalnız input|output; `gen_ai.conversation.compacted`; tüm
  alanlar `development`.
- **Resmî belge ek okuması:** traces beta, `OTEL_LOG_TOOL_CONTENT`,
  `tool_decision`/`permission_mode_changed`/`auth`/`mcp_server_connection`
  olayları, kardinalite değişkenleri, `otelHeadersHelper`; alıcı kapalıyken
  davranış **hâlâ belgesiz**; `modelPricing` yalnız managed; yerel transcript
  saklama **30 gün** (`cleanupPeriodDays`), Desktop/Cowork muaf.
- Doğrulama: claude-meter Authorization başlığını **temizliyor** (risk kapandı).
- **Puan revizyonu (batch-06, 20 kayıt, `rev:` notlu):** yeni sıralama
  codeburn 72.9 · ccusage 72.2 · litellm 71.7 · vibe-bar 70.1 · langfuse
  69.7 · toktrack 68.4 · tycho 68.2 · activitywatch 68.1 · codexU 67.6;
  düşenler: Maciek (accuracy 9→6: P90 "limit" Inferred), disler (privacy
  3→2), zcquant (data 8→5). `research/reports/catalog.md` yenilendi.

---

## Bilinen riskler / açık sorular
- `/api/oauth/usage` belgelenmemiş; şema değişebilir.
- OTLP alıcısı kapalıyken Claude Code davranışı bilinmiyor (Aşama 1 deneyi).
- Claude Desktop token cache'ini çözmek güçlü ve hassas — opt-in, salt
  okunur, asla diske yazılmaz; README'de açık anlatım.
- **Tedarik zinciri:** üçüncü taraf repo klonu (`toktrack`) `.claude/skills`
  taşıyınca bu oturuma **skill olarak enjekte oldu**; klonları her zaman
  scratchpad'de tut, `.claude/` içeriğini çalıştırma; platform README'sinde
  uyarı.
- Katalogdaki dil/teknoloji etiketleri bayatlayabilir (ccusage: TS → Rust).
